"""Parse a submitted config blob into (key, value) pairs.

Supports the four formats a Python/Django dev actually pastes: dotenv,
settings.py (simple top-level assignments), YAML, and JSON. Format is
auto-detected when not given. Values are returned raw here; masking happens one
layer up so this module stays a pure parser.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass


@dataclass
class ParsedKey:
    name: str
    value: str


# KEY=value, optional `export`, optional quotes, ignore comments/blank lines.
_DOTENV_LINE = re.compile(
    r"""^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$"""
)


def detect_format(text: str, filename: str = "") -> str:
    """Guess the config format from filename then content."""
    f = filename.lower()
    if f.endswith((".json",)):
        return "json"
    if f.endswith((".yaml", ".yml")):
        return "yaml"
    if f.endswith(".py"):
        return "python"
    if f.endswith(".env") or f.startswith(".env") or "/.env" in f:
        return "env"

    stripped = text.strip()
    if stripped.startswith("{"):
        return "json"
    # A python settings file tends to have UPPER = ... assignments + imports.
    if re.search(r"^\s*[A-Z_]+\s*=", text, re.MULTILINE) and (
        "import " in text or "= {" in text or "os.environ" in text
    ):
        return "python"
    if re.search(r"^\s*[A-Za-z_][\w.-]*\s*:\s*\S", text, re.MULTILINE) and "=" not in text.split("\n")[0]:
        return "yaml"
    return "env"


def _flatten(prefix: str, obj, out: list[ParsedKey]) -> None:
    """Flatten nested dicts to UPPER_SNAKE keys; stringify scalars."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}_{k}" if prefix else str(k)
            _flatten(key, v, out)
    elif isinstance(obj, (list, tuple)):
        out.append(ParsedKey(prefix, json.dumps(obj)))
    elif obj is None:
        out.append(ParsedKey(prefix, ""))
    else:
        out.append(ParsedKey(prefix, str(obj)))


def _parse_env(text: str) -> list[ParsedKey]:
    keys: list[ParsedKey] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _DOTENV_LINE.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        # Strip surrounding quotes and inline comments on unquoted values.
        if value and value[0] in "\"'" and value[-1:] == value[0]:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        keys.append(ParsedKey(name, value))
    return keys


def _parse_python(text: str) -> list[ParsedKey]:
    """Pull simple top-level NAME = <literal/str> assignments from a .py file.

    Uses AST so we never execute the file. Non-literal RHS (e.g. function calls
    like env('X')) are recorded with an empty value — their *name* still matters
    for the inventory and usage location.
    """
    keys: list[ParsedKey] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return keys
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if not name.isupper():
                continue
            try:
                value = ast.literal_eval(node.value)
                value = "" if value is None else str(value)
            except (ValueError, SyntaxError):
                value = ""
            keys.append(ParsedKey(name, value))
    return keys


def _parse_yaml(text: str) -> list[ParsedKey]:
    try:
        import yaml  # optional dependency
    except ImportError:
        # Minimal fallback: top-level "key: value" lines only.
        keys = []
        for line in text.splitlines():
            m = re.match(r"^([A-Za-z_][\w.-]*)\s*:\s*(.+)$", line)
            if m:
                keys.append(ParsedKey(m.group(1), m.group(2).strip().strip("\"'")))
        return keys
    data = yaml.safe_load(text) or {}
    out: list[ParsedKey] = []
    _flatten("", data, out)
    return out


def _parse_json(text: str) -> list[ParsedKey]:
    data = json.loads(text)
    out: list[ParsedKey] = []
    _flatten("", data, out)
    return out


def parse_config(text: str, fmt: str = "", filename: str = "") -> tuple[str, list[ParsedKey]]:
    """Parse config text; returns (detected_format, parsed_keys)."""
    fmt = fmt or detect_format(text, filename)
    parser = {
        "env": _parse_env,
        "python": _parse_python,
        "yaml": _parse_yaml,
        "json": _parse_json,
    }.get(fmt, _parse_env)
    keys = parser(text)
    # De-dupe by name, last write wins (mirrors how env files behave).
    deduped: dict[str, ParsedKey] = {}
    for k in keys:
        if k.name:
            deduped[k.name] = k
    return fmt, list(deduped.values())
