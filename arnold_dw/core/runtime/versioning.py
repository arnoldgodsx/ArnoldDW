"""Small, dependency-free version helpers.

``packaging`` is not guaranteed to be present in the frozen app, and the versions we deal
with (yt-dlp calendar versions, ``deno 2.9.7``, ``v24.1.0``) only need numeric comparison.
"""

from __future__ import annotations

import re
import sys

_LEADING_NUMERIC = re.compile(r"\s*v?(\d+(?:\.\d+)*)")
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;,]+)")
_SPECIFIER = re.compile(r"^\s*(~=|==|!=|<=|>=|<|>)\s*([0-9][0-9.]*)(\.\*)?\s*$")


def parse_version(text: str | None) -> tuple[int, ...] | None:
    """Numeric prefix of a version string as a tuple, trailing zeros dropped.

    ``"2026.08.19"`` and ``"2026.8.19"`` -> ``(2026, 8, 19)``; ``"v2.9.7"`` -> ``(2, 9, 7)``;
    ``"2026.9.16.232951.dev0"`` -> ``(2026, 9, 16, 232951)``; unparsable -> ``None``.
    """
    if not text:
        return None
    match = _LEADING_NUMERIC.match(str(text))
    if not match:
        return None
    parts = [int(p) for p in match.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(candidate: str | None, baseline: str | None) -> bool:
    """True when ``candidate`` is strictly newer than ``baseline``.

    An unknown baseline counts as older than any parsable candidate; an unparsable
    candidate is never newer.
    """
    cand = parse_version(candidate)
    if cand is None:
        return False
    base = parse_version(baseline)
    if base is None:
        return True
    return cand > base


def same_version(a: str | None, b: str | None) -> bool:
    pa, pb = parse_version(a), parse_version(b)
    return pa is not None and pa == pb


def meets_minimum(version: str | None, minimum: tuple[int, ...]) -> bool:
    parsed = parse_version(version)
    return parsed is not None and parsed >= _trim(minimum)


def _trim(parts: tuple[int, ...]) -> tuple[int, ...]:
    parts = list(parts)
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def python_satisfies(requires_python: str | None, version_info=None) -> bool:
    """Evaluate a PEP 440 ``Requires-Python`` string such as ``">=3.10"`` or ``">=3.9,<4"``.

    Unknown specifier syntax is treated as satisfied (PyPI metadata is advisory here; a
    genuinely incompatible engine is caught later when it fails to byte-compile/import).
    """
    if not requires_python:
        return True
    vi = version_info or sys.version_info
    current = (vi[0], vi[1], vi[2])
    for raw in requires_python.split(","):
        if not raw.strip():
            continue
        match = _SPECIFIER.match(raw)
        if not match:
            continue
        op, number, wildcard = match.groups()
        wanted = tuple(int(p) for p in number.rstrip(".").split("."))
        if wildcard:
            prefix_equal = current[: len(wanted)] == wanted
            ok = prefix_equal if op == "==" else not prefix_equal if op == "!=" else True
        else:
            padded = (wanted + (0, 0, 0))[:3]
            if op == "~=":
                prefix = wanted[:-1] or wanted
                ok = current >= padded and current[: len(prefix)] == prefix
            else:
                ok = {
                    "==": current == padded,
                    "!=": current != padded,
                    ">=": current >= padded,
                    "<=": current <= padded,
                    ">": current > padded,
                    "<": current < padded,
                }[op]
        if not ok:
            return False
    return True


def _normalize_project(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned_requirement(requires_dist: list[str] | None, project: str) -> str | None:
    """Exact version pinned for ``project`` in a ``Requires-Dist`` list (``name==X; extra == ...``)."""
    wanted = _normalize_project(project)
    for entry in requires_dist or ():
        match = _REQ_NAME.match(entry)
        if match and _normalize_project(match.group(1)) == wanted:
            return match.group(2)
    return None
