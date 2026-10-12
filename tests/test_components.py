import hashlib
import io
import os
import tarfile
import threading
import zipfile

import pytest
import requests
from fakes import FakeResponse

from arnold_dw.core.runtime import components
from tools import build_runtime_packs

FILES = {"tool.exe": b"tool binary", "helper.dll": b"helper library"}


def _component(**kw):
    sha = {name: hashlib.sha256(data).hexdigest() for name, data in FILES.items()}
    base = dict(
        name="tool",
        title="Tool",
        version="1.0",
        files=sha,
        sources=(
            components.Source("https://github.com/o/r/releases/download/x/pack.tar.xz", "tar.xz", 10_000),
            components.Source("https://github.com/up/r/releases/download/1/tool.zip", "zip", 10_000),
        ),
    )
    base.update(kw)
    return components.Component(**base)


def _tar_xz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip(files, prefix="tool-1.0/bin/"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(prefix + name, data)
        zf.writestr(prefix + "README.txt", b"not needed")
    return buf.getvalue()


class Session:
    """requests.Session stand-in serving canned bodies per URL (exceptions raise)."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        body = self.bodies.get(url, 404)
        if isinstance(body, Exception):
            raise body
        if body == 404:
            return FakeResponse(status=404)
        response = FakeResponse([body[i:i + 7] for i in range(0, len(body), 7)],
                                headers={"Content-Length": str(len(body))})
        response.url = url
        return response


@pytest.fixture(autouse=True)
def local_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(components._env, "bin_dir", lambda: str(tmp_path / "no-bin"))
    return tmp_path / "local"


def test_installs_from_pack_and_writes_marker():
    component = _component()
    session = Session({component.sources[0].url: _tar_xz(FILES)})
    seen = []

    folder = components.install(component, progress=lambda d, t: seen.append((d, t)), session=session)

    assert folder == components.component_dir(component)
    for name, data in FILES.items():
        with open(os.path.join(folder, name), "rb") as fh:
            assert fh.read() == data
    assert components.is_installed(component)
    assert seen[-1][0] == seen[-1][1]
    assert not [e for e in os.listdir(components.root_dir()) if e.startswith(".staging-")]


def test_falls_back_to_upstream_zip_when_pack_is_missing():
    component = _component()
    session = Session({component.sources[1].url: _zip(FILES)})

    components.install(component, session=session)

    assert session.urls == [component.sources[0].url, component.sources[1].url]
    assert components.is_installed(component)
    assert not os.path.exists(os.path.join(components.component_dir(component), "README.txt"))


def test_rejects_tampered_file_and_tries_next_source():
    component = _component()
    bad = dict(FILES, **{"tool.exe": b"evil"})
    session = Session({component.sources[0].url: _tar_xz(bad), component.sources[1].url: _zip(FILES)})

    components.install(component, session=session)

    with open(os.path.join(components.component_dir(component), "tool.exe"), "rb") as fh:
        assert fh.read() == b"tool binary"


def test_all_sources_failing_raises_user_message():
    component = _component()
    session = Session({s.url: requests.ConnectionError("offline") for s in component.sources})

    with pytest.raises(components.ComponentError, match="İnternet bağlantınızı"):
        components.install(component, session=session)
    assert not components.is_installed(component)


def test_verification_failure_message():
    component = _component()
    session = Session({component.sources[0].url: _tar_xz({"tool.exe": b"x"})})
    with pytest.raises(components.ComponentError, match="doğrulanamadı"):
        components.install(component, session=session)


def test_archive_hash_is_checked_when_pinned():
    component = _component(sources=(
        components.Source("https://github.com/up/r/releases/download/1/tool.zip", "zip", 10_000, "0" * 64),
    ))
    session = Session({component.sources[0].url: _zip(FILES)})
    with pytest.raises(components.ComponentError):
        components.install(component, session=session)


def test_size_limit_is_enforced():
    component = _component(sources=(
        components.Source("https://github.com/o/r/releases/download/x/pack.tar.xz", "tar.xz", 10),
    ))
    session = Session({component.sources[0].url: _tar_xz(FILES)})
    with pytest.raises(components.ComponentError):
        components.install(component, session=session)


def test_refuses_non_github_urls():
    component = _component(sources=(components.Source("http://evil.test/pack.tar.xz", "tar.xz", 10_000),))
    session = Session({})
    with pytest.raises(components.ComponentError):
        components.install(component, session=session)
    assert session.urls == []


def test_cancel_stops_install():
    component = _component()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(components.Cancelled):
        components.install(component, cancel_event=cancel, session=Session({}))


def test_reinstall_replaces_previous_version():
    component = _component()
    session = Session({component.sources[0].url: _tar_xz(FILES)})
    components.install(component, session=session)
    newer = _component(version="2.0")
    assert not components.is_installed(newer)
    components.install(newer, session=session)
    assert components.is_installed(newer)


def test_truncated_install_is_not_reported_installed():
    component = _component()
    components.install(component, session=Session({component.sources[0].url: _tar_xz(FILES)}))
    with open(os.path.join(components.component_dir(component), "tool.exe"), "wb") as fh:
        fh.write(b"tool")
    assert not components.is_installed(component)


def test_missing_and_executable(monkeypatch):
    component = _component(name="deno", files={"deno.exe": hashlib.sha256(b"d").hexdigest()})
    monkeypatch.setattr(components, "COMPONENTS", (component,))
    monkeypatch.setitem(components.PROVIDES, "deno", component)
    monkeypatch.setattr(components._env, "exe_name", lambda name: f"{name}.exe")
    assert components.missing() == [component]
    assert components.executable("deno") is None

    components.install(component, session=Session({component.sources[0].url: _tar_xz({"deno.exe": b"d"})}))

    assert components.missing() == []
    assert components.executable("deno") == os.path.join(components.component_dir(component), "deno.exe")


def test_bin_folder_counts_as_installed(tmp_path, monkeypatch):
    component = _component()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, data in FILES.items():
        (bin_dir / name).write_bytes(data)
    monkeypatch.setattr(components._env, "bin_dir", lambda: str(bin_dir))
    monkeypatch.setattr(components, "COMPONENTS", (component,))
    assert components.missing() == []


def test_cleanup_staging_removes_leftovers():
    os.makedirs(os.path.join(components.root_dir(), ".staging-tool-abc"))
    os.makedirs(os.path.join(components.root_dir(), "tool.old-1-2"))
    os.makedirs(os.path.join(components.root_dir(), "tool"))
    components.cleanup_staging()
    assert os.listdir(components.root_dir()) == ["tool"]


def test_install_missing_exit_codes(monkeypatch):
    component = _component()
    monkeypatch.setattr(components, "missing", lambda: [component])
    monkeypatch.setattr(components, "install", lambda c: None)
    assert components.install_missing() == 0

    def fail(c):
        raise components.ComponentError("x")

    monkeypatch.setattr(components, "install", fail)
    assert components.install_missing() == 1


def test_real_components_are_pinned_consistently():
    for component in components.COMPONENTS:
        kinds = [s.kind for s in component.sources]
        assert kinds[0] == "tar.xz" and "zip" in kinds
        assert component.sources[0].url.endswith(components.pack_name(component.name, component.version))
        for source in component.sources:
            assert source.url.startswith("https://github.com/")
        assert all(len(h) == 64 for h in component.files.values())
    assert components.PROVIDES["ffprobe"] is components.FFMPEG


def test_pack_builder_output_installs(tmp_path):
    component = _component()
    folder = tmp_path / "files"
    folder.mkdir()
    for name, data in FILES.items():
        (folder / name).write_bytes(data)
    pack = tmp_path / "pack.tar.xz"
    build_runtime_packs.write_pack(component, folder, pack)
    session = Session({component.sources[0].url: pack.read_bytes()})
    components.install(component, session=session)
    assert components.is_installed(component)
