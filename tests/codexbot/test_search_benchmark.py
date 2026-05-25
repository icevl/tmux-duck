"""Opt-in search benchmark tests using deterministic fake embeddings."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "search" / "benchmark_cases.json"


def test_benchmark_fixture_shape_is_representative() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert len(raw["documents"]) >= 8
    assert len(raw["queries"]) >= 6
    assert {query["kind"] for query in raw["queries"]} >= {"exact", "semantic"}
    assert any(query.get("fallback") for query in raw["queries"])


def test_fake_provider_benchmark_schema_and_summary_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.benchmark import run_benchmark
    from codexbot.search.client import get_status
    from codexbot.search.state import benchmark_summary_path, read_benchmark_summary

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    summary = run_benchmark(
        fixtures=FIXTURE,
        provider_name="fake",
        batch_size=4,
        chunk_max_chars=400,
        chunk_overlap_chars=40,
        threshold_query_p95_ms=10_000,
        threshold_memory_mb=1024,
        write_summary=True,
    )
    dumped = summary.model_dump(mode="json")

    for key in [
        "ok",
        "model_id",
        "vector_dimension",
        "batch_size",
        "chunk_max_chars",
        "chunk_overlap_chars",
        "document_count",
        "query_count",
        "embedding_docs_per_second",
        "peak_memory_mb",
        "index_elapsed_ms",
        "query_p50_ms",
        "query_p95_ms",
        "exact_top3",
        "semantic_top5",
        "fallback_ok",
        "package_versions",
        "thresholds",
    ]:
        assert key in dumped

    assert dumped["ok"] is True
    assert dumped["model_id"] == "fake/codi-search-benchmark"
    assert dumped["vector_dimension"] == 16
    assert dumped["batch_size"] == 4
    assert dumped["document_count"] >= 8
    assert dumped["query_count"] >= 6
    assert dumped["fallback_ok"] is True
    assert benchmark_summary_path().exists()
    assert read_benchmark_summary() == summary
    assert get_status(open_session_count=0).operations.benchmark == summary  # type: ignore[union-attr]

    serialized = benchmark_summary_path().read_text(encoding="utf-8")
    forbidden = [
        "Persistent shell survives attach mode",
        "src/codexbot/web/api.py",
        "Browser notifications alert",
    ]
    for text in forbidden:
        assert text not in serialized


def test_benchmark_cli_prints_json_and_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from codexbot.search.benchmark import main
    from codexbot.search.state import read_benchmark_summary

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    assert (
        main(
            [
                "--fixtures",
                str(FIXTURE),
                "--provider",
                "fake",
                "--batch-size",
                "4",
                "--write-summary",
            ]
        )
        == 0
    )
    body = json.loads(capsys.readouterr().out)

    assert body["ok"] is True
    assert body["provider"] == "fake"
    assert read_benchmark_summary() is not None


def test_pyproject_and_worker_expose_benchmark_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from codexbot.search.worker import main

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert (
        data["project"]["scripts"]["codexbot-search-benchmark"]
        == "codexbot.search.benchmark:main"
    )
    assert (
        main(
            [
                "benchmark",
                "--fixtures",
                str(FIXTURE),
                "--provider",
                "fake",
                "--batch-size",
                "4",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"] is True
