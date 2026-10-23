# ida-re-mcp

IDA Pro 9.2+ 的 headless 逆向工程 MCP 服务。任何支持 MCP 的 AI Agent（Codex、
Claude Code、Kimi CLI 等）都可以通过 stdio 接入，让 Agent 直接驱动 IDA 分析
PE / ELF 文件。当前支持 PE x86/x86-64，以及小端 ELF x86/x86-64/ARM/AArch64。
动态调试需要 IDA Pro 9.3+；IDA 9.2 可用于静态分析。

## 功能

- **静态分析**：程序概览与搜索（`program.*`）、函数、反汇编、类型、交叉引用、
  字符串、伪代码、数据流切片
- **IDB 修改**：重命名、注释、改类型等，每次修改生成新的分析版本（revision），
  旧版本仍可读取
- **动态调试**：Windows x86/x64 本机调试，断点、寄存器、线程、调用栈、内存读写
- **产物**：Markdown / JSON 报告、样本与分析结果导出、IL2CPP 元数据
- **协作**：分析结果持久化在本机 `data/`，多个 Agent 可通过 `workspace_id` 接手
  同一份分析，不必重复导入样本

## 要求

- IDA Pro 9.2+ 及有效许可证；动态调试需要 IDA Pro 9.3+
- [uv](https://docs.astral.sh/uv/)
- 读取伪代码需要对应处理器的 Hex-Rays Decompiler；动态调试需要 Windows

## 快速开始

1. 确认 `config.toml` 中的 `ida_dir` 指向本机 IDA 安装目录，其余选项通常无需修改。
2. 运行检查，确认 `healthy` 和 `worker.available` 都为 `true`：

   ```powershell
   uv run ida-re-mcp doctor --config config.toml
   ```

   `doctor` 检查 IDA 的基础运行环境。它尚未打开数据库，因此
   `worker.hexrays_available` 为 `null`；当前处理器的 Hex-Rays 能力会在实际查询时检查。

3. 在你的 Agent 客户端中登记一个 stdio MCP 服务，启动命令为：

   ```powershell
   uv run ida-re-mcp serve --config config.toml
   ```

   以 Codex 为例，在 `config.toml` 中加入：

   ```toml
   [mcp_servers.ida-re-mcp]
   command = "uv"
   args = ["run", "ida-re-mcp", "serve", "--config", "config.toml"]
   cwd = 'D:\path\to\ida-re-mcp'
   startup_timeout_sec = 240.0
   tool_timeout_sec = 3900.0
   ```

   其他客户端同理，工作目录指向本项目即可。这里的
   `startup_timeout_sec` 和 `tool_timeout_sec` 只限制客户端等待 MCP 服务的时间。
   IDA 子进程的单次操作时限由本项目 `config.toml` 的 `[workers]` 控制：
   `operation_timeout_seconds` 用于普通查询、分析细化、IDB 修改和 `expert.execute`，
   `initial_analysis_timeout_seconds` 单独用于首次导入时的 IDA 自动分析。
   默认值和最大值分别为 1 小时和 3 小时。`expert.execute.timeout_seconds`
   可以缩短单次 Expert worker 操作，但不能超过 `operation_timeout_seconds`；
   修改配置后需要重启 MCP 服务。

## 作为 DSH 插件使用

Release 提供一个只含配置的 DSH bundle：它把本项目注册为 DSH 的 `ida_re` stdio
MCP 服务，工具以 `mcp__ida_re__<tool>` 的形式提供给 Agent。bundle 不含 Python
代码，服务启动时由 uv 从同一次 Release 里固定地址的 wheel 安装并运行，因此
不需要把本仓库放到某个固定目录。

### 安装前准备

- uv：运行 DSH 的进程要能找到 `uv`。uv 不在 PATH 中时，把 MCP 条目的 `command`
  改成 uv 可执行文件的绝对路径。
- IDA Pro 9.2+ 和有效许可证；动态调试需要 IDA Pro 9.3+ 和 Windows。
- 网络：第一次启动要下载 Python 3.13 和项目依赖，换 Release 版本时也一样。
  插件不包含 Python 运行时，也不承诺离线可用。

### 从 Release 安装

在 DSH 插件管理器中安装这个 Release 资产：

https://github.com/UranusNo7/ida-re-mcp/releases/download/dsh-v1.1.0/ida-re-mcp-dsh-1.1.0.tgz

安装后启用 `@local/ida-re-mcp`，在新会话中调用任一 `mcp__ida_re__*` 工具
（例如 `workspace.list`）确认连接。

插件管理器不接受 URL 时，先下载同一个 `.tgz`，再用它的绝对路径安装。GitHub
Release 页面自动生成的 “Source code (zip / tar.gz)” 是仓库快照，不是安装包，
不能用来安装。

### 指定 IDA 安装目录

服务不扫描磁盘，也不会猜测 IDA 的位置，必须明确指定：

- 在 DSH 的 MCP 条目环境变量中设置 `IDADIR`，值为 IDA 安装目录；或者
- 写平台默认配置文件，设置 `runtime.ida_dir`（必须是绝对路径）。Windows 的
  配置文件是 `%LOCALAPPDATA%\ida-re-mcp\config.toml`：

  ```toml
  schema_version = "1"

  [runtime]
  ida_dir = 'D:\Tool\IDA'
  ```

  macOS 为 `~/Library/Application Support/ida-re-mcp/config.toml`，Linux 为
  `~/.config/ida-re-mcp/config.toml`。

`IDADIR` 环境变量和 `runtime.ida_dir` 都没有指定时，服务仍能启动，
`workspace.list` 这类不依赖 IDA 的工具可以正常调用；但 `doctor` 会报告 IDA
不可用，导入样本、静态分析、修改和调试等依赖 IDA 的操作会失败。

没有配置文件时，服务使用平台用户数据目录和以下默认策略：

- `authoring`、`debug_launch` 开启；
- `debug_attach`、`expert` 关闭。

需要附加外部进程或执行任意 IDAPython 时，在配置文件的 `[policy]` 中显式开启
并重启服务。

### 首次启动

第一次连接要下载 Python 3.13 和依赖，可能比 MCP 客户端的启动等待更久。安装后
先手动运行一次检查，把依赖放进本机缓存：

```powershell
uv tool run --python 3.13 --from "<bundle 中记录的 wheel 地址>" ida-re-mcp doctor
```

wheel 地址记录在 bundle 的 `cordis.patch.yml` 和 `README.md` 中（下载 tgz 解开
即可查看），形如
`https://github.com/UranusNo7/ida-re-mcp/releases/download/dsh-v1.1.0/ida_re_mcp-1.0.0.dev0-py3-none-any.whl#sha256=...`，
原样复制即可。输出 `healthy: true` 后再回到 DSH 连接；`doctor` 的
`runtime_paths` 会列出实际使用的 data、logs 目录。

地址里的 `#sha256=` 只是版本指纹；在 uv 0.13.1 上实测不会强制校验，需要核对
文件时按 Release 的 `SHA256SUMS` 手动比较。

如果只在 DSH 的 MCP 条目里设置了 `IDADIR`，当前终端没有这个变量，运行 `doctor`
前先补上，否则它会按缺少 IDA 的默认配置检查：

```powershell
$env:IDADIR = 'D:\Tool\IDA'
```

安装后的数据和日志位于平台用户数据目录（Windows 为
`%LOCALAPPDATA%\ida-re-mcp`），与本仓库源码方式使用的 `data/` 是两套目录，
不会自动迁移或删除原有数据。

发布和打包细节见 [docs/dsh-release.md](docs/dsh-release.md)，相关模块说明见
[docs/project-structure.md](docs/project-structure.md)。

### 本机源码开发（仅本机）

`dsh-plugin/` 仍保留本机开发用的配置：先 `uv sync --locked`，把 `dsh-plugin`
目录安装到 DSH，再启用 `@local/ida-re-mcp`。它的 `command` 和 `cwd` 是本机
绝对路径，移动仓库后需要同步修改。这种方式不进 Release，也不适合作为其他人
的安装步骤。

## 工作原理

```
Agent ──stdio/MCP──▶ supervisor ──IPC──▶ IDA headless worker
                          │                     │
                       data/ 持久化 ◀───────────┘
```

- 服务进程（supervisor）只负责协议和调度，真正的分析在独立的 IDA 子进程中执行；
  IDA 崩溃不会影响 MCP 连接，空闲 worker 会自动退出。
- 导入的样本副本、IDB、每次修改生成的 revision 都写入 `data/`，日志写入 `logs/`；
  相对路径以 `config.toml` 所在目录为准。
- 长任务（首次分析、报告生成）返回 `operation` 编号，用 `operation.wait` 等待完成。
- 首次分析失败或取消且尚未产生 revision 时，使用 `workspace.retry` 重新分析已有
  workspace；不要再次导入同一份样本。
- 所有修改走 `change.prepare` → `change.apply` 两段提交，prepare 先校验，
  apply 成功后才产生新 revision。
- 工具结果的完整数据在 `structuredContent` 中，附带的中文文本只是摘要；
  出错时第一段文本说明原因和下一步，第二段是 `{code,message,details}` 错误对象。
- 单个函数反编译失败时，错误会保留 IDA 提供的函数地址、失败位置和 Hex-Rays 错误码。
  例如 `MERR_BADCALL` 表示调用参数分析失败，应检查调用指令和被调用函数原型；
  用 `function.inspect` 的 `instructions`、`types` 视图继续检查，原始诊断可在会话日志中找到。
  `capability_unavailable` 用于当前环境无法提供所需能力的情况，例如缺少对应处理器的授权。

默认配置允许修改 IDB、启动调试、附加外部进程和执行任意 IDAPython。不需要这些
功能时，在 `config.toml` 的 `[policy]` 中关闭对应选项并重启服务。

## 开发

```powershell
./scripts/run_quality.ps1
```

运行格式检查、类型检查、全部测试和 MCP 启动检查，任一步失败即返回非零退出码。

## 许可证

[MIT](LICENSE)
