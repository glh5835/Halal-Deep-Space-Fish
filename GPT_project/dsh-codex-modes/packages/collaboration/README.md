# dsh-codex-collaboration

该插件复用 DSH 的 `planMode` 服务、`/plan`、`/plan off` 和原生方案确认。它在执行前允许 Plan 访问已知读取工具和原生用户交互，拦截写入、补丁、终端和未知工具。计划生效后提交的工具调用会重新检查，已经开始执行的操作由原有调用生命周期处理。

```powershell
$package = Join-Path (Get-Location).Path 'dist\dsh-codex-collaboration-0.1.0.tgz'
dsh plugin --profile web add "$package"
```

以上命令在解压后的项目根目录执行。也可从 GitHub 直接安装，命令为 `dsh plugin --profile web add "https://raw.githubusercontent.com/glh5835/Halal-Deep-Space-Fish/dsh-codex-modes/GPT_project/dsh-codex-modes/dist/dsh-codex-collaboration-0.1.0.tgz"`。

支持插槽的 Web profile 在输入栏显示 Plan / Default 下拉。各版本均可使用以下命令。

```text
/collab
/collab plan
/collab default
/collab plan 检查 src 目录并给出修改计划
/collab default 按刚才的计划执行
```

带消息的命令在会话空闲时提交。消息与模式在同一个命令处理器中入队，消息进入模型前会核对选择。命令也可携带 DSH 支持的图片附件。切到 Default 后，工具仍需通过安装的安全层及 DSH 原有策略。

可选配置 `trustedProviders` 声明受限模式可用的纯模型路由，默认 `[deepseek-official]`。只有模型提供方由你信任、且不运行独立代理工具时才添加该路由。
