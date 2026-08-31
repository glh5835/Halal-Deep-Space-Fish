# HTTP API（watermarks-remover）

服务默认 `http://127.0.0.1:8765`（可用环境变量 `WATERMARKS_SERVICE_URL` 覆盖）。机器可读契约在 `GET /openapi.json`（OpenAPI 3.0.3），需要精确字段时以它为准。

## 端点一览

| 方法 | 路径 | 请求体 | 返回 |
| --- | --- | --- | --- |
| GET | /health | — | `{"ok": true, "version": ...}` |
| GET | /capabilities | — | 服务端可用工具/评分器/后端 |
| GET | /openapi.json | — | OpenAPI 3.0.3 规范 |
| POST | /inspect | `{"file": "<base64>", "name": "notes.md"}` | `{"ok", "kind", "suspicious", "report"}` |
| POST | /detect | `{"file": "<base64>", "name": "notes.txt"}` | `{"ok", "kind", "detections": [...]}` |
| POST | /clean | `{"file": "<base64>", "name": "notes.md", "options": {...}}` | `{"ok", "kind", "cleaned": "<base64>", "report"}` |

## /clean 的 options

- 文本：`nfkc`、`aggressive_homoglyphs`
- 元数据：`keep_non_ai_metadata`、`strip_all_metadata`
- 图片：`remove_pixel`（`"ctrlregen"` | `"diffusion"`，仅当 `/capabilities` 报告后端存在）
- 容器：`also_layer_a_text`
- PDF：`deep_images`（`"auto"` | `"always"` | `"lossless"` | `"never"`；其他值报错，不静默降级）
- 检测：`detect_before` / `detect_after`（文本/图片，结果进 `report`）

## 示例

bash inspect + clean：

```bash
WM="${WATERMARKS_SERVICE_URL:-http://127.0.0.1:8765}"
curl -s -X POST "$WM/inspect" -H 'Content-Type: application/json' \
  -d "{\"file\": \"$(base64 < notes.md | tr -d '\n')\", \"name\": \"notes.md\"}"
curl -s -X POST "$WM/clean" -H 'Content-Type: application/json' \
  -d "{\"file\": \"$(base64 < notes.md | tr -d '\n')\", \"name\": \"notes.md\"}"
```

PowerShell inspect + clean + 解码：

```powershell
$body = @{
  file = [Convert]::ToBase64String([IO.File]::ReadAllBytes("notes.md"))
  name = "notes.md"
} | ConvertTo-Json -Compress
$resp = Invoke-RestMethod -Uri "http://127.0.0.1:8765/clean" -Method Post `
  -ContentType "application/json" -Body $body
[IO.File]::WriteAllBytes("notes.cleaned.md", [Convert]::FromBase64String($resp.cleaned))
```

若服务端要求认证，在请求头加 `Authorization: Bearer <key>`。

## 能力与局限

- `/capabilities` 报告：可选工具（c2patool、exiftool、qpdf、ghostscript）、评分器（scorers.stylometry、scorers.synthid、scorers.synthid_http）、文本水印检测器（text_detectors.markllm、text_detectors.claude-text）、重后端（pixel_backends.ctrlregen、pixel_backends.diffusion、harnesses.markllm）。只推荐报告里存在的能力。
- PDF：缺 exiftool 时 best-effort，缺 qpdf 时不彻底；图片内嵌元数据深挖需要 ghostscript（`deep_images` 控制）。
- Layer A 不去 token-sampling 水印；C2PA 软绑定、密钥型检测器、训练后门、音频/视频水印超出范围。
- 本地检测器不等于官方厂商检测器（Google 已于 2026-08 退役官方 SynthID-text API 检测器；Claude 官方检测 API 尚未公开）。

## 目录/网站批量审计

服务镜像自带 `audit_dir.py`。一次性容器示例：

```bash
docker run --rm -v "$(pwd)/src:/data:ro" watermarks-remover /app/scripts/audit_dir.py /data --json
```

本地检出时：`python3 service/scripts/audit_dir.py DIR --json`。

退出码：0 无可处理项；1 有可处理项；2 用法/拒绝错误；3 部分扫描未完成（视为“不完整”，不是“干净”）。
