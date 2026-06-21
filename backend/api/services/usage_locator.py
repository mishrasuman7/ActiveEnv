"""Locate where each config key is used in the submitted codebase.

This is the *bounded retrieval* layer: instead of feeding a whole repo to the
LLM, we find the exact lines that reference each key and capture only the
surrounding function (or a small line window). That keeps Phase 2 intent
inference grounded and within context limits no matter how big the repo is.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

# Files we bother scanning for usage. Python first (v1 target), plus the common
# companions where config tends to be referenced.
_CODE_EXTS = (".py", ".cfg", ".ini", ".toml", ".yaml", ".yml", ".env", ".sh", ".txt")
_MAX_SNIPPET_LINES = 30
_WINDOW = 4  # lines of context each side when no enclosing function is found


@dataclass
class UsageHit:
    file_path: str
    line_number: int
    usage_kind: str
    snippet: str


def _usage_kind(line: str) -> str:
    l = line
    if "os.environ" in l or "getenv" in l:
        return "os.environ"
    if "settings." in l:
        return "settings"
    if re.search(r"\b(env|config|Env|Config)\s*\(", l):
        return "env-helper"
    if "=" in l.split("#", 1)[0]:
        return "assignment"
    return "reference"


def _function_ranges(text: str) -> list[tuple[int, int, str]]:
    """Return (start_line, end_line, name) for every def in a Python file."""
    ranges: list[tuple[int, int, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ranges
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start) or start
            ranges.append((start, end, node.name))
    return ranges


def _enclosing_snippet(lines: list[str], line_no: int, fn_ranges) -> str:
    """The enclosing function source, or a small window, bounded in size."""
    for start, end, _name in fn_ranges:
        if start <= line_no <= end:
            if end - start + 1 > _MAX_SNIPPET_LINES:
                # Huge function: window around the hit instead of the whole thing.
                break
            return "\n".join(lines[start - 1 : end])
    lo = max(0, line_no - 1 - _WINDOW)
    hi = min(len(lines), line_no + _WINDOW)
    return "\n".join(lines[lo:hi])


def _key_pattern(key: str) -> re.Pattern:
    """Match a key as a quoted literal, an attribute (.KEY), or a bare word.

    The bare-word case forbids a leading word char or dot so a longer name like
    OLD_DATABASE_URL never matches DATABASE_URL, while `settings.DATABASE_URL`
    still matches via the explicit attribute alternative.
    """
    k = re.escape(key)
    return re.compile(rf"""(['"]{k}['"]|\.{k}\b|(?<![\w.]){k}\b)""")


def locate_usages(
    files: dict[str, str], key_names: list[str]
) -> dict[str, list[UsageHit]]:
    """Map each key name to the list of places it is referenced.

    `files` is {relative_path: file_text}. Returns {key_name: [UsageHit, ...]}.
    """
    patterns = {k: _key_pattern(k) for k in key_names}
    results: dict[str, list[UsageHit]] = {k: [] for k in key_names}

    for path, text in files.items():
        if not path.lower().endswith(_CODE_EXTS):
            continue
        lines = text.splitlines()
        fn_ranges = _function_ranges(text) if path.lower().endswith(".py") else []

        for i, line in enumerate(lines, start=1):
            # Cheap pre-filter: only test keys whose name appears on the line.
            for key in key_names:
                if key not in line:
                    continue
                if not patterns[key].search(line):
                    continue
                results[key].append(
                    UsageHit(
                        file_path=path,
                        line_number=i,
                        usage_kind=_usage_kind(line),
                        snippet=_enclosing_snippet(lines, i, fn_ranges),
                    )
                )
    return results
