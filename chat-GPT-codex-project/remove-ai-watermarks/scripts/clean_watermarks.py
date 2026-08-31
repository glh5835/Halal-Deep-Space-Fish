#!/usr/bin/env python3
"""Thin HTTP client for the watermarks-remover local service.

This script contains NO cleaning logic: it only talks to the local
watermarks-remover HTTP service (default http://127.0.0.1:8765).

Examples:
  python clean_watermarks.py notes.md
  python clean_watermarks.py notes.md -o notes.cleaned.md
  python clean_watermarks.py shot.png -o shot.cleaned.png --options '{"remove_pixel":"ctrlregen"}'
  python clean_watermarks.py notes.md --inspect-only
  python clean_watermarks.py --capabilities
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("WATERMARKS_SERVICE_URL", "http://127.0.0.1:8765")


def call(base_url, method, path, payload=None, api_key=None, timeout=180):
    url = base_url.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = str(exc)
        sys.exit("HTTP %s %s -> %s: %s" % (method, path, exc.code, detail))
    except urllib.error.URLError as exc:
        sys.exit(
            "无法连接服务 %s%s（%s）。请先启动 watermarks-remover：\n"
            "  git clone https://github.com/guillaumemeyer/watermarks-remover\n"
            "  cd watermarks-remover && docker compose up core -d\n"
            "或 python service/server.py，然后重试。" % (base_url, path, exc.reason)
        )


def read_file_b64(path):
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def write_output(path, b64):
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(b64))


def main():
    ap = argparse.ArgumentParser(
        description="调用本地 watermarks-remover 服务去除 AI 水印（仅 HTTP 客户端，不含清洗逻辑）。"
    )
    ap.add_argument("input", nargs="?", help="输入文件路径")
    ap.add_argument("-o", "--output", help="输出文件路径（默认 <名称>.cleaned.<扩展名>）")
    ap.add_argument("--inspect-only", action="store_true", help="只做 /inspect，不做 /clean")
    ap.add_argument("--skip-inspect", action="store_true", help="跳过 /inspect 直接 /clean")
    ap.add_argument(
        "--options",
        default="{}",
        help='/clean 的 options，JSON 字符串，例如 {"detect_before":true}',
    )
    ap.add_argument("--capabilities", action="store_true", help="打印 /capabilities 后退出")
    ap.add_argument("--url", default=DEFAULT_URL, help="服务地址（默认环境变量或 http://127.0.0.1:8765）")
    ap.add_argument("--api-key", help="Bearer API Key（默认读 WATERMARKS_SERVICE_API_KEY / WATERMARKS_SERVER_API_KEY）")
    args = ap.parse_args()

    api_key = (
        args.api_key
        or os.environ.get("WATERMARKS_SERVICE_API_KEY")
        or os.environ.get("WATERMARKS_SERVER_API_KEY")
    )

    if args.capabilities:
        caps = call(args.url, "GET", "/capabilities", api_key=api_key)
        print(json.dumps(caps, ensure_ascii=False, indent=2))
        return

    if not args.input:
        ap.error("需要输入文件路径（或使用 --capabilities）")

    try:
        options = json.loads(args.options)
    except json.JSONDecodeError as exc:
        ap.error("--options 不是合法 JSON：%s" % exc)
    if not isinstance(options, dict):
        ap.error("--options 必须是 JSON 对象")

    health = call(args.url, "GET", "/health", api_key=api_key)
    if not health.get("ok"):
        sys.exit("服务健康检查失败：%s" % health)

    name = os.path.basename(args.input)
    payload = {"file": read_file_b64(args.input), "name": name}

    if not args.skip_inspect:
        insp = call(args.url, "POST", "/inspect", payload, api_key=api_key)
        print("inspect: kind=%s suspicious=%s" % (insp.get("kind"), insp.get("suspicious")))
        if insp.get("kind") == "unknown":
            sys.exit("不支持的格式（%s）。支持范围见 /capabilities 或 /openapi.json。" % name)

    if args.inspect_only:
        return

    if options:
        payload["options"] = options
    result = call(args.url, "POST", "/clean", payload, api_key=api_key)
    if not result.get("ok"):
        sys.exit("clean 失败：%s" % result)
    if not result.get("cleaned"):
        sys.exit("返回缺少 cleaned 字段：%s" % result)

    out = args.output
    if not out:
        stem, ext = os.path.splitext(args.input)
        out = "%s.cleaned%s" % (stem, ext)
    write_output(out, result["cleaned"])

    print("已写入 %s" % out)
    report = result.get("report")
    if report:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
