## 2026-10-20 - Task: 将 ida-re-mcp 接入为 DSH 插件并适配本机 IDA Pro 9.2

### What was done

- 新增配置型 DSH bundle `dsh-plugin/`：把项目注册为 DSH 的 `ida_re` stdio MCP
  服务，工具以 `mcp__ida_re__<tool>` 暴露；bundle 复用项目现有 `config.toml`，
  不复制样本、不改变服务运行方式。
- 将 `config.toml` 的 `ida_dir` 指向本机 `D:\Tool\IDA`。
- 将 IDA 最低版本从 9.3 放宽到 9.2：静态分析在 9.2 上实测可用；动态调试仍要求
  9.3+，9.2 下调用调试会返回 `capability_unavailable`，不会启动会崩溃的调试
  worker。
- 兼容 IDA 9.2 启动时向 stdout 打印的 Qt 迁移横幅：doctor 改为读取探测输出的
  最后一行 JSON；探测 JSON 改为 ASCII 转义，避免中文输出受控制台编码影响。

### Testing

- `uv sync --locked` 成功，`.venv` 使用 Python 3.13.7。
- `uv run --locked ida-re-mcp doctor --config config.toml`：`healthy: true`，
  `worker.available: true`，`ida_kernel_version: 9.2`。
- `pytest tests/unit tests/integration -q`：553 passed。
- `pytest tests/ida -q -k "not debug"`（IDADIR=D:\Tool\IDA）：23 passed，
  9 deselected（9.2 不支持的调试用例）。
- 通过 DSH 插件实际调用链路验证：`workspace.create` 导入
  `tests/fixtures/bin/native_pe_x64.dll`，`operation.wait` 完成首次分析，
  `program.overview` 返回 12 个函数、11 个字符串、8 个导出项。
- `ruff format --check .`、`ruff check .` 通过；`basedpyright` 0 errors。

### Notes

- 改动文件：`README.md`、`config.toml`、`pyproject.toml`、
  `src/ida_re_mcp/{application.py,cli.py}`、
  `src/ida_re_mcp/supervisor/backend.py`、
  `src/ida_re_mcp/worker/{_ida.py,analysis.py,runtime.py}`、
  `tests/ida/{conftest.py,test_worker_e2e.py}`、
  `tests/unit/{test_python_process.py,test_supervisor_backend.py,test_worker_runtime.py}`；
  新增 `dsh-plugin/`。
- 本机原先没有 uv，已用 `python -m pip install --user uv` 安装 0.13.1；DSH 插件
  的启动命令固定使用项目 `.venv\Scripts\python.exe`，不依赖 uv 在 PATH 中。
- 插件已安装到 desktop profile：bundle `@local/ida-re-mcp`，Loader 条目
  `include:ida-re-mcp`，安装结果 `application: applied`。
- 回滚：删除 `dsh-plugin/`，恢复上述文件，使用插件管理器移除
  `@local/ida-re-mcp`；如只需停用，将 `include:ida-re-mcp` 设为 disabled。
- 已知限制：IDA 9.2 的动态调试被显式禁用；需要完整调试能力时请安装 IDA 9.3+。

## 2026-10-20 - Task: 适配更新后的 IDA Pro 9.5 并修复冷验证偶发失败

### What was done

- IDA 更新为 9.5 后重新验证插件链路：doctor 通过，静态分析与动态调试均可运行。
- 修复冷验证的偶发失败：IDA 关闭数据库后仍可能短暂占用文件，冷查询会随机出现
  `ida_open_failed` 或缺少输入 SHA-256。`_cold_overview` 现在最多重试 5 次
  （递增等待），覆盖这两种情况；重试耗尽后才按原错误上抛。
- 新增 `tests/unit/test_cold_validation_retry.py`；并把 `test_application_changes`
  的 fake backend 语义改为“从指定调用起持续不匹配”，使原有失败用例仍然成立。

### Testing

- `ida-re-mcp doctor`：`healthy: true`，`ida_kernel_version: 9.5`。
- `pytest tests/unit tests/integration -q`：555 passed。
- `pytest tests/ida -q`（IDADIR=D:\Tool\IDA）：32 passed，含 Windows 调试链路。
- `pytest tests/ida/test_stdio_e2e.py -q` 连续 3 次全部通过（修复前每 1 至 3 次
  会出现 1 个偶发失败）。
- `ruff format --check .`、`ruff check .` 通过；`basedpyright` 0 errors。
- 重启 DSH 插件后调用 `workspace.list` 正常返回。

### Notes

- 改动文件：`src/ida_re_mcp/application.py`、`tests/unit/test_application_changes.py`；
  新增 `tests/unit/test_cold_validation_retry.py`。
- 回滚：还原 `application.py` 的 `_cold_overview` 重试逻辑与新增测试，恢复
  `test_application_changes.py` 中的 `==` 比较即可。
- IDA 9.5 会输出若干 IDAPython 弃用告警（`getseg`、`get_first_seg` 等），只写入
  worker stderr 日志，不影响本次功能。

## 2026-10-24 - Task: 补充 DSH Release 链接安装与发布文档

### What was done

- README 的 DSH 小节改为 Release 安装说明：在 DSH 插件管理器中填 Release
  资产地址安装，不接受 URL 时下载 `.tgz` 后用绝对路径安装；说明 GitHub 自动
  生成的 Source code 压缩包不是安装包。
- 写明安装前置条件（uv、IDA 9.2+ / 动态调试 9.3+、许可证、首次运行联网）和
  IDADIR 的两种配置方式（MCP 条目环境变量，或平台默认 `config.toml` 的
  `runtime.ida_dir`），并记录默认安全策略（`debug_attach`、`expert` 关闭）。
- 保留本机源码 patch 作为本机开发方式，明确它使用本机绝对路径，不能作为其他
  人的安装教程。
- 新增 `docs/dsh-release.md`：Release 资产、构建命令与产物、发布步骤、安装、
  升级和故障排查。
- 新增 `docs/project-structure.md`：只说明与本次发布和安装相关的模块。

### Testing

- 尚未验证：本地冒烟、Release 上传与远程安装验证由发布流程执行，最终证据待
  补齐后另外追加记录。
- 已核对文档事实来源：`scripts/build_dsh_release.py`（选项只有 `--uv`、产物
  固定写入 `dist/dsh-release`、固定 tag 与 wheel 地址）、
  `dsh-plugin/package.json`（版本 1.1.0、MIT、files 清单）、
  `src/ida_re_mcp/config.py`（平台默认路径与默认策略）、
  `src/ida_re_mcp/cli.py`（serve / doctor / gc）；并检查了当前构建产物
  `dist/dsh-release/` 的 tgz 成员、生成的 `cordis.patch.yml` 和 `SHA256SUMS`。

### Notes

- 改动文件：`README.md`（只替换 DSH 小节）、新增 `docs/dsh-release.md`、新增
  `docs/project-structure.md`、`progress.md`（追加本条）。
- 回滚：还原 README 的 DSH 小节，删除新增的两个 docs 文件，删除本条 progress
  记录；不修改更早的历史记录。
- 未执行：git commit / push / tag、GitHub Release 上传、DSH profile 安装变更。

## 2026-10-24 - Task: 记录 DSH Release 本地验收结果

### What was done

- 追加本次 DSH Release 的本地验收记录：最终构建产物、tgz 与 wheel 内容检查、
  隔离环境真实安装、doctor 检查、官方 MCP 客户端全链路调用和全量测试结果。
- 远程发布之后才可能验证的部分（真实 Release URL 安装、实际 DSH profile 安装、
  界面图标渲染）保持待验证，不提前记为成功。

### Testing

- 最终构建 `dist/dsh-release/` 成功，之后不再重建；tgz 含 7 个成员，通过白名单、
  metadata、图标 XML、无安装脚本、无本机路径检查；wheel 共 70 个文件，不含
  IDA 运行时、IDA 许可证和样本文件。
- 在隔离的 pnpm 环境中真实安装 `@local/ida-re-mcp` 1.1.0 成功。
- 用绝对路径的 uv，从本地 wheel 在仓库外的工作目录、全新 UV 缓存运行
  `doctor`：`healthy: true`，IDA 9.5，Python 3.13，24 个工具。
- 用官方 MCP `ClientSession` 经真实 uv stdio 依次调用 initialize、list_tools、
  `workspace.list`、`workspace.create`（`native_pe_x64.dll`）、`operation.wait`
  和 `program.overview`，全部通过；`structuredContent` 完整，中文摘要正常，
  概览返回 13 个函数（IDA 9.5）。
- 全量 `pytest tests/unit tests/integration`：571 passed。
- `ruff format --check`（111 files）、`ruff check`、`basedpyright` 均通过，
  0 error。
- 尚未验证：GitHub 公开后的真实 URL 安装、实际 DSH profile 中的安装与持久化、
  图标在界面中的渲染；这些留待远程验收。

### Notes

- 改动文件：仅 `progress.md`（追加本条）；未改动 README、docs 和代码，避免
  改变 wheel 内容和哈希。
- 回滚：删除本条 progress 记录；已有文档与构建产物不受影响。

