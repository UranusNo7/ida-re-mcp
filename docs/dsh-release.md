# DSH 插件的发布与安装

本文件说明 DSH 插件的 Release 内容、构建和发布步骤，以及安装、升级和故障排查。
插件本身只包含配置；服务代码来自同一次 Release 中固定地址的 Python wheel。

## Release 内容

当前 Release 使用 tag `dsh-v1.1.0`，包含三个文件：

| 文件 | 内容 |
| --- | --- |
| `ida-re-mcp-dsh-1.1.0.tgz` | 只含配置的 DSH bundle：`package.json`、`cordis.patch.yml`、`locale/en.json`、`locale/zh.json`、`icon.svg`、`README.md`、`LICENSE`。不含 Python 代码、IDA、uv 或本机路径 |
| `ida_re_mcp-1.0.0.dev0-py3-none-any.whl` | 当前仓库构建的 wheel，只含包源码、元数据和许可证 |
| `SHA256SUMS` | 上面两个文件的 SHA-256 |

bundle 内的启动配置固定为：

- `command`：`uv`
- `args`：`tool run --python 3.13 --from <同一次 Release 的 wheel 地址> ida-re-mcp serve`

wheel 地址固定指向 `dsh-v1.1.0`，末尾带 `#sha256=` 哈希片段，例如
`https://github.com/UranusNo7/ida-re-mcp/releases/download/dsh-v1.1.0/ida_re_mcp-1.0.0.dev0-py3-none-any.whl#sha256=...`。
这个片段只是这次构建的版本指纹：当前验证的 uv 0.13.1 不会强制校验它，不能把
它当作安全校验保证。文件完整性由 `SHA256SUMS` 提供，用户下载后手动核对。
启动配置不写 `cwd`，不读取本仓库的 `config.toml`，也不引用 `main` 分支的代码。

## 构建 Release 资产

前置条件：本机有可用的 uv，仓库依赖已按 `uv.lock` 锁定。

```powershell
uv run --locked python scripts/build_dsh_release.py --uv <uv 命令或绝对路径>
```

脚本没有其他选项，产物固定写入 `dist/dsh-release`（`dist/` 已在 `.gitignore`
中忽略，不提交）。构建过程如下：

1. 检查 `dsh-plugin/package.json`：包名、版本 `1.1.0`、MIT 许可证、用途说明，
   不含安装脚本，`files` 覆盖必需文件。
2. 用 `uv build --wheel` 构建当前仓库的 wheel，并检查 wheel 只包含包源码、
   元数据和许可证。
3. 计算 wheel 的 SHA-256，拼出本次 Release 的固定下载地址。
4. 在临时目录生成可移植的 `cordis.patch.yml` 和简短 `README.md`，与
   `package.json`、locale、图标、许可证一起打包为 npm 风格的 tgz。
5. 把 tgz 和 wheel 复制到输出目录，写入 `SHA256SUMS`。

脚本不会改写仓库里的 `dsh-plugin/cordis.patch.yml`，那份文件是本机开发安装
使用的。修改版本号时，需要同时修改 `dsh-plugin/package.json` 的 `version` 和
脚本里的 `BUNDLE_VERSION`、`RELEASE_TAG`；三者不一致时构建会失败。

## 发布步骤

1. 在本地构建并冒烟：确认产物可生成后，先用本次构建的 wheel 做等价启动验证。
   此时 Release 还没公开，bundle 里的地址不可下载，所以本地安装需要临时把启动
   配置的 `--from` 换成刚构建的 wheel 路径（或在启动命令里直接指定这个 wheel）。
   确认服务能启动、`mcp__ida_re__*` 工具可调用后，恢复本机原有的本地安装。
2. 提交并推送本次改动，创建 tag `dsh-v1.1.0`。
3. 在 GitHub 创建 Release，先存为草稿，上传 `ida-re-mcp-dsh-1.1.0.tgz`、
   `ida_re_mcp-1.0.0.dev0-py3-none-any.whl` 和 `SHA256SUMS`。
4. 公开 Release 后，用未登录的网络环境确认 tgz 和 wheel 都能下载，wheel 的
   实际校验值与 `SHA256SUMS` 一致，再按真实 Release URL 重新安装，在 DSH 中
   验证工具可调用。
5. 验证结束后恢复本机原来的本地安装方式。

以上是发布操作步骤；实际发布的版本和文件以 GitHub Release 页面为准。GitHub
自动生成的 “Source code (zip / tar.gz)” 是仓库快照，不是安装包。

## 安装

### 前置条件

- uv：运行 DSH 的进程必须能找到 `uv`。uv 不在 PATH 中时，把 MCP 条目的
  `command` 改成 uv 可执行文件的绝对路径。
- IDA Pro 9.2+ 和有效许可证；动态调试需要 IDA Pro 9.3+ 和 Windows。
- 网络：第一次启动时 uv 要下载 Python 3.13 和项目依赖，换 Release 版本时也要
  重新下载。插件不包含 Python 运行时，不承诺离线可用。

### 步骤

1. 在 DSH 插件管理器中安装 Release 资产地址：

   https://github.com/UranusNo7/ida-re-mcp/releases/download/dsh-v1.1.0/ida-re-mcp-dsh-1.1.0.tgz

   插件管理器不接受 URL 时，先下载这个 `.tgz`，再用它的绝对路径安装。

2. 启用 `@local/ida-re-mcp`。
3. 指定 IDA 安装目录，服务不扫描磁盘，也不会猜测 IDA 的位置：
   - 在 DSH 的 MCP 条目环境变量中设置 `IDADIR`；或者
   - 在平台默认配置文件里设置 `runtime.ida_dir`（绝对路径）。

   Windows 的配置文件是 `%LOCALAPPDATA%\ida-re-mcp\config.toml`：

   ```toml
   schema_version = "1"

   [runtime]
   ida_dir = 'D:\Tool\IDA'
   ```

   macOS 为 `~/Library/Application Support/ida-re-mcp/config.toml`，Linux 为
   `~/.config/ida-re-mcp/config.toml`。

4. 先手动运行一次检查，把 Python 3.13 和依赖下载到本机缓存。命令里的 wheel
   地址以 bundle 中 `cordis.patch.yml` 或 `README.md` 记录的值为准，连同
   `#sha256=` 一起原样复制：

   ```powershell
   uv tool run --python 3.13 --from "<wheel 地址>" ida-re-mcp doctor
   ```

   输出 `healthy: true` 后，回到 DSH 连接；`doctor` 的 `runtime_paths` 会列出
   实际使用的 data、logs 目录。

   如果只在 DSH 的 MCP 条目里设置了 `IDADIR`，手动运行 `doctor` 的终端没有这个
   变量，需要先补上（PowerShell：`$env:IDADIR = 'D:\Tool\IDA'`），否则它会按
   缺少 IDA 的默认配置检查。

5. 在新会话中调用任一 `mcp__ida_re__*` 工具（例如 `workspace.list`）确认连接。

### 校验下载的文件

手动下载后，把 tgz、wheel 和 `SHA256SUMS` 放在同一目录再核对校验值。Linux 和
macOS 可以直接运行：

```bash
sha256sum -c SHA256SUMS
```

Windows 分别计算再与 `SHA256SUMS` 中的值比较：

```powershell
Get-FileHash .\ida-re-mcp-dsh-1.1.0.tgz -Algorithm SHA256
Get-FileHash .\ida_re_mcp-1.0.0.dev0-py3-none-any.whl -Algorithm SHA256
```

### 默认策略

没有配置文件时，服务使用平台用户数据目录和以下默认策略：

- `authoring`、`debug_launch` 开启；
- `debug_attach`、`expert` 关闭。

需要附加外部进程或执行任意 IDAPython 时，在平台默认配置文件的 `[policy]` 中
显式开启并重启服务。`expert` 的代码可以访问文件、网络和子进程，开启前要确认
风险。

### 数据目录

安装后的数据和日志放在平台用户数据目录：Windows 为
`%LOCALAPPDATA%\ida-re-mcp`（日志在其下的 `Logs`），macOS 为
`~/Library/Application Support/ida-re-mcp`，Linux 为 `~/.local/share/ida-re-mcp`。
实际路径以 `doctor` 的 `runtime_paths` 为准。

需要更换位置时，可以设置 `IDA_RE_MCP_DATA_ROOT` 环境变量为绝对路径；这个路径
不能是项目目录或它的上级目录。它与本仓库源码方式使用的 `data/`、`logs/` 是
两套目录，不会自动迁移，也不会删除已有数据。

## 升级

升级时安装新 Release 的 tgz：bundle 版本随 Release 变化，uv 会按新的固定地址
安装新的 wheel。旧 wheel 留在 uv 缓存中，可以自行清理。分析数据在平台用户数据
目录，重装 bundle 不会删除它们。

如果 DSH 不允许覆盖同名 bundle，先移除旧 bundle 再安装新版本；移除 bundle
不影响数据目录。

## 故障排查

- **启用后连接失败或工具报启动错误**：先确认 uv 在 PATH 中或 `command` 已改为
  绝对路径，并确认能联网；再按上面的 `doctor` 命令预热缓存，然后重新启用插件
  或重启 DSH 后重试。
- **`doctor` 输出 `healthy: false`**：检查 `IDADIR` 或 `runtime.ida_dir` 是否为
  IDA 安装目录的绝对路径，确认 IDA 许可证可用；日志位置见 `doctor` 输出中的
  `runtime_paths.logs` 和 `runtime_paths.session_logs`。
- **不能修改 IDB、附加进程或执行 IDAPython**：默认策略关闭了 `debug_attach`
  和 `expert`，在平台默认配置文件中开启后重启服务。
- **下载 Python 3.13 或依赖失败**：首次运行需要网络，可以配置 uv 的镜像或代理
  后重试；插件不提供离线安装包。
