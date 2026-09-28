"""The engine (arnold_dw.core) must never pull in tkinter/customtkinter."""

import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = textwrap.dedent("""
    import importlib, pkgutil, sys

    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in ("tkinter", "_tkinter", "customtkinter"):
                raise ImportError(f"UI module imported from core: {name}")
            return None

    sys.meta_path.insert(0, Blocker())

    import arnold_dw.core
    imported = []
    for mod in pkgutil.walk_packages(arnold_dw.core.__path__, "arnold_dw.core."):
        importlib.import_module(mod.name)
        imported.append(mod.name)
    for name in ("arnold_dw", "arnold_dw.paths", "arnold_dw.config", "arnold_dw.log"):
        importlib.import_module(name)
    leaked = [m for m in sys.modules if m.split(".")[0] in ("tkinter", "_tkinter", "customtkinter")]
    assert not leaked, leaked
    print("\\n".join(imported))
""")


def test_core_modules_import_without_tkinter():
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    imported = set(result.stdout.split())
    for name in ("formats", "errors", "filenames", "text", "http", "youtube", "instagram"):
        assert f"arnold_dw.core.{name}" in imported
