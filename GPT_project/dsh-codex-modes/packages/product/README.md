# dsh-codex-product

在 DSH 新建会话时可选 Chat、Work 或 Codex。各预设共享一套底层工具能力，会话模式选择决定提示前缀、默认工作流和模型可见的工具。

| 预设 | 默认工作流 | 工具 |
| --- | --- | --- |
| Chat | 问答、解释和写作 | 用户交互与 Web 查询 |
| Work | 确认交付物、查资料、执行和检查 | Chat 工具加本地文件读取、搜索、写入和 Todo |
| Codex | 检查仓库、最小改动、验证 | Work 工具加终端和已安装的代码编辑工具 |

```powershell
$package = Join-Path (Get-Location).Path 'dist\dsh-codex-product-0.1.0.tgz'
dsh plugin --profile web add "$package"
```

以上命令在解压后的项目根目录执行。也可从 GitHub 直接安装，命令为 `dsh plugin --profile web add "github:glh5835/Halal-Deep-Space-Fish#dsh-codex-modes&path:/GPT_project/dsh-codex-modes/packages/product"`。

运行 `/product` 查看当前模式。会话空闲时用 `/product chat`、`/product work` 或 `/product codex` 切换。命令记录写入 DSH 会话日志，重开时从成功的切换记录恢复。已有轮次的工具记录保持可读。

该插件无必填配置。旧版 DSH 从插件内置目录发现预设，新版通过 DSH 预设服务注册。其他会话默认使用自己的 DSH 预设。工具集受目标 profile 已安装的工具影响。Plan 及沙箱判定由各自的插件处理。
