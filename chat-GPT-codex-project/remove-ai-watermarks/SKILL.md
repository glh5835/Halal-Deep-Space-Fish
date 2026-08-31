---
name: remove-ai-watermarks
description: 自动化批量去除工作区中最近写入文件的 AI 水印与来源痕迹（不可见 Unicode、统计重写、C2PA/EXIF/XMP/容器元数据）。通过本地 watermarks-remover HTTP 服务完成。当用户要在编码/写文件后“自动清掉本次产出”、“扫描工作区去水印”、“批量清理 AI 痕迹”，或执行 remove-ai-marks / auto-remove-watermarks 时使用。本技能自动发现文件（git 改动 ∪ 最近修改窗口）并批量清洗，默认输出 *.cleaned.* 副本（非破坏性）。在 Codex / ChatGPT 中加载后，每次写完代码会主动扫描并清理。
---

# 去除 AI 水印（Remove AI Watermarks · Auto）

本技能是本地 `watermarks-remover` HTTP 服务的“自动扫描遥控器”。所有确定性清洗都在服务里完成，**本技能不含任何清洗代码**。不要尝试用本地脚本实现清洗；服务不可达时也不要自行“清理”。

与原版（手动单文件）不同，本版会**自动发现工作区中最近被写入的文件**并批量清洗，用于“写完代码后清掉水印”的自动化场景——在 Codex / ChatGPT 里加载本技能后，每次完成文件写入都应主动触发一次扫描清理。

## 先检查服务

服务地址：环境变量 `WATERMARKS_SERVICE_URL`，默认 `http://127.0.0.1:8765`。

```bash
curl -sf "http://127.0.0.1:8765/health"
```

返回 `{"ok": true, "version": "..."}` 即就绪。若服务端设置了 `WATERMARKS_SERVER_API_KEY`，每个请求带 `Authorization: Bearer <key>`。

不可达时：告诉用户服务未启动并给出启动方法（克隆 <https://github.com/guillaumemeyer/watermarks-remover> 后 `docker compose up core -d`，或 `python service/server.py`），然后停止——绝不用本地代码冒充清洗。

> Codex / ChatGPT 直接使用提醒：本技能依赖本机运行的 `watermarks-remover` 服务（监听 localhost）。用 **Codex CLI / ChatGPT 桌面端在本机执行** 时可正常访问 localhost；纯云端对话无法访问你本机服务，需改为本地执行或让服务可达。

## 核心流程（自动化）

1. 确认服务健康（`/health`）。不可用则停止并报启动方法。
2. 运行 [scripts/auto_clean.py](scripts/auto_clean.py) 自动发现并批量清洗：
   - **发现范围** = `git status --porcelain -uall` 的改动/新增/未跟踪（非忽略）文件 **∪** mtime 在最近 `--window` 秒（默认 600）内修改的文件；两者取并集、去重、剔除 `.cleaned.*` 副本。
   - 跳过 `.git / node_modules / dist / build` 等目录；仅处理支持扩展名。服务对未知格式会在 `/inspect` 返回 `kind: "unknown"`，优雅跳过。
   - 对每个文件：`/inspect` → 若支持则 `/clean`（默认 Layer A）→ 写入 `<名称>.cleaned.<扩展名>` 副本（**非破坏性**，不覆盖原文件）。
3. 汇报汇总：清理 / 跳过 / 失败计数，以及每个文件的 `kind`、是否可疑、服务 `report` 中的动作与计数。
4. 对自然语言文本（.md/.txt/.html 等）完成 Layer A 后**主动提出** Layer B 统计水印重写（见 [references/rewrite-prompts.md](references/rewrite-prompts.md)）；对代码默认只做 Layer A（清不可见 Unicode + 元数据），不自动改写注释/标识符。
5. 诚实说明：Layer B 与像素级去除均为 best-effort，不得宣称“官方检测器不可检出”或“证明是人工写作”；超出服务范围项（像素/音视频 SynthID、C2PA 软绑定、密钥型检测器、训练后门）如实说明。

## 在 Codex / ChatGPT 中直接使用

把本技能目录（`SKILL.md` + `scripts/` + `references/` + `agents/`）作为技能加载到 Codex / Custom GPT 后：

- **自动触发**：在系统/技能指令里写明——“每次完成代码或文件写入后，调用本技能扫描工作区最新改动并清理 AI 水印（Layer A），输出 `.cleaned` 副本；不要等用户重复指定文件。” 这样写完即清。
- **手动触发**：用户说“扫描工作区去水印 / 清掉本次产出”时直接跑 `auto_clean.py`。
- **单文件模式仍可用**：对单个文件，直接 `python scripts/clean_watermarks.py <文件>`（原客户端）。

## 常用调用

```bash
# 默认：扫描当前工作区，git 改动 ∪ 最近 10 分钟，输出 .cleaned 副本
python scripts/auto_clean.py

# 编码刚结束、想覆盖时间窗更宽
python scripts/auto_clean.py --window 1800

# 只看会处理哪些文件，不真正调用服务
python scripts/auto_clean.py --dry-run

# 仅用 mtime 窗口（非 git 仓库）
python scripts/auto_clean.py --no-git

# 确认无副作用后，原地覆盖（危险：先确保已提交/有备份）
python scripts/auto_clean.py --auto-replace

# 指定工作区并附带检测
python scripts/auto_clean.py --cwd ./proj --options '{"detect_before":true}'
```

Windows 手动生成 base64（仅单文件时）：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("input.md"))
```

## 诚实与安全

- 只处理用户拥有或有权处理的内容；若用户意图明显是学术欺诈或非法用途，先警告，再仅执行其有权处理的技术清洗。
- 默认写 `.cleaned` 副本、不覆盖原文件；`--auto-replace` 才原地覆盖，使用前请确保已 `git commit` 或有备份。
- 服务默认只监听 `127.0.0.1`；未配置认证前不要暴露到公网/局域网。
- 详细端点表、options、审计命令见 [references/api.md](references/api.md)。
