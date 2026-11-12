# dsh-codex-sandbox

安全层在 DSH 工具预执行、单调守卫和最终分发处检查操作。它可独立安装，若检测到 DSH 原生 Plan 状态，执行工具按只读限制处理。

```powershell
$package = Join-Path (Get-Location).Path 'dist\dsh-codex-sandbox-0.1.0.tgz'
dsh plugin --profile web add "$package"
```

以上命令在解压后的项目根目录执行。也可从 GitHub 直接安装，命令为 `dsh plugin --profile web add "github:glh5835/Halal-Deep-Space-Fish#dsh-codex-modes&path:/GPT_project/dsh-codex-modes/packages/sandbox"`。

## 工具边界

| `sandbox` | 可执行范围 |
| --- | --- |
| `read-only` | 已知读取工具和原生用户交互 |
| `workspace-write` | 读取、交互、会话 Todo，以及经校验的会话工作区内原生 `write` / `edit` |
| `danger-full-access` | 此层不限制工具的文件范围，调用仍受 DSH 本身和操作系统限制 |

受限模式根据 DSH 本地文件系统和规范化路径检查工作区。第三方编辑器的修改指令、终端、MCP、委派和其他副作用无法验证的工具会被拒绝。已知敏感路径的直接请求会被识别，读权限仍由当前工具及其原生读策略决定。该插件保护 DSH 的代理工具入口，信任宿主、本地文件系统及安装的插件。第三方插件直接执行的进程、外部模型供应商自己的代理循环，以及宿主之外的并发文件系统修改属于宿主边界。

## 审批

| `approvalPolicy` | 行为 |
| --- | --- |
| `untrusted` | 为变更、未知副作用及边界请求发起单次审批 |
| `on-request` | 为边界请求发起审批，工作区内合法写入无需提示 |
| `never` | 跳过人工审批，越界调用直接拒绝 |

默认 `workspace-write` 和 `on-request`。两个字段独立设置。自动审查器开启后先处理请求，拒绝终止调用，允许继续到当前策略的人工环节。DSH 原生审批渠道不可用时，需批准的调用拒绝。已触及固定沙箱边界的请求即使获准也无法执行，调整配置后重新提交操作。

## 自动审查

在 profile 的 `cordis.patch.yml` 中配置。组合包使用 `name: dsh-codex-modes/sandbox`。示例中的模型名需换成目标 provider 已注册的模型。

```yaml
- id: dsh-codex-sandbox
  name: dsh-codex-sandbox
  config:
    sandbox: workspace-write
    approvalPolicy: on-request
    trustedProviders: [deepseek-official]
    reviewer:
      provider: deepseek-official
      model: YOUR_REVIEW_MODEL
      timeoutMs: 15000
```

省略 `reviewer` 或设为 `false` 可关闭自动审查。审查模型只收到工具名称和结构化分类，不接收原始命令、路径或文件内容，也不获得任何工具。已知删除和敏感路径操作在审查入口拒绝。模型不可用、超时或输出格式错误均以拒绝结束。使用执行外部代理的模型路由时，需要该外部运行时提供自己的边界。
