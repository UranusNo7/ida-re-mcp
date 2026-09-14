# pyright: reportPrivateUsage=false
"""Hex-Rays 已加载时，函数失败不能被误报为缺少反编译能力。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ida_re_mcp.worker._hexrays import decompile_function
from ida_re_mcp.worker._ida import IdaModules
from ida_re_mcp.worker.analysis import AnalysisWorker
from ida_re_mcp.worker.errors import WorkerError
from ida_re_mcp.worker.refine import RefineWorker, _FunctionRange


class _Failure:
    def __init__(self, code: int) -> None:
        self.code = code
        self.errea = 0x1010

    def desc(self) -> str:
        return "call analysis failed"


class _HexRays:
    MERR_LICENSE = -100
    MERR_BADARCH = -101
    MERR_ONLY32 = -102
    MERR_ONLY64 = -103
    MERR_BADCALL = -12
    MMAT_GENERATED = 1

    def __init__(self, *, throws: bool = False, licensed: bool = True) -> None:
        self.throws = throws
        self.licensed = licensed

    def hexrays_failure_t(self) -> _Failure:
        return _Failure(self.MERR_BADCALL if self.licensed else self.MERR_LICENSE)

    def decompile(self, _entry: int, failure: _Failure) -> None:
        assert failure.errea == 0x1010
        if self.throws:
            raise ValueError("internal diagnostic")

    @staticmethod
    def init_hexrays_plugin() -> bool:
        return True

    @staticmethod
    def mark_cfunc_dirty(_entry: int, _close_views: bool) -> None:
        pass

    @staticmethod
    def mba_ranges_t(function: object) -> object:
        return function

    @staticmethod
    def mlist_t() -> None:
        pass

    @staticmethod
    def gen_microcode(*_arguments: object) -> None:
        pass


def _api(hexrays: _HexRays) -> IdaModules:
    return cast(
        IdaModules,
        SimpleNamespace(ida_hexrays=hexrays, ida_idaapi=SimpleNamespace(BADADDR=(1 << 64) - 1)),
    )


@pytest.mark.parametrize("throws", [False, True])
def test_decompile_failure_preserves_sdk_location_and_classification(throws: bool) -> None:
    with pytest.raises(WorkerError) as raised:
        decompile_function(_api(_HexRays(throws=throws)), 0x1000)
    assert raised.value.code == "decompilation_failed"
    expected: dict[str, object] = {
        "entry": "0x1000",
        "error_address": "0x1010",
        "error_code": -12,
        "reason_code": "MERR_BADCALL",
        "reason": "call analysis failed",
        "stage": "decompile",
    }
    if throws:
        expected.update(exception_type="ValueError", exception="internal diagnostic")
    assert raised.value.details == expected


def test_actual_license_failure_remains_a_capability_error() -> None:
    with pytest.raises(WorkerError) as raised:
        decompile_function(_api(_HexRays(licensed=False)), 0x1000)
    assert raised.value.code == "capability_unavailable"
    assert raised.value.details["reason_code"] == "MERR_LICENSE"


def test_microcode_and_refine_use_the_same_function_failure_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api(_HexRays())
    checkout = tmp_path / "database.i64"
    checkout.write_bytes(b"fixture")
    worker = AnalysisWorker(checkout)

    def function(*_args: object) -> SimpleNamespace:
        return SimpleNamespace(start_ea=0x1000)

    def address(*_args: object) -> int:
        return 0x1010

    monkeypatch.setattr(worker, "_function_from_input", function)
    monkeypatch.setattr(worker, "_resolve_address", address)
    with pytest.raises(WorkerError) as microcode:
        worker._dataflow_slice(api, {"direction": "backward", "semantics": "may"})
    assert microcode.value.code == "decompilation_failed"
    assert microcode.value.details["error_address"] == "0x1010"
    assert microcode.value.details["stage"] == "microcode"

    with pytest.raises(WorkerError) as refined:
        RefineWorker()._decompile(api, [cast(_FunctionRange, SimpleNamespace(entry=0x1000))])
    assert refined.value.code == "decompilation_failed"
    assert refined.value.details["reason_code"] == "MERR_BADCALL"
