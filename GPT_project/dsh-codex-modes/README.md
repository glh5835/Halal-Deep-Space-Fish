# DSH Codex Modes

在同一个 DeepSeek Harness profile 中独立配置产品形态、协作模式和工具边界。每层也可独立安装。

| 插件 | 职责 | 入口 |
| --- | --- | --- |
| [产品形态](packages/product/README.md) | Chat / Work / Codex 的提示前缀、默认工具和工作流 | 新建会话预设，或输入 `/product chat`、`/product work`、`/product codex` |
| [协作模式](packages/collaboration/README.md) | Plan / Default，Plan 执行层只读 | Web 输入栏下拉，或输入 `/collab plan`、`/collab default` |
| [安全沙箱](packages/sandbox/README.md) | 三档工具边界、三档审批策略，可选只读审查器 | profile 的 `cordis.patch.yml` |

## 安装

从交付包解压后进入项目目录，将下方命令中的 `web` 换成目标 profile。安装后重启该 profile 的 DSH 进程。组合包和独立包使用相同的插件行 ID，同一个 profile 选择一种安装方式。

```powershell
$package = Join-Path (Get-Location).Path 'dist\dsh-codex-modes-0.1.0.tgz'
dsh plugin --profile web add "$package"
```

四个安装包都在 `dist`。独立层也可通过相应 `.tgz` 的绝对路径安装。也可以使用下面的 GitHub 直装命令。

```powershell
dsh plugin --profile web add "github:glh5835/Halal-Deep-Space-Fish#dsh-codex-modes&path:/GPT_project/dsh-codex-modes"
```

按需安装单层时，从以下命令中选择。

```powershell
dsh plugin --profile web add "github:glh5835/Halal-Deep-Space-Fish#dsh-codex-modes&path:/GPT_project/dsh-codex-modes/packages/product"
dsh plugin --profile web add "github:glh5835/Halal-Deep-Space-Fish#dsh-codex-modes&path:/GPT_project/dsh-codex-modes/packages/collaboration"
dsh plugin --profile web add "github:glh5835/Halal-Deep-Space-Fish#dsh-codex-modes&path:/GPT_project/dsh-codex-modes/packages/sandbox"
```

本地源码安装也可传入对应包目录的绝对路径。三个单层包和组合包都包含已生成的 JavaScript。发布到 npm 后，可用 `dsh plugin --profile web add <包名>` 安装。

```powershell
dsh plugin --profile web add "D:\path\to\dsh-codex-modes\dist\dsh-codex-modes-0.1.0.tgz"
```

## 配置组合包

例如将下列项写入该 profile 的 `cordis.patch.yml`。独立包的行 ID 相同，`name` 使用对应独立包名。下面演示独立配置安全层和禁用产品形态层。

```yaml
- id: dsh-codex-sandbox
  name: dsh-codex-modes/sandbox
  config:
    sandbox: workspace-write
    approvalPolicy: on-request

- id: dsh-codex-product
  disabled: true
```

工作区以会话目录为准。Plan 的执行守卫优先于安全层的常规规则。安全层的审批只对当前调用有效，固定边界外的请求即使获得审批也会被拦截。受限沙箱仅允许已知工具，终端、任意代码执行、MCP 和未知工具需要当前策略允许且运行于 DSH 的其他有效边界之内。

## 开发和验证

基线为 DSH `0.1.1-rc.2`。代码包含 0.1 系列的文件预设注册和 0.2 系列的运行时注册。Web 下拉使用 `conversation.input.plan` 插槽，缺少该扩展点的版本可使用命令。工作区文件写入适配 DSH 原生本地文件系统。

```sh
npm run build
npm test
npm run pack:all
```

测试通过模拟 DSH 服务调用插件钩子，并检查预期文件是否写入。当前完成了模拟钩子测试，官方 DSH 实际装包、Web 下拉和模型接口联调待验证。以下命令可在隔离 profile 检查包是否被 DSH 发现。

```powershell
dsh --version
dsh --profile web --dump-config
```

参考 [DSH 架构](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md)、[Codex Coding](https://github.com/ygzhang-lab/dsh-plugin-codex-coding)、[Plan / Build](https://github.com/yzhclcl/dsh-plan-build-mode)、[Codex Relay](https://github.com/necokeine/dsh-codex-relay) 和 [Auto Review](https://github.com/PerryLink/dsh-auto-review)。
