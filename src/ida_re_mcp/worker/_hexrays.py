# pyright: reportAny=false, reportAttributeAccessIssue=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""区分 Hex-Rays 能力缺失与特定函数的分析失败。"""

from __future__ import annotations

from typing import Literal, Protocol

from ida_re_mcp.worker._ida import IdaModules
from ida_re_mcp.worker.errors import CapabilityError, WorkerError


class _Failure(Protocol):
    code: int
    errea: int

    def desc(self) -> str: ...


def analysis_failure(
    api: IdaModules,
    failure: _Failure,
    *,
    entry: int,
    stage: Literal["decompile", "microcode"],
    exception: Exception | None = None,
) -> WorkerError:
    """保存 SDK 的原始诊断，Supervisor 仅公开经过筛选的字段。"""

    code = int(failure.code)
    reason_code = next(
        (
            name
            for name in (
                "MERR_LICENSE",
                "MERR_BADARCH",
                "MERR_ONLY32",
                "MERR_ONLY64",
                "MERR_BADCALL",
                "MERR_BADSP",
                "MERR_BADFRAME",
                "MERR_BADBLK",
                "MERR_HUGESTACK",
                "MERR_FUNCSIZE",
                "MERR_COMPLEX",
                "MERR_MEM",
                "MERR_CANCELED",
                "MERR_BUSY",
            )
            if code == getattr(api.ida_hexrays, name)
        ),
        "MERR_UNKNOWN",
    )
    details: dict[str, object] = {
        "entry": f"0x{entry:x}",
        "stage": stage,
        "error_code": code,
        "reason_code": reason_code,
        "reason": str(failure.desc()),
    }
    if int(failure.errea) != int(api.ida_idaapi.BADADDR):
        details["error_address"] = f"0x{int(failure.errea):x}"
    if exception is not None:
        details["exception_type"] = type(exception).__name__
        details["exception"] = str(exception)
    if reason_code in {"MERR_LICENSE", "MERR_BADARCH", "MERR_ONLY32", "MERR_ONLY64"}:
        return CapabilityError(
            "Hex-Rays 无法为当前数据库提供反编译能力",
            capability="hexrays",
            details=details,
        )
    return WorkerError("decompilation_failed", "Hex-Rays 未能完成目标函数分析", details=details)


def decompile_function(api: IdaModules, entry: int) -> object:
    if not api.ida_hexrays.init_hexrays_plugin():
        raise CapabilityError(
            "当前数据库无法初始化 Hex-Rays decompiler",
            capability="hexrays",
        )
    failure = api.ida_hexrays.hexrays_failure_t()
    try:
        cfunc = api.ida_hexrays.decompile(entry, failure)
    except Exception as exc:
        raise analysis_failure(api, failure, entry=entry, stage="decompile", exception=exc) from exc
    if cfunc is None:
        raise analysis_failure(api, failure, entry=entry, stage="decompile")
    return cfunc
