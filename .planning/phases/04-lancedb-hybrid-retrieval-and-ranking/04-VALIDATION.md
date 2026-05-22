---
phase: 04
slug: lancedb-hybrid-retrieval-and-ranking
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
---

# Phase 04 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-asyncio |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_index.py tests/codexbot/test_search_retrieval.py -q` |
| **Full suite command** | `/tmp/codexbot-venv/bin/pytest -q` |
| **Estimated runtime** | ~60-240 seconds for full suite; model smoke may be slower on first download |

---

## Sampling Rate

- **After every task commit:** Run the plan's targeted `uv run pytest ... -q`
  command.
- **After every plan wave:** Run all Phase 4 targeted tests:
  `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_index.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_web_api.py -q`
- **Before `$gsd-verify-work`:** Run
  `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && /tmp/codexbot-venv/bin/pytest -q`
- **Local model smoke before readiness:** Run the Phase 4 smoke command added
  by the plans, using local model/cache settings, and capture vector dimension,
  elapsed time, and degraded error output if the model is unavailable.
- **Max feedback latency:** 240 seconds for targeted lanes excluding first-time
  model download; full suite may take longer on constrained local machines.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | SRCH-04, SRCH-05, SRCH-06, RETR-06, RETR-07 | T-04-01 / T-04-02 | API contracts expose bounded results, filters, labels, and highlights without raw backend score leakage | unit | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_web_api.py -q` | yes | pending |
| 04-01-02 | 01 | 1 | RETR-01, RETR-06, RETR-07, OPS-01 | T-04-01 / T-04-03 | Lexical/degraded ranking handles exact technical text and request paths stay free of heavy imports | unit | `uv run pytest tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_contracts.py -q` | yes | pending |
| 04-02-01 | 02 | 2 | RETR-02, RETR-04, RETR-05, OPS-01 | T-04-04 / T-04-05 | LanceDB/Qwen provider lazy-loads locally and never sends transcript text to cloud services | unit/integration | `uv run pytest tests/codexbot/test_search_index.py tests/codexbot/test_search_worker.py -q` | yes | pending |
| 04-02-02 | 02 | 2 | SRCH-02, RETR-02, RETR-04, RETR-05 | T-04-04 / T-04-06 | Initial backfill and live flush idempotently materialize chunk rows into generation-owned LanceDB state | unit/integration | `uv run pytest tests/codexbot/test_search_index.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_worker.py -q` | yes | pending |
| 04-03-01 | 03 | 3 | SRCH-02, SRCH-04, SRCH-05, SRCH-06, RETR-01, RETR-02, RETR-03, RETR-06, RETR-07 | T-04-02 / T-04-07 | Hybrid query ranks open sessions exact-first, groups by window ID, filters metadata, and hides stale sources | unit/integration | `uv run pytest tests/codexbot/test_search_retrieval.py tests/codexbot/test_web_api.py -q` | yes | pending |
| 04-03-02 | 03 | 3 | RETR-04, RETR-05, RETR-08, OPS-01 | T-04-05 / T-04-08 | Ranking fixtures and local smoke validate model/index readiness or explicit degraded behavior | unit/smoke | `uv run pytest tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_index.py -q` | yes | pending |

---

## Wave 0 Requirements

Existing pytest infrastructure covers Phase 4. Add focused modules during
Plan 01 and Plan 02:

- [ ] `tests/codexbot/test_search_retrieval.py` - lexical, hybrid ranking,
  filters, snippets, labels, degraded responses, and fixture coverage.
- [ ] `tests/codexbot/test_search_index.py` - LanceDB table materialization,
  row upserts, embedding provider boundaries, and model smoke hooks.

---

## Manual-Only Verifications

All Phase 4 product behaviors should have automated tests. Manual Web UI smoke
is deferred to Phase 5 because this phase does not add browser search UX.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands or existing Wave 0 coverage
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency target defined
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
