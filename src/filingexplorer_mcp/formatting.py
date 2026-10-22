"""Render API payloads as compact, YAML-like text.

The goal is a format that is cheap in tokens and easy for a model to read:
null and empty mapping values are dropped, short scalar lists stay on one line,
and multi-line strings use a literal block. Inside a list a null stays as
``null``: lists are often aligned to periods, and dropping an item would shift
every later value onto the wrong period.
"""

from __future__ import annotations

import json
import re
from typing import Any

_PLAIN = re.compile(r"^[A-Za-z0-9_./()%$@+\-][^:#\n]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~"}
_INLINE_LIST_MAX = 120


def _is_empty(value: Any) -> bool:
    if isinstance(value, list):
        return all(item is None for item in value)
    return value is None or value == "" or value == {}


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value) if value != int(value) or abs(value) >= 1e16 else str(int(value))
    text = str(value)
    if (
        _PLAIN.match(text)
        and text == text.strip()
        and text.lower() not in _RESERVED
        and not text.endswith(":")
    ):
        return text
    return json.dumps(text, ensure_ascii=False)


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (dict, list))


def _lines(value: Any, indent: int) -> list[str]:
    pad = "  " * indent
    out: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_empty(item):
                continue
            out.extend(_keyed(str(key), item, indent))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                body = _lines(item, indent + 1)
                if not body:
                    continue
                first = body[0].lstrip()
                out.append(f"{pad}- {first}")
                out.extend(body[1:])
            elif isinstance(item, list):
                out.append(f"{pad}-")
                out.extend(_lines(item, indent + 1))
            else:
                out.extend(_block_or_line(f"{pad}- ", item, indent + 1))
    else:
        out.extend(_block_or_line(pad, value, indent))
    return out


def _block_or_line(prefix: str, value: Any, indent: int) -> list[str]:
    if isinstance(value, str) and "\n" in value:
        pad = "  " * indent
        return [f"{prefix}|"] + [f"{pad}{line}" if line else "" for line in value.split("\n")]
    return [f"{prefix}{_scalar(value)}"]


def _keyed(key: str, item: Any, indent: int) -> list[str]:
    pad = "  " * indent
    label = _scalar(key)
    if isinstance(item, list) and all(_is_scalar(v) for v in item):
        rendered = ", ".join(_scalar(v) for v in item)
        if len(rendered) <= _INLINE_LIST_MAX and not any(
            isinstance(v, str) and "\n" in v for v in item
        ):
            return [f"{pad}{label}: [{rendered}]"]
    if isinstance(item, (dict, list)):
        body = _lines(item, indent + 1)
        return [f"{pad}{label}:"] + body if body else []
    return _block_or_line(f"{pad}{label}: ", item, indent + 1)


def to_text(value: Any) -> str:
    """Render ``value`` as compact YAML-like text."""
    if _is_empty(value):
        return "(no data)"
    return "\n".join(_lines(value, 0))


def page_note(total: int | None, offset: int, returned: int, has_more: bool | None) -> str:
    """One-line pagination footer, or an empty string when everything was returned."""
    more = has_more if has_more is not None else (total is not None and offset + returned < total)
    if not more:
        return ""
    total_part = f" of {total}" if total is not None else ""
    return (
        f"\n\n[showing {offset + 1}-{offset + returned}{total_part}; "
        f"call again with offset={offset + returned} for more]"
    )


def slice_text(text: str, offset: int, max_chars: int) -> str:
    """Return one window of a long text with a header describing the window."""
    total = len(text)
    offset = max(0, offset)
    chunk = text[offset : offset + max_chars]
    end = offset + len(chunk)
    if offset == 0 and end >= total:
        return chunk
    note = f"[characters {offset}-{end} of {total}"
    note += f"; call again with offset={end} for more]" if end < total else "; end of text]"
    return f"{note}\n\n{chunk}"
