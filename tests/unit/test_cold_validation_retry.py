from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ida_re_mcp.application import (  # pyright: ignore[reportPrivateUsage]
    Application,
    _ColdImageIdentity,  # pyright: ignore[reportPrivateUsage]
)
from ida_re_mcp.supervisor.workspaces import RevisionStaging
from ida_re_mcp.worker.errors import WorkerError

_SHA = "a" * 64


def _staging() -> RevisionStaging:
    return RevisionStaging(
        workspace_id="ws_test",
        staging_id="stg_test",
        candidate_revision="rev_candidate",
        expected_revision=None,
        source_revision=None,
        path=Path("C:/staging"),
    )


def _identity() -> _ColdImageIdentity:
    return _ColdImageIdentity(sample_sha256=_SHA)


def _overview(sha256: str) -> dict[str, object]:
    return {"image": {"sha256": sha256}}


def test_cold_overview_retries_open_failure_and_missing_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes: list[object] = [
        WorkerError("ida_open_failed", "IDALib 无法打开 worker 数据库输入"),
        _overview(""),
        _overview(_SHA),
    ]
    calls: list[int] = []

    async def cold_overview_once(_staging: RevisionStaging) -> dict[str, object]:
        calls.append(1)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return cast(dict[str, object], outcome)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    app = cast(Application, SimpleNamespace(_cold_overview_once=cold_overview_once))

    overview = asyncio.run(
        Application._cold_overview(app, _staging(), _identity())  # pyright: ignore[reportPrivateUsage]
    )

    assert overview == _overview(_SHA)
    assert len(calls) == 3


def test_cold_overview_stops_after_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    async def opening_failure(_staging: RevisionStaging) -> dict[str, object]:
        calls.append(1)
        raise WorkerError("ida_open_failed", "IDALib 无法打开 worker 数据库输入")

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    app = cast(Application, SimpleNamespace(_cold_overview_once=opening_failure))

    with pytest.raises(WorkerError) as raised:
        asyncio.run(
            Application._cold_overview(app, _staging(), _identity())  # pyright: ignore[reportPrivateUsage]
        )

    assert raised.value.code == "ida_open_failed"
    assert len(calls) == 5
