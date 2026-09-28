"""Engine update + activation inside a real PyInstaller build.

Builds a small ``--onedir`` exe that bundles an OLDER yt-dlp (2026.7.4), then - from inside
the exe - checks PyPI, installs the latest yt-dlp into a scratch APPDATA, restarts, and
verifies that the new engine is the one imported and that it extracts a YouTube video.
Also shows what a plain ``sys.path.insert`` does and that a broken engine is rolled back.

Slow (PyInstaller build, ~2-4 min) and needs internet, so it only runs with
``--network`` and ``ARNOLD_DW_FROZEN_TEST=1``.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_YTDLP = "2026.7.4"

HARNESS = textwrap.dedent('''
    import glob, json, logging, os, sys

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    mode = sys.argv[1]
    root = os.path.join(os.environ["APPDATA"], "Arnold DW", "engine", "yt-dlp")
    out = {"mode": mode, "frozen": bool(getattr(sys, "frozen", False))}

    if mode == "naive":
        engine = max(d for d in glob.glob(os.path.join(root, "2*")) if os.path.isdir(d))
        sys.path.insert(0, engine)
        import yt_dlp
        import yt_dlp.version
        out.update(version=yt_dlp.version.__version__, file=yt_dlp.__file__, engine=engine)
    else:
        from arnold_dw.core.runtime import binaries, selectors, ytdlp_updater

        out["bundled"] = ytdlp_updater.detect_bundled_version()
        if mode == "install":
            info = ytdlp_updater.check_for_update()
            out["offered"] = info.version if info else None
            if info:
                out["installed"] = ytdlp_updater.download_and_install(info)
        else:
            out["active"] = ytdlp_updater.activate()
            import yt_dlp

            manager = ytdlp_updater.default_manager()
            out.update(file=yt_dlp.__file__, source=manager.engine_source(),
                       meta_path=[type(f).__name__ for f in sys.meta_path], state=manager._load_state())
            import yt_dlp_ejs
            out["ejs_file"] = yt_dlp_ejs.__file__
            if mode == "extract":
                opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                        "format": selectors.video_selector(), **binaries.ytdlp_runtime_options()}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info("https://www.youtube.com/watch?v=jNQXAC9IVRw", download=False)
                out["formats"] = [[f["format_id"], f.get("vcodec"), f.get("acodec")]
                                  for f in info.get("requested_formats") or [info]]
                runtime = binaries.find_js_runtime()
                out["js_runtime"] = runtime.name if runtime else None
    print("RESULT " + json.dumps(out))
''')


@pytest.fixture(scope="module")
def frozen_exe(tmp_path_factory):
    if os.environ.get("ARNOLD_DW_FROZEN_TEST") != "1":
        pytest.skip("set ARNOLD_DW_FROZEN_TEST=1 to build and test a frozen exe")
    work = tmp_path_factory.mktemp("frozen")
    old = work / "old"
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--target", str(old),
                    f"yt-dlp=={OLD_YTDLP}"], check=True)
    harness = work / "harness.py"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--console", "--log-level", "WARN",
         "--name", "harness", "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
         "--specpath", str(work), "--paths", str(old), "--paths", REPO_ROOT,
         "--collect-submodules", "yt_dlp", str(harness)],
        check=True,
    )
    exe = work / "dist" / "harness" / "harness.exe"
    assert exe.is_file()
    appdata = work / "appdata"
    appdata.mkdir()
    return exe, appdata


def run_exe(frozen_exe, mode):
    exe, appdata = frozen_exe
    env = {**os.environ, "APPDATA": str(appdata)}
    proc = subprocess.run([str(exe), mode], capture_output=True, text=True, env=env, timeout=600)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    assert proc.returncode == 0 and lines, proc.stdout + proc.stderr
    result = json.loads(lines[-1][len("RESULT "):])
    print(mode, json.dumps(result, indent=1))
    return result


def engine_root(frozen_exe):
    return os.path.join(str(frozen_exe[1]), "Arnold DW", "engine", "yt-dlp")


@pytest.mark.network
def test_frozen_update_cycle(frozen_exe):
    from arnold_dw.core.runtime.versioning import is_newer, same_version

    before = run_exe(frozen_exe, "activate")
    assert before["frozen"] is True
    assert same_version(before["bundled"], OLD_YTDLP)
    assert before["source"] == "bundled" and same_version(before["active"], OLD_YTDLP)

    installed = run_exe(frozen_exe, "install")
    assert installed["offered"] and is_newer(installed["offered"], OLD_YTDLP)
    new_version = installed["installed"]

    after = run_exe(frozen_exe, "extract")
    root = engine_root(frozen_exe)
    assert after["source"] == "engine"
    assert same_version(after["active"], new_version)
    assert after["file"].startswith(os.path.join(root, new_version))
    assert after["ejs_file"].startswith(os.path.join(root, new_version))
    # Once imported, yt-dlp puts its own PluginFinders (yt_dlp_plugins.* only) in front;
    # every other finder, including PyInstaller's, comes after ours.
    finders = after["meta_path"]
    assert set(finders[:finders.index("EngineFinder")]) <= {"PluginFinder"}, finders
    assert after["formats"], after
    assert all(v.startswith("avc1") for _, v, a in after["formats"] if v and v != "none")

    naive = run_exe(frozen_exe, "naive")  # documents plain sys.path behaviour on this PyInstaller
    print("plain sys.path.insert loaded:", naive["version"], naive["file"])


@pytest.mark.network
def test_frozen_broken_engine_rolls_back(frozen_exe):
    root = engine_root(frozen_exe)
    versions = [d for d in os.listdir(root) if d[0].isdigit()]
    assert versions, "run after test_frozen_update_cycle"
    init = os.path.join(root, versions[0], "yt_dlp", "__init__.py")
    with open(init, "a", encoding="utf-8") as fh:
        fh.write("\nraise ImportError('simulated incompatible engine')\n")

    result = run_exe(frozen_exe, "activate")
    assert result["source"] == "bundled"
    assert "engine" not in result["file"]
    assert result["state"]["active"] is None
    assert "simulated incompatible engine" in result["state"]["broken"][versions[0]]
