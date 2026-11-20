"""Gooclaim: a member's words never reach a log (fork rule 8 — no query, passage or file content).

Found live on dev 2026-11-20: every instant search logged the member's question in full
("Instant search started … query='Is there any limit on room rent in my policy?'"), as did
classic search, federated search and Slack's search; Vespa's error text (which can quote
the query) was logged on a failure; and every API-key request logged the key creator's
email. A question can carry a diagnosis or a name — it is PHI.

This reads the code: no logging call in the search path may format a query, a passage or
a person's email into its message. Its length is fine — `len(...)` says how long, not what.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/airweave
SCOPE = [
    ROOT / "domains" / "search",
    ROOT / "api",
    ROOT / "adapters" / "llm",
    ROOT / "adapters" / "reranker",
    ROOT / "platform" / "sources" / "slack.py",
]
_LEVELS = {"debug", "info", "warning", "error", "exception", "critical"}
#: Names that hold a member's words or a person's email, wherever they are formatted.
_FORBIDDEN = {"query", "primary", "textual_representation", "snippet", "created_by_email"}


def _files() -> list[Path]:
    out: list[Path] = []
    for item in SCOPE:
        paths = [item] if item.is_file() else sorted(item.rglob("*.py"))
        out += [p for p in paths if "tests" not in p.parts]
    return out


def _names_in(node: ast.AST) -> set[str]:
    return {
        sub.id if isinstance(sub, ast.Name) else sub.attr
        for sub in ast.walk(node)
        if isinstance(sub, (ast.Name, ast.Attribute))
    }


def _leaking_lines(source: str) -> list[int]:
    """Lines of logging calls that format a forbidden name (not inside `len(...)`)."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LEVELS
            and "log" in ast.unparse(node.func.value).lower()
        ):
            continue
        formatted = [v for a in node.args for v in ast.walk(a) if isinstance(v, ast.FormattedValue)]
        for value in formatted:
            inner = value.value
            only_length = isinstance(inner, ast.Call) and ast.unparse(inner.func) == "len"
            if _names_in(inner) & _FORBIDDEN and not only_length:
                lines.append(node.lineno)
    return lines


def test_no_log_line_in_the_search_path_carries_a_members_words_or_an_email() -> None:
    files = _files()
    assert files, "the scanned folders moved — update SCOPE"
    leaks = [
        f"{path.relative_to(ROOT)}:{line}"
        for path in files
        for line in _leaking_lines(path.read_text(encoding="utf-8"))
    ]
    assert leaks == []


def test_the_guard_catches_the_line_that_leaked_and_not_its_replacement() -> None:
    source = (
        'ctx.logger.info(f"Instant search started collection={readable_id} '
        'query={request.query!r}")\n'
        'ctx.logger.info(f"Instant search started query_chars={len(request.query)}")\n'
        'audit_logger.info(f"API key usage: created_by={api_key_obj.created_by_email}")\n'
    )
    assert _leaking_lines(source) == [1, 3]
