from __future__ import annotations

import json
from importlib import util
from pathlib import Path

import pytest



def load_bones_seed_module():
    module_path = Path(__file__).resolve().parents[1] / "kimodo" / "scripts" / "bones_seed.py"
    spec = util.spec_from_file_location("bones_seed", module_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bones_seed = load_bones_seed_module()


def test_list_repo_files_uses_hf_api(monkeypatch):
    recorded = {}

    class FakeApi:
        def __init__(self, token=None):
            recorded["token"] = token

        def list_repo_files(self, repo_id, repo_type, revision):
            recorded["repo_id"] = repo_id
            recorded["repo_type"] = repo_type
            recorded["revision"] = revision
            return ["b.json", "a.json"]

    monkeypatch.setattr(bones_seed, "HfApi", FakeApi)
    monkeypatch.setenv("HF_TOKEN", "env-token")

    files = bones_seed.list_repo_files(revision="main")

    assert files == ["a.json", "b.json"]
    assert recorded == {
        "token": "env-token",
        "repo_id": bones_seed.DEFAULT_REPO_ID,
        "repo_type": bones_seed.DEFAULT_REPO_TYPE,
        "revision": "main",
    }


def test_download_repo_files_writes_all_targets(monkeypatch, tmp_path):
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        local_dir = Path(kwargs["local_dir"])
        file_path = local_dir / kwargs["filename"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("ok", encoding="utf-8")
        return str(file_path)

    monkeypatch.setattr(bones_seed, "hf_hub_download", fake_download)

    downloaded = bones_seed.download_repo_files(["x/meta.json", "y/sample.npz"], local_dir=tmp_path, token="abc")

    assert [path.name for path in downloaded] == ["meta.json", "sample.npz"]
    assert calls[0]["token"] == "abc"
    assert calls[0]["local_dir"] == tmp_path
    assert calls[0]["local_dir_use_symlinks"] is False


def test_download_by_prefix_filters_listing(monkeypatch, tmp_path):
    monkeypatch.setattr(bones_seed, "list_repo_files", lambda *args, **kwargs: ["clips/a.json", "clips/b.json", "other/c.json"])
    monkeypatch.setattr(
        bones_seed,
        "download_repo_files",
        lambda files, **kwargs: [tmp_path / Path(name) for name in files],
    )

    downloaded = bones_seed.download_by_prefix("clips/", local_dir=tmp_path)

    assert [path.as_posix() for path in downloaded] == [
        f"{tmp_path.as_posix()}/clips/a.json",
        f"{tmp_path.as_posix()}/clips/b.json",
    ]


def test_write_manifest_records_downloaded_files(tmp_path):
    files = [tmp_path / "one.json", tmp_path / "two.json"]
    for file_path in files:
        file_path.write_text("{}", encoding="utf-8")

    manifest_path = bones_seed.write_manifest(tmp_path, files, revision="abc123")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["repo_id"] == bones_seed.DEFAULT_REPO_ID
    assert payload["revision"] == "abc123"
    assert payload["files"] == [str(path) for path in files]
    assert payload["local_dir"] == str(tmp_path)


def test_main_list(monkeypatch, capsys):
    monkeypatch.setattr(bones_seed, "list_repo_files", lambda *args, **kwargs: ["a.json"])

    assert bones_seed.main(["list"]) == 0
    assert capsys.readouterr().out.strip() == "a.json"


def test_main_download_requires_files():
    with pytest.raises(SystemExit):
        bones_seed.main(["download"])