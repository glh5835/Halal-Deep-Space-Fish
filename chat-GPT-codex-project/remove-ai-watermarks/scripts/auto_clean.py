#!/usr/bin/env python3
"""Auto watermark removal across a workspace (thin HTTP client only).

Discovers recently-written files via:
  * git status (modified / added / untracked, non-ignored), and/or
  * an mtime window (files touched in the last N seconds),
then for each *supported* file calls the local watermarks-remover service
(Layer A by default) and writes a `<name>.cleaned.<ext>` sidecar.

This script contains NO cleaning logic -- the local watermarks-remover
service does all the work. If the service is unreachable it stops with a
clear message (it never impersonates cleaning with local code).

Examples:
  python auto_clean.py                       # discover + clean cwd (git ∪ 10min)
  python auto_clean.py --window 1800         # widen mtime window to 30 min
  python auto_clean.py --no-git              # mtime window only
  python auto_clean.py --dry-run             # list targets, do not call service
  python auto_clean.py --auto-replace        # overwrite originals (NOT default)
  python auto_clean.py --cwd D:/proj --options '{"detect_before":true}'
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clean_watermarks as cw  # the original thin HTTP client

DEFAULT_WINDOW = 600  # seconds

# Directories we never walk into (build output, deps, VCS, assistant state).
EXCLUDED_DIRS = {
    ".git", "node_modules", "dist", "build", ".workbuddy", "__pycache__",
    ".venv", "venv", "env", "vendor", "target", "out", "coverage", ".idea",
    ".vscode", ".next", ".nuxt", ".output", ".svelte-kit", "bin", "obj",
}

# Extensions we are willing to hand to the service. The service still does the
# final support decision via /inspect (unknown -> skipped gracefully).
SUPPORTED_EXT = {
    # text / source
    ".txt", ".md", ".markdown", ".html", ".htm", ".json", ".yaml", ".yml",
    ".toml", ".csv", ".tsv", ".py", ".js", ".jsx", ".ts", ".tsx", ".mts",
    ".mjs", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".java", ".go", ".rs",
    ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash", ".ps1", ".sql",
    ".r", ".lua", ".pl", ".vue", ".svelte", ".css", ".scss", ".less", ".xml",
    ".ipynb", ".tex", ".rst", ".cfg", ".ini", ".env.example",
    # docs / images / containers
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf", ".docx", ".odt",
    ".epub",
}


def discover_git(cwd):
    """Return absolute paths of changed/added/untracked (non-ignored) files."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain", "-uall"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return []  # git not installed
    except Exception:
        return []
    if out.returncode != 0:
        return []  # not a repo / git error -> fall back to mtime
    found = []
    for line in out.stdout.splitlines():
        if len(line) < 4:
            continue
        x, y = line[0], line[1]
        if x == "D" or y == "D":  # skip deletions
            continue
        path = line[3:].strip()
        full = os.path.join(cwd, path)
        if os.path.isfile(full):
            found.append(full)
    return found


def discover_mtime(cwd, window, max_files=3000):
    now = time.time()
    found = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for f in files:
            if ".cleaned." in f:  # never re-process a sidecar
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext not in SUPPORTED_EXT:
                continue
            full = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if mtime >= now - window:
                found.append(full)
            if len(found) >= max_files:
                return found
    return found


def discover(cwd, window, use_git, use_mtime):
    files = []
    if use_git:
        files += discover_git(cwd)
    if use_mtime:
        files += discover_mtime(cwd, window)
    # dedupe, keep existing, drop sidecars / unsupported ext
    seen = {}
    for f in files:
        af = os.path.abspath(f)
        if af in seen:
            continue
        if ".cleaned." in os.path.basename(af):
            continue
        if os.path.splitext(af)[1].lower() not in SUPPORTED_EXT:
            continue
        if os.path.isfile(af):
            seen[af] = True
    return sorted(seen.keys())


def process(path, args):
    name = os.path.basename(path)
    payload = {"file": cw.read_file_b64(path), "name": name}

    kind = suspicious = None
    if not args.skip_inspect:
        insp = cw.call(args.url, "POST", "/inspect", payload, api_key=args.api_key)
        kind = insp.get("kind")
        suspicious = insp.get("suspicious")
        if kind == "unknown":
            return {"file": path, "status": "skipped",
                    "reason": "unsupported format (%s)" % name}

    options = {}
    if args.options:
        try:
            options = json.loads(args.options)
        except json.JSONDecodeError as exc:
            return {"file": path, "status": "error",
                    "reason": "--options not valid JSON: %s" % exc}
    if options:
        payload["options"] = options

    result = cw.call(args.url, "POST", "/clean", payload, api_key=args.api_key)
    if not result.get("ok") or not result.get("cleaned"):
        return {"file": path, "status": "error", "reason": str(result)[:240]}

    if args.auto_replace:
        out = path
    else:
        stem, ext = os.path.splitext(path)
        out = "%s.cleaned%s" % (stem, ext)
    cw.write_output(out, result["cleaned"])
    return {"file": path, "status": "cleaned", "out": out,
            "kind": kind, "suspicious": suspicious, "report": result.get("report")}


def main():
    ap = argparse.ArgumentParser(
        description="自动发现工作区中最近写入的文件并调用本地 watermarks-remover 服务去水印（仅 HTTP 客户端）。"
    )
    ap.add_argument("--cwd", default=os.getcwd(),
                    help="要扫描的工作区根目录（默认当前目录）")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                    help="mtime 窗口秒数（默认 %d）" % DEFAULT_WINDOW)
    ap.add_argument("--no-git", action="store_true", help="不用 git status 发现")
    ap.add_argument("--no-mtime", action="store_true", help="不用 mtime 窗口发现")
    ap.add_argument("--dry-run", action="store_true",
                    help="只列出将处理的文件，不调用服务")
    ap.add_argument("--auto-replace", action="store_true",
                    help="原地覆盖原文件（默认关：写 *.cleaned.* 副本）")
    ap.add_argument("--skip-inspect", action="store_true",
                    help="跳过 /inspect 直接 /clean")
    ap.add_argument("--options", default="{}",
                    help='/clean 的 options JSON，例如 {"detect_before":true}')
    ap.add_argument("--url", default=cw.DEFAULT_URL,
                    help="服务地址（默认环境变量或 http://127.0.0.1:8765）")
    ap.add_argument("--api-key",
                    help="Bearer API Key（默认读 WATERMARKS_SERVICE_API_KEY）")
    args = ap.parse_args()

    api_key = args.api_key or os.environ.get("WATERMARKS_SERVICE_API_KEY") \
        or os.environ.get("WATERMARKS_SERVER_API_KEY")
    args.api_key = api_key

    if args.no_git and args.no_mtime:
        ap.error("不能同时禁用 git 与 mtime 发现")

    if not args.dry_run:
        health = cw.call(args.url, "GET", "/health", api_key=api_key)
        if not health.get("ok"):
            sys.exit("服务健康检查失败：%s" % health)

    targets = discover(args.cwd, args.window, not args.no_git, not args.no_mtime)
    if not targets:
        print("未发现最近写入的可处理文件（git 改动 ∪ %d 秒内修改）。" % args.window)
        return

    print("将处理 %d 个文件：\n" % len(targets))
    for t in targets:
        print("  - %s" % t)

    if args.dry_run:
        print("\n[dry-run] 未调用服务。")
        return

    results, cleaned, skipped, errors = [], 0, 0, 0
    for t in targets:
        r = process(t, args)
        results.append(r)
        if r["status"] == "cleaned":
            cleaned += 1
            print("\n[cleaned] %s" % r["file"])
            print("  -> %s" % r["out"])
            if r.get("kind"):
                print("  kind=%s suspicious=%s" % (r["kind"], r.get("suspicious")))
            if r.get("report"):
                print("  report: %s" % json.dumps(r["report"], ensure_ascii=False))
        elif r["status"] == "skipped":
            skipped += 1
            print("\n[skipped] %s (%s)" % (r["file"], r["reason"]))
        else:
            errors += 1
            print("\n[error] %s (%s)" % (r["file"], r["reason"]))

    print("\n==== 汇总 ====")
    print("清理: %d | 跳过(不支持): %d | 失败: %d" % (cleaned, skipped, errors))
    if cleaned:
        print("提示：Layer B（统计水印弱化重写）对自然语言文本有效，可对本技能提出以进一步弱化 AI 痕迹。")


if __name__ == "__main__":
    main()
