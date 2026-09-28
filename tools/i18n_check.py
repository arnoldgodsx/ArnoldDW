"""Check translation catalogs and list UI literals still awaiting migration."""

from __future__ import annotations

import argparse
import ast
import json
import re
import string
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "arnold_dw" / "i18n"
TURKISH = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
SENTENCE_END = re.compile(r"[.!?…]$")


def _catalog(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        raise ValueError(f"Catalog must be a JSON object of string values: {path}")
    return data


def catalog_issues() -> list[str]:
    catalogs = {code: _catalog(CATALOG_DIR / f"{code}.json") for code in ("tr", "en")}
    keys = {code: set(catalog) for code, catalog in catalogs.items()}
    issues: list[str] = []
    for source, target in (("tr", "en"), ("en", "tr")):
        for key in sorted(keys[source] - keys[target]):
            issues.append(f"{target}.json is missing key: {key}")
    for key in sorted(keys["tr"] & keys["en"]):
        params = {
            code: {name for _, name, _, _ in string.Formatter().parse(catalogs[code][key]) if name}
            for code in ("tr", "en")
        }
        if params["tr"] != params["en"]:
            issues.append(
                f"Placeholder mismatch for {key}: tr={sorted(params['tr'])}, en={sorted(params['en'])}"
            )
    return issues


def _inside_translation_call(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.Call) and isinstance(current.func, ast.Name) and current.func.id == "t":
            return True
    return False


def untranslated_literals() -> list[str]:
    findings: list[str] = []
    sources = [*(ROOT / "arnold_dw" / "ui").rglob("*.py"), ROOT / "arnold_dw" / "core" / "errors.py"]
    for path in sorted(sources):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.strip()
                if not value or _inside_translation_call(node, parents):
                    continue
                # User-facing widget/dialog arguments, returned error text, and Turkish literals
                # are useful migration candidates. Ignore docstrings and technical identifiers.
                parent = parents.get(node)
                user_argument = isinstance(parent, ast.keyword) and parent.arg in {
                    "text", "placeholder", "placeholder_text", "title", "label"
                }
                returned_error = path.name == "errors.py" and isinstance(parent, ast.Return)
                if TURKISH.search(value) or (
                    " " in value and SENTENCE_END.search(value)
                ) or ((user_argument or returned_error) and value.isupper()):
                    findings.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}: {value!r}")
            elif isinstance(node, ast.JoinedStr):
                # F-string static portions are the translatable pieces; dynamic values remain code.
                chunks = "".join(part.value for part in node.values if isinstance(part, ast.Constant))
                if chunks.strip() and TURKISH.search(chunks) and not _inside_translation_call(node, parents):
                    findings.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}: {chunks.strip()!r} (f-string)")
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit nonzero if catalogs or UI literals need work")
    parser.add_argument("--catalog-only", action="store_true", help="check catalogs without listing UI literals")
    args = parser.parse_args(argv)

    issues = catalog_issues()
    if issues:
        print("Catalog issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("Catalogs: keys and placeholders match.")

    literals = [] if args.catalog_only else untranslated_literals()
    if literals:
        print("\nUI literals to migrate through t() in Phase 3:")
        for literal in literals:
            print(f"  - {literal}")
    elif not args.catalog_only:
        print("No untranslated UI literals found.")
    return int(bool(issues or (args.strict and literals)))


if __name__ == "__main__":
    raise SystemExit(main())
