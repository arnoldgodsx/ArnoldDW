import hashlib
import io
import json
import os
import subprocess
import sys
import textwrap
import threading
import zipfile

import pytest
import requests

from arnold_dw.core.runtime import ytdlp_updater as up

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GOOD_INIT = '''\
from .version import __version__


class YoutubeDL:
    def __init__(self, params=None):
        self.params = params or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_info_extractor(self, key):
        return key
'''
BROKEN_INIT = "raise ImportError('engine needs a module this app does not ship')\n"


def make_wheel(version, init=GOOD_INIT, with_ejs_module=False, extra_members=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("yt_dlp/__init__.py", init)
        zf.writestr("yt_dlp/version.py", f"__version__ = '{version}'\nRELEASE_GIT_HEAD = 'x'\n")
        zf.writestr("yt_dlp/utils/__init__.py", "")
        zf.writestr("yt_dlp/utils/helper.py", "VALUE = 42\n")
        zf.writestr(f"yt_dlp-{version}.dist-info/METADATA", f"Name: yt-dlp\nVersion: {version}\n")
        zf.writestr(f"yt_dlp-{version}.data/scripts/yt-dlp", "#!python\n")
        if with_ejs_module:
            zf.writestr("yt_dlp_ejs/__init__.py", "version = '0.8.0'\n")
        for name, data in (extra_members or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def make_ejs_wheel(version="0.8.0"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("yt_dlp_ejs/__init__.py", f"version = '{version}'\n")
        zf.writestr("yt_dlp_ejs/yt/solver/core.min.js", "/* solver */\n")
        zf.writestr(f"yt_dlp_ejs-{version}.dist-info/METADATA", f"Name: yt-dlp-ejs\nVersion: {version}\n")
    return buf.getvalue()


def wheel_entry(project, version, data, *, sha256=None, size=None, yanked=False):
    filename = f"{project.replace('-', '_')}-{version}-py3-none-any.whl"
    return {
        "filename": filename,
        "packagetype": "bdist_wheel",
        "url": f"https://files.example/{filename}",
        "digests": {"sha256": sha256 or hashlib.sha256(data).hexdigest()},
        "size": len(data) if size is None else size,
        "yanked": yanked,
    }


class FakeResponse:
    def __init__(self, payload=None, content=None, status=200):
        self._payload = payload
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_content(self, chunk_size):
        for i in range(0, len(self.content), 7):  # tiny chunks: exercise progress + cancel
            yield self.content[i:i + 7]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakePyPI:
    """Serves the PyPI JSON API and wheel downloads from memory."""

    def __init__(self):
        self.json = {}
        self.files = {}
        self.requests = []

    def add_release(self, version, *, latest=True, requires_python=">=3.10", ejs="0.8.0",
                    wheel=None, entry_overrides=None):
        data = wheel if wheel is not None else make_wheel(version)
        entry = wheel_entry("yt-dlp", version, data, **(entry_overrides or {}))
        self.files[entry["url"]] = data
        requires = [f'yt-dlp-ejs=={ejs}; extra == "default"'] if ejs else []
        release = {
            "info": {"version": version, "requires_python": requires_python, "requires_dist": requires},
            "urls": [entry, {"filename": f"yt_dlp-{version}.tar.gz", "packagetype": "sdist",
                             "url": "https://files.example/sdist", "digests": {"sha256": "0"}}],
        }
        self.json[f"https://pypi.org/pypi/yt-dlp/{version}/json"] = release
        project = self.json.setdefault("https://pypi.org/pypi/yt-dlp/json", {"info": {}, "releases": {}, "urls": []})
        project["releases"][version] = release["urls"]
        if latest:
            project["info"] = release["info"]
            project["urls"] = release["urls"]
        if ejs and f"https://pypi.org/pypi/yt-dlp-ejs/{ejs}/json" not in self.json:
            ejs_data = make_ejs_wheel(ejs)
            ejs_entry = wheel_entry("yt-dlp-ejs", ejs, ejs_data)
            self.files[ejs_entry["url"]] = ejs_data
            self.json[f"https://pypi.org/pypi/yt-dlp-ejs/{ejs}/json"] = {
                "info": {"version": ejs, "requires_dist": []}, "urls": [ejs_entry]}
        return release

    def get(self, url, timeout=None, stream=False):
        self.requests.append(url)
        if url in self.json:
            return FakeResponse(payload=self.json[url])
        if url in self.files:
            return FakeResponse(content=self.files[url])
        return FakeResponse(status=404)


@pytest.fixture
def pypi():
    return FakePyPI()


@pytest.fixture
def manager(tmp_path, pypi):
    return up.EngineManager(tmp_path / "engine", session=pypi, bundled_version="2026.08.19")


def state_of(manager):
    with open(os.path.join(manager.root, up.STATE_FILE), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# check_for_update
# ---------------------------------------------------------------------------


def test_no_update_when_bundled_is_latest(manager, pypi):
    pypi.add_release("2026.8.19")
    assert manager.check_for_update() is None
    assert manager.last_check() is not None


def test_update_info_for_newer_release(manager, pypi):
    pypi.add_release("2026.9.1")
    info = manager.check_for_update()
    assert info.version == "2026.9.1"
    assert info.current == "2026.08.19"
    assert info.wheel.filename == "yt_dlp-2026.9.1-py3-none-any.whl"
    assert info.ejs.project == "yt-dlp-ejs" and info.ejs.version == "0.8.0"
    assert info.total_size == info.wheel.size + info.ejs.size


def test_release_without_ejs_pin(manager, pypi):
    pypi.add_release("2026.9.1", ejs=None)
    info = manager.check_for_update()
    assert info.ejs is None and info.files == (info.wheel,)


def test_network_error_means_no_update(manager):
    class Offline:
        def get(self, *a, **k):
            raise requests.ConnectionError("offline")

    manager._session = Offline()
    assert manager.check_for_update() is None


def test_malformed_json_means_no_update(manager, pypi):
    pypi.json["https://pypi.org/pypi/yt-dlp/json"] = {"unexpected": True}
    assert manager.check_for_update() is None


def test_incompatible_python_means_no_update(manager, pypi):
    pypi.add_release("2026.9.1", requires_python=">=3.99")
    assert manager.check_for_update() is None


def test_broken_release_is_not_offered_again(manager, pypi):
    pypi.add_release("2026.9.1")
    manager._mark_broken("2026.9.1", "ImportError: boom")
    assert manager.check_for_update() is None


def test_yanked_or_missing_wheel_means_no_update(manager, pypi):
    pypi.add_release("2026.9.1", entry_overrides={"yanked": True})
    assert manager.check_for_update() is None


def test_nightly_channel_picks_newest_dev_build(manager, pypi):
    pypi.add_release("2026.8.19")
    pypi.add_release("2026.9.16.232951.dev0", latest=False)
    pypi.add_release("2026.8.30.232658.dev0", latest=False)
    assert manager.check_for_update("stable") is None
    info = manager.check_for_update("nightly")
    assert info.version == "2026.9.16.232951.dev0"


def test_pending_install_suppresses_same_update(manager, pypi):
    pypi.add_release("2026.9.1")
    manager.download_and_install(manager.check_for_update())
    assert manager.check_for_update() is None
    assert manager.restart_required()


# ---------------------------------------------------------------------------
# download_and_install
# ---------------------------------------------------------------------------


def test_install_layout_state_and_progress(manager, pypi):
    pypi.add_release("2026.9.1")
    info = manager.check_for_update()
    progress = []
    assert manager.download_and_install(info, lambda d, t: progress.append((d, t))) == "2026.9.1"

    site = os.path.join(manager.root, "2026.9.1")
    assert os.path.isfile(os.path.join(site, "yt_dlp", "__init__.py"))
    assert os.path.isfile(os.path.join(site, "yt_dlp_ejs", "yt", "solver", "core.min.js"))
    assert not any(n.endswith(".data") for n in os.listdir(site)), "wheel .data/ must be skipped"
    assert not os.path.exists(os.path.join(site, ".downloads"))
    assert os.path.isdir(os.path.join(site, "yt_dlp", "__pycache__")), "engine is byte-compiled"
    manifest = json.load(open(os.path.join(site, up.MANIFEST_FILE), encoding="utf-8"))
    assert manifest["wheel_sha256"] == info.wheel.sha256 and manifest["ejs_version"] == "0.8.0"

    assert state_of(manager)["active"] == "2026.9.1"
    assert manager.installed_version() == "2026.9.1"
    assert manager.installed_versions() == ["2026.9.1"]
    assert progress[-1] == (info.total_size, info.total_size)
    assert [d for d, _ in progress] == sorted(d for d, _ in progress)
    assert not [n for n in os.listdir(manager.root) if n.startswith(".staging") or n.endswith(".lock")]


def test_reinstall_is_idempotent(manager, pypi):
    pypi.add_release("2026.9.1")
    info = manager.check_for_update()
    manager.download_and_install(info)
    downloads_before = len(pypi.requests)
    manager.download_and_install(info)
    assert len(pypi.requests) == downloads_before


def test_hash_mismatch_is_rejected(manager, pypi):
    pypi.add_release("2026.9.1", entry_overrides={"sha256": "0" * 64})
    info = manager.check_for_update()
    with pytest.raises(up.UpdateError) as err:
        manager.download_and_install(info)
    assert "sha256" in str(err.value)
    assert "doğrulanamadı" in err.value.user_message
    assert manager.installed_versions() == []
    assert manager.installed_version() is None
    assert not [n for n in os.listdir(manager.root) if n.startswith(".staging")]


def test_size_mismatch_is_rejected(manager, pypi):
    pypi.add_release("2026.9.1", entry_overrides={"size": 10})
    with pytest.raises(up.UpdateError):
        manager.download_and_install(manager.check_for_update())
    assert manager.installed_versions() == []


def test_wheel_with_wrong_version_is_rejected(manager, pypi):
    pypi.add_release("2026.9.1", wheel=make_wheel("2026.8.1"))
    with pytest.raises(up.UpdateError, match="contains yt-dlp 2026.8.1"):
        manager.download_and_install(manager.check_for_update())
    assert manager.installed_versions() == []


def test_wheel_that_does_not_compile_is_rejected(manager, pypi):
    pypi.add_release("2026.9.1", wheel=make_wheel("2026.9.1", extra_members={"yt_dlp/new.py": "def f(:\n"}))
    with pytest.raises(up.UpdateError) as err:
        manager.download_and_install(manager.check_for_update())
    assert "uyumlu değil" in err.value.user_message
    assert manager.installed_versions() == []


def test_path_traversal_in_wheel_is_rejected(manager, pypi):
    pypi.add_release("2026.9.1", wheel=make_wheel("2026.9.1", extra_members={"yt_dlp/../../evil.py": "x = 1\n"}))
    with pytest.raises(up.UpdateError, match="unsafe path"):
        manager.download_and_install(manager.check_for_update())
    assert not os.path.exists(os.path.join(os.path.dirname(manager.root), "evil.py"))


def test_corrupt_zip_is_rejected(manager, pypi):
    pypi.add_release("2026.9.1", wheel=b"not a zip file at all")
    with pytest.raises(up.UpdateError, match="corrupt wheel"):
        manager.download_and_install(manager.check_for_update())


def test_cancel_during_download(manager, pypi):
    pypi.add_release("2026.9.1")
    info = manager.check_for_update()
    cancel = threading.Event()

    def progress(done, total):
        if done > 20:
            cancel.set()

    with pytest.raises(up.UpdateCancelled) as err:
        manager.download_and_install(info, progress, cancel)
    assert "iptal" in err.value.user_message
    assert manager.installed_versions() == []
    assert not [n for n in os.listdir(manager.root) if n.startswith(".staging")]


def test_download_network_error_is_wrapped(manager, pypi):
    pypi.add_release("2026.9.1")
    info = manager.check_for_update()
    pypi.files.clear()  # every download now returns 404
    with pytest.raises(up.UpdateError) as err:
        manager.download_and_install(info)
    assert "İnternet" in err.value.user_message


def test_concurrent_install_is_refused(manager, pypi):
    pypi.add_release("2026.9.1")
    info = manager.check_for_update()
    with manager._install_lock(), pytest.raises(up.UpdateError, match="another engine update"):
        manager.download_and_install(info)


def test_stale_lock_is_taken_over(manager, pypi):
    pypi.add_release("2026.9.1")
    info = manager.check_for_update()
    lock = os.path.join(manager.root, ".install.lock")
    open(lock, "w").close()
    os.utime(lock, (0, 0))
    assert manager.download_and_install(info) == "2026.9.1"


def test_prune_keeps_active_and_one_previous(manager, pypi):
    for version in ("2026.9.1", "2026.9.5", "2026.9.9"):
        pypi.add_release(version)
        manager.download_and_install(manager.check_for_update())
    assert manager.installed_versions() == ["2026.9.9", "2026.9.5"]
    assert state_of(manager)["active"] == "2026.9.9"


def test_prune_never_deletes_engine_in_use(manager, pypi):
    pypi.add_release("2026.9.1")
    manager.download_and_install(manager.check_for_update())
    manager._active_dir = os.path.join(manager.root, "2026.9.1")  # as if activated at startup
    for version in ("2026.9.5", "2026.9.9"):
        pypi.add_release(version)
        manager.download_and_install(manager.check_for_update())
    assert set(manager.installed_versions()) == {"2026.9.9", "2026.9.5", "2026.9.1"}


def test_corrupt_state_file_is_tolerated(manager, pypi):
    os.makedirs(manager.root)
    with open(os.path.join(manager.root, up.STATE_FILE), "w") as fh:
        fh.write("{not json")
    assert manager.installed_version() is None
    pypi.add_release("2026.9.1")
    manager.download_and_install(manager.check_for_update())
    assert state_of(manager)["active"] == "2026.9.1"


# ---------------------------------------------------------------------------
# activate() - runs in a fresh interpreter so the real yt_dlp stays untouched here
# ---------------------------------------------------------------------------

ACTIVATE_SCRIPT = textwrap.dedent("""
    import json, sys
    sys.path.insert(0, {repo!r})
    from arnold_dw.core.runtime.ytdlp_updater import EngineManager
    manager = EngineManager({root!r}, bundled_version={bundled!r})
    version = manager.activate()
    import yt_dlp
    out = {{"version": version, "file": yt_dlp.__file__, "source": manager.engine_source(),
            "current": manager.current_version(), "meta_path": [type(f).__name__ for f in sys.meta_path]}}
    try:
        from yt_dlp.utils import helper
        out["helper"] = helper.VALUE
    except ImportError as exc:
        out["helper"] = type(exc).__name__
    try:
        import yt_dlp.not_in_engine  # noqa: F401
        out["missing"] = "imported"
    except ModuleNotFoundError:
        out["missing"] = "ModuleNotFoundError"
    print(json.dumps(out))
""")


def run_activate(root, bundled="2026.08.19"):
    script = ACTIVATE_SCRIPT.format(repo=REPO_ROOT, root=str(root), bundled=bundled)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def install(manager, pypi, version, **kwargs):
    pypi.add_release(version, **kwargs)
    return manager.download_and_install(manager.check_for_update())


def test_activate_prefers_newer_engine(manager, pypi):
    install(manager, pypi, "2026.9.1")
    out = run_activate(manager.root)
    assert out["version"] == "2026.9.1"
    assert out["source"] == "engine"
    assert out["file"].startswith(os.path.join(manager.root, "2026.9.1"))
    assert "EngineFinder" in out["meta_path"]
    assert out["helper"] == 42
    assert out["missing"] == "ModuleNotFoundError"


def test_activate_without_engine_uses_bundled(manager):
    out = run_activate(manager.root)
    assert out["source"] == "bundled"
    assert out["version"] == "2026.08.19"
    assert "engine" not in out["file"]


def test_activate_ignores_engine_older_than_bundled(manager, pypi):
    install(manager, pypi, "2026.9.1")
    out = run_activate(manager.root, bundled="2026.10.1")
    assert out["source"] == "bundled"
    assert state_of(manager)["active"] is None


def test_activate_rolls_back_broken_engine_to_bundled(manager, pypi):
    install(manager, pypi, "2026.9.1", wheel=make_wheel("2026.9.1", init=BROKEN_INIT))
    out = run_activate(manager.root)
    assert out["source"] == "bundled"
    assert "engine" not in out["file"]
    state = state_of(manager)
    assert state["active"] is None
    assert "ImportError" in state["broken"]["2026.9.1"]


def test_activate_rolls_back_to_previous_engine(manager, pypi):
    install(manager, pypi, "2026.9.1")
    install(manager, pypi, "2026.9.5", wheel=make_wheel("2026.9.5", init=BROKEN_INIT))
    out = run_activate(manager.root)
    assert (out["source"], out["version"]) == ("engine", "2026.9.1")
    state = state_of(manager)
    assert state["active"] == "2026.9.1"
    assert "2026.9.5" in state["broken"]
    # The broken build is also never offered again by the update check.
    assert manager.check_for_update() is None


def test_activate_skips_missing_active_directory(manager, pypi):
    install(manager, pypi, "2026.9.1")
    import shutil

    shutil.rmtree(os.path.join(manager.root, "2026.9.1"))
    out = run_activate(manager.root)
    assert out["source"] == "bundled"
    assert state_of(manager)["active"] is None


def test_mark_active_broken(manager, pypi):
    assert manager.mark_active_broken("x") is False  # bundled running: nothing to roll back
    install(manager, pypi, "2026.9.1")
    manager._active_dir = os.path.join(manager.root, "2026.9.1")
    manager._activated = "2026.9.1"
    assert manager.mark_active_broken("ImportError at download time") is True
    assert state_of(manager)["active"] is None
    assert run_activate(manager.root)["source"] == "bundled"


def test_activate_after_yt_dlp_import_does_not_switch(manager, pypi):
    import yt_dlp

    install(manager, pypi, "2026.9.1")
    assert manager.activate() == yt_dlp.version.__version__
    assert not any(isinstance(f, up.EngineFinder) for f in sys.meta_path)


def test_engine_finder_ignores_other_packages(tmp_path):
    (tmp_path / "yt_dlp").mkdir()
    (tmp_path / "yt_dlp" / "__init__.py").write_text("")
    finder = up.EngineFinder(str(tmp_path))
    assert finder.packages == {"yt_dlp"}
    assert finder.find_spec("requests") is None
    assert finder.find_spec("yt_dlp_ejs") is None  # not in this engine: bundled one is used
    assert finder.find_spec("yt_dlp").origin.startswith(str(tmp_path))


# ---------------------------------------------------------------------------
# Bundled version detection
# ---------------------------------------------------------------------------


def test_detect_bundled_version_matches_metadata():
    from importlib import metadata

    from arnold_dw.core.runtime.versioning import same_version

    assert same_version(up.detect_bundled_version(), metadata.version("yt-dlp"))


def test_detect_bundled_version_does_not_import(monkeypatch):
    for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
        monkeypatch.delitem(sys.modules, name)
    up.detect_bundled_version()
    assert "yt_dlp" not in sys.modules


def test_module_level_api_uses_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(up, "_default_manager", None)
    assert up.engine_root() == os.path.join(str(tmp_path), "Arnold DW", "engine", "yt-dlp")
    assert up.default_manager().root == up.engine_root()


# ---------------------------------------------------------------------------
# Network: real PyPI round trip
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_network_real_update_install_and_activate(tmp_path, monkeypatch):
    # Other tests import the real yt_dlp into this process; pretend it is not loaded so the
    # fake old bundled version is the baseline.
    monkeypatch.setattr(up, "_loaded_version", lambda: None)
    manager = up.EngineManager(tmp_path / "engine", bundled_version="2020.01.01")
    info = manager.check_for_update()
    assert info is not None, "PyPI check failed"
    assert info.wheel.sha256 and info.wheel.size > 1_000_000
    assert info.ejs is not None, "current yt-dlp pins yt-dlp-ejs"

    progress = []
    manager.download_and_install(info, lambda d, t: progress.append(d))
    assert progress[-1] == info.total_size

    out = run_activate(manager.root, bundled="2020.01.01")
    assert out["source"] == "engine"
    assert out["file"].startswith(os.path.join(str(manager.root), info.version))
    from arnold_dw.core.runtime.versioning import same_version

    assert same_version(out["version"], info.version)
