# 项目结构

本文件只说明与 Release 发布、DSH 插件安装直接相关的模块。其余源码模块在涉及
它们的任务中另行补充，这里不展开。

## 顶层文件

| 路径 | 作用 |
| --- | --- |
| `pyproject.toml` | 包名 `ida-re-mcp`、版本 `1.0.0.dev0`、Python 3.13、命令入口 `ida-re-mcp = ida_re_mcp.cli:main` |
| `config.toml` | 本仓库开发用的配置，`ida_dir` 指向开发机上的 IDA；安装插件的用户不使用它 |
| `dsh-plugin/` | DSH 插件的源目录，供本机开发安装使用 |
| `scripts/build_dsh_release.py` | 生成 Release 资产（bundle tgz、wheel、SHA256SUMS） |
| `dist/dsh-release/` | Release 构建产物；`dist/` 已在 `.gitignore` 中忽略，不提交 |
| `tests/unit/test_dsh_release.py` | 校验构建产物内容与清单字段 |
| `data/`、`logs/` | 本机开发时的分析数据和日志；不提交 |

## DSH 插件与打包

- `dsh-plugin/package.json`：bundle 清单。声明包名 `@local/ida-re-mcp`、版本、
  `files` 打包范围、`license` 以及 `dsh.bundle.patch` 指向的 patch 文件。
  脚本要求清单里没有安装脚本（`scripts` 字段），并用 `files` 列出必需文件。
- `dsh-plugin/cordis.patch.yml`：**本机开发专用** patch。它把服务注册为 DSH 的
  `ida_re` stdio MCP 服务，`command` 指向本仓库 `.venv\Scripts\python.exe`，
  `cwd` 指向本仓库绝对路径。移动仓库或换机器后需要同步修改，因此不能作为
  其他人的安装说明。
- `dsh-plugin/locale/en.json`、`dsh-plugin/locale/zh.json`、`dsh-plugin/icon.svg`：
  插件在 DSH 界面显示的标题、说明和图标。
- `scripts/build_dsh_release.py`：Release 构建脚本。用 `uv build --wheel` 生成
  当前仓库的 wheel，在临时 staging 目录里重新生成可移植的 `cordis.patch.yml`
  （固定 wheel 地址加 SHA-256，不写本机路径），把 package 目录打成 npm 风格的
  tgz，并在输出目录写入 `SHA256SUMS`。脚本中的 `BUNDLE_VERSION`、`RELEASE_TAG`
  和 `RELEASE_REPOSITORY` 决定产物的版本、tag 与下载地址；清单版本与脚本不一致
  时构建会直接失败。仓库里的 `dsh-plugin/cordis.patch.yml` 不会被改写。
- `tests/unit/test_dsh_release.py`：在不联网、不安装插件的前提下检查 tgz 成员、
  固定版本 URL、校验值、清单显示信息和 wheel 内容。

## 安装后运行相关的源码

- `src/ida_re_mcp/cli.py`：命令行入口，子命令为 `serve`、`doctor`、`gc`，
  都接受 `--config`；不传时使用平台默认配置文件。
- `src/ida_re_mcp/config.py`：配置模型和运行目录解析。默认策略为
  `authoring`、`debug_launch` 开启，`debug_attach`、`expert` 关闭；没有平台默认
  配置文件时使用这些安全默认值。`default_config_path()` 决定平台配置文件位置，
  `RuntimePaths.discover()` 决定平台数据和日志目录，并支持
  `IDA_RE_MCP_DATA_ROOT`、`IDA_RE_MCP_LOG_ROOT` 环境变量覆盖。
- `src/ida_re_mcp/application.py`：`Application.open()` 读取配置、准备运行目录。
  `doctor` 报告 `runtime_paths`（data、logs、会话日志）和 worker 探测结果；
  配置里有 `runtime.ida_dir` 时，把 `IDADIR` 传给 IDA 子进程。
- `src/ida_re_mcp/supervisor/backend.py`：启动 IDA worker，合并父进程环境变量与
  显式配置的 `IDADIR`，因此未写配置文件时，父进程环境中的 `IDADIR` 仍然生效。
