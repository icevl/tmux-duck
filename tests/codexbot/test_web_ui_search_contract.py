"""Static contract tests for the Web UI search flow.

The repo does not currently have a frontend unit/e2e runner. These tests keep
Phase 5's UI wiring covered by pytest until a browser-level harness exists.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"const {name} = useCallback\((.*?)\n  }}", source, re.S)
    assert match, f"{name} callback not found"
    return match.group(1)


def test_session_search_uses_bounded_backend_search_only() -> None:
    api_source = _read("web-ui/src/api.ts")
    search_source = _read("web-ui/src/components/SessionSearch.tsx")

    assert "getSearchStatus: () =>" in api_source
    assert "searchSessions:" in api_source
    assert 'method: "POST"' in api_source
    assert "json: searchRequest" in api_source

    assert "const MIN_QUERY_LENGTH = 2" in search_source
    assert "const DEFAULT_LIMIT = 10" in search_source
    assert "const DEFAULT_HITS_PER_SESSION = 3" in search_source
    assert "window.setTimeout" in search_source
    assert "setDebouncedQuery(trimmedQuery)" in search_source
    assert ".searchSessions({" in search_source
    assert "limit: DEFAULT_LIMIT" in search_source
    assert "hits_per_session: DEFAULT_HITS_PER_SESSION" in search_source
    assert "api.getMessages" not in search_source

    # Status polling/footer copy moved to Sidebar + SearchStatusFooter; only
    # the inline state-panel copy that SessionSearch still renders is asserted
    # here.
    for copy in [
        "Search open sessions",
        "Searching...",
        "No matches",
        "Try different terms or filters.",
        "Indexing",
        "Results may be incomplete.",
        "Degraded",
        "Semantic search is not ready. Showing lexical results.",
        "Search unavailable",
        "Keep working and try again after indexing recovers.",
    ]:
        assert copy in search_source

    degraded_start = search_source.index("showLexicalNotice")
    degraded_branch = search_source[
        degraded_start : search_source.index("response?.results.map", degraded_start)
    ]
    assert 'className="search-state-panel warn compact"' in degraded_branch
    assert "window.confirm" not in search_source
    assert "acknowledge" not in search_source.lower()


def test_session_search_routes_by_window_id_and_preserves_local_query() -> None:
    search_source = _read("web-ui/src/components/SessionSearch.tsx")

    for field in [
        "target_id: string",
        "window_id: string",
        "session_id: string | null",
        "transcript_offset: number | null",
        "transcript_index: number | null",
        "chunk_index: number | null",
        "source_order: number",
        "snippet: string",
    ]:
        assert field in search_source

    open_hit_start = search_source.index("const openHit = ")
    open_hit = search_source[
        open_hit_start : search_source.index("return (", open_hit_start)
    ]
    assert "result.routing.window_id" in open_hit
    assert "hit.provenance.transcript_offset" in open_hit
    assert "hit.provenance.transcript_index" in open_hit
    assert "hit.identity.chunk_index" in open_hit
    assert "hit.source_order" in open_hit
    assert "Date.now()" in open_hit
    assert "setQuery" not in open_hit
    assert "setResponse" not in open_hit

    assert "onClick={() => onOpenResult(result.routing.window_id)}" in search_source
    assert 'onClick={() => setQuery("")}' in search_source


def test_sidebar_search_keeps_session_ordering_and_pinned_list() -> None:
    sidebar_source = _read("web-ui/src/components/Sidebar.tsx")

    assert 'import { SessionSearch, type SearchHitTarget } from "./SessionSearch";' in (
        sidebar_source
    )
    assert "<SessionSearch" in sidebar_source
    assert "onHasActiveQueryChange={handleSearchActiveChange}" in sidebar_source
    assert "searchActive ? null : ordered.length === 0" in sidebar_source

    for existing_list_contract in [
        "ordered.map((s) =>",
        "const moveSession =",
        "void onReorder(next.map((session) => session.window_id))",
        "s.pinned",
        'className="pin-marker"',
    ]:
        assert existing_list_contract in sidebar_source


def test_app_and_chatview_search_hit_navigation_contract() -> None:
    app_source = _read("web-ui/src/App.tsx")
    chat_source = _read("web-ui/src/components/ChatView.tsx")

    open_hit = _function_body(app_source, "handleOpenSearchHit")
    assert "setActiveId(target.window_id)" in open_hit
    assert "setSearchTarget(target)" in open_hit
    assert "setSidebarOpen(false)" in open_hit
    assert "draftsRef" not in open_hit
    assert "textRef" not in open_hit
    assert "choicePageByKey" not in open_hit
    assert "choiceSendingKey" not in open_hit
    assert "Opened session. Exact hit is unavailable." in app_source
    assert "searchTarget={searchTarget}" in app_source
    assert "onSearchTargetFallback={handleSearchTargetFallback}" in app_source
    assert "onOpenSearchHit={handleOpenSearchHit}" in app_source

    assert "historyLoadedWindowRef.current !== session.window_id" in chat_source
    assert "handledSearchTargetRef.current === searchTarget.target_id" in chat_source
    assert "around_offset: offset" in chat_source
    assert "around_index: searchTarget.transcript_index ?? 0" in chat_source
    assert "limit: 120" in chat_source
    assert "showSearchHighlight(key)" in chat_source
    assert "Search hit" in chat_source
    assert ".messages-row.search-hit" not in chat_source

    assert "activeChoiceMessage" in chat_source
    assert "messages.filter((m) => m._clientId !== activeChoiceMessage._clientId)" in (
        chat_source
    )
    assert "{awaitingResponse && (" in chat_source
    assert "waiting-duck-row" in chat_source
    assert "{activeChoiceMessage && (" in chat_source
    assert "choiceDisabled={false}" in chat_source


def test_search_mobile_styles_and_highlight_contract() -> None:
    styles = _read("web-ui/src/styles.css")

    # `.search-details-toggle` was replaced by the bottom `.search-status-footer`
    # widget, which lives in SearchStatusFooter rather than inside the search
    # results panel. The remaining selectors are still load-bearing.
    for selector in [
        ".session-search",
        ".search-status-footer",
        ".search-status-details",
        ".search-detail-row",
        ".search-result-hit",
        ".messages-row.search-hit",
        ".search-hit-label",
    ]:
        assert selector in styles

    assert "overflow-wrap: anywhere" in styles
    assert "-webkit-line-clamp: 3" in styles

    mobile = styles[styles.index("@media (max-width: 760px)") :]
    assert ".session-search" in mobile
    assert ".session-search-input-wrap input" in mobile
    assert "font-size: 16px" in mobile
    assert ".search-status-details" in mobile
    assert ".search-filter-row" in mobile
    assert ".search-results" in mobile
    assert "max-height: calc(100dvh - 270px)" in mobile
    assert ".search-hit-snippet" in mobile
    assert "-webkit-line-clamp: 2" in mobile
