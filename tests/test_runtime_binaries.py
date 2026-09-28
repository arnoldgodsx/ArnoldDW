import os
import subprocess
import sys

import pytest

from arnold_dw.core.runtime import _env, binaries


@pytest.fixture(autouse=True)
def _fresh_cache():
    binaries.refresh()
    yield
    binaries.refresh()


@pytest.fixture
def fake_tools(tmp_path, monkeypatch):
    """Isolated bin/ + PATH directories and a fake ``subprocess.run`` reporting versions."""
    bin_dir = tmp_path / "bundle" / "bin"
    path_dir = tmp_path / "path"
    bin_dir.mkdir(parents=True)
    path_dir.mkdir()
    versions: dict[str, str] = {}

    def add(where, name, output):
        target = (bin_dir if where == "bundled" else path_dir) / _env.exe_name(name)
        target.write_bytes(b"")
        versions[os.path.normcase(str(target))] = output
        return str(target)

    def which(name):
        candidate = path_dir / _env.exe_name(name)
        return str(candidate) if candidate.exists() else None

    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        output = versions.get(os.path.normcase(cmd[0]))
        if output is None:
            raise FileNotFoundError(cmd[0])
        return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")

    monkeypatch.setattr(_env, "bin_dir", lambda: str(bin_dir))
    monkeypatch.setattr(binaries.shutil, "which", which)
    monkeypatch.setattr(binaries.subprocess, "run", run)
    add.calls = calls
    return add


DENO_OUT = "deno 2.9.7 (stable, release, x86_64-pc-windows-msvc)\nv8 15.0\ntypescript 6.0.3\n"


def test_ffmpeg_prefers_bundled(fake_tools):
    bundled = fake_tools("bundled", "ffmpeg", "ffmpeg version 7.1-essentials_build Copyright")
    fake_tools("system", "ffmpeg", "ffmpeg version 9.0 Copyright")
    assert binaries.ffmpeg_path() == bundled
    assert binaries.ffmpeg_version() == "7.1-essentials_build"


def test_ffmpeg_falls_back_to_path(fake_tools):
    system = fake_tools("system", "ffmpeg", "ffmpeg version 9.0-full_build Copyright")
    assert binaries.ffmpeg_path() == system
    assert binaries.ffmpeg_version() == "9.0-full_build"


def test_ffmpeg_missing(fake_tools):
    assert binaries.ffmpeg_path() is None
    assert binaries.ffmpeg_version() is None
    assert "ffmpeg_location" not in binaries.ytdlp_runtime_options()


def test_bundled_deno_beats_system_runtimes(fake_tools):
    deno = fake_tools("bundled", "deno", DENO_OUT)
    fake_tools("system", "node", "v24.19.0\n")
    runtime = binaries.find_js_runtime()
    assert runtime == binaries.JsRuntime("deno", deno, "2.9.7", bundled=True)


def test_system_priority_is_deno_node_bun(fake_tools):
    fake_tools("system", "bun", "1.2.20\n")
    node = fake_tools("system", "node", "v24.19.0\n")
    runtime = binaries.find_js_runtime()
    assert (runtime.name, runtime.path, runtime.bundled) == ("node", node, False)


def test_too_old_runtime_is_skipped(fake_tools):
    fake_tools("system", "deno", "deno 2.1.4 (stable)\n")
    fake_tools("system", "node", "v20.11.1\n")
    bun = fake_tools("system", "bun", "1.2.11\n")
    runtime = binaries.find_js_runtime()
    assert (runtime.name, runtime.path, runtime.version) == ("bun", bun, "1.2.11")


def test_unrunnable_runtime_is_skipped(fake_tools, monkeypatch):
    fake_tools("system", "deno", "garbage output")
    assert binaries.find_js_runtime() is None


def test_runtime_options_wire_everything(fake_tools):
    ffmpeg = fake_tools("bundled", "ffmpeg", "ffmpeg version 7.1")
    deno = fake_tools("bundled", "deno", DENO_OUT)
    opts = binaries.ytdlp_runtime_options()
    assert opts == {
        "remote_components": ["ejs:github"],
        "ffmpeg_location": ffmpeg,
        "js_runtimes": {"deno": {"path": deno}},
    }


def test_runtime_options_without_js_runtime(fake_tools):
    opts = binaries.ytdlp_runtime_options()
    assert "js_runtimes" not in opts  # yt-dlp keeps its own default, logs its own warning
    assert opts["remote_components"] == ["ejs:github"]


def test_probes_hide_console_window(fake_tools):
    fake_tools("bundled", "deno", DENO_OUT)
    binaries.find_js_runtime()
    (cmd, kwargs), = fake_tools.calls
    assert cmd[1:] == ["--version"]
    assert kwargs["timeout"] > 0
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_results_are_cached_until_refresh(fake_tools):
    fake_tools("system", "node", "v24.19.0\n")
    binaries.find_js_runtime()
    binaries.find_js_runtime()
    assert len(fake_tools.calls) == 1
    binaries.refresh()
    binaries.find_js_runtime()
    assert len(fake_tools.calls) == 2


def test_min_versions_do_not_import_yt_dlp(monkeypatch):
    monkeypatch.delitem(sys.modules, "yt_dlp", raising=False)
    assert binaries.js_runtime_min_versions() == binaries.JS_RUNTIME_MIN_VERSIONS
    assert "yt_dlp" not in sys.modules


def test_min_versions_follow_loaded_yt_dlp():
    import yt_dlp  # noqa: F401
    from yt_dlp.utils import _jsruntime

    minimums = binaries.js_runtime_min_versions()
    assert minimums["deno"] == _jsruntime.DenoJsRuntime.MIN_SUPPORTED_VERSION
    assert minimums["node"] == _jsruntime.NodeJsRuntime.MIN_SUPPORTED_VERSION


def test_our_minimum_table_matches_installed_yt_dlp():
    from yt_dlp.utils import _jsruntime

    assert binaries.JS_RUNTIME_MIN_VERSIONS == {
        "deno": _jsruntime.DenoJsRuntime.MIN_SUPPORTED_VERSION,
        "node": _jsruntime.NodeJsRuntime.MIN_SUPPORTED_VERSION,
        "bun": _jsruntime.BunJsRuntime.MIN_SUPPORTED_VERSION,
    }


def test_options_are_accepted_by_yt_dlp(fake_tools):
    import yt_dlp

    fake_tools("bundled", "deno", DENO_OUT)
    opts = binaries.ytdlp_runtime_options()
    with yt_dlp.YoutubeDL({"quiet": True, **opts}) as ydl:
        assert ydl.params["js_runtimes"] == opts["js_runtimes"]
        assert ydl.params["remote_components"] == {"ejs:github"}


def test_real_environment_discovery():
    """Smoke test against this machine: must not raise, results must be consistent."""
    path = binaries.ffmpeg_path()
    if path:
        assert os.path.isfile(path)
        assert binaries.ffmpeg_version()
    runtime = binaries.find_js_runtime()
    if runtime:
        assert os.path.isfile(runtime.path)
        assert runtime.name in binaries.JS_RUNTIME_PRIORITY


def test_ffprobe_next_to_ffmpeg(fake_tools):
    ffmpeg = fake_tools("bundled", "ffmpeg", "ffmpeg version 7.1")
    assert binaries.ffprobe_path() is None
    probe = os.path.join(os.path.dirname(ffmpeg), _env.exe_name("ffprobe"))
    open(probe, "wb").close()
    binaries.refresh()
    assert binaries.ffprobe_path() == probe


def test_ffprobe_on_path_elsewhere_is_not_used(fake_tools):
    fake_tools("bundled", "ffmpeg", "ffmpeg version 7.1")
    fake_tools("system", "ffprobe", "ffprobe version 9.0")  # yt-dlp would not look there
    assert binaries.ffprobe_path() is None


def test_ffprobe_without_ffmpeg(fake_tools):
    assert binaries.ffprobe_path() is None
