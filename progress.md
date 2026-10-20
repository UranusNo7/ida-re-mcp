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

