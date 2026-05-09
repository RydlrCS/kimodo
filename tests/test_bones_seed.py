from __future__ import annotations

import json
import sys
from importlib import util
from pathlib import Path

import pytest



def load_bones_seed_module():
    module_path = Path(__file__).resolve().parents[1] / "kimodo" / "scripts" / "bones_seed.py"
    spec = util.spec_from_file_location("bones_seed", module_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
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


def test_upload_manifest_to_space(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    captured = {}

    class FakeApi:
        def __init__(self, token=None):
            captured["token"] = token

        def upload_file(self, **kwargs):
            captured.update(kwargs)
            return "https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/movimento/blob/main/data/bones_seed/manifest.json"

    monkeypatch.setattr(bones_seed, "HfApi", FakeApi)

    result = bones_seed.upload_manifest_to_space(
        manifest,
        token="abc",
        space_id="lablab-ai-amd-developer-hackathon/movimento",
        path_in_repo="data/bones_seed/manifest.json",
    )

    assert result.startswith("https://huggingface.co/spaces/")
    assert captured["repo_type"] == "space"
    assert captured["repo_id"] == "lablab-ai-amd-developer-hackathon/movimento"


def test_verify_space_logs(monkeypatch):
    def fake_check(url, token, timeout_sec):
        if url.endswith("/run"):
            return 200, True
        return 200, True

    monkeypatch.setattr(bones_seed, "_check_logs_endpoint", fake_check)

    result = bones_seed.verify_space_logs(space_id="lablab-ai-amd-developer-hackathon/movimento", token="abc")
    assert result.run_ok is True
    assert result.build_ok is True
    assert result.run_status_code == 200
    assert result.build_status_code == 200


def test_main_verify_logs(monkeypatch, capsys):
    monkeypatch.setattr(
        bones_seed,
        "verify_space_logs",
        lambda **kwargs: bones_seed.SpaceLogCheckResult(
            space_id="lablab-ai-amd-developer-hackathon/movimento",
            run_status_code=200,
            build_status_code=200,
            run_ok=True,
            build_ok=True,
        ),
    )

    rc = bones_seed.main(["verify-logs"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "run_ok" in out


def test_publish_manifest_requires_manifest_flag(monkeypatch):
    monkeypatch.setattr(bones_seed, "download_repo_files", lambda *args, **kwargs: [Path("fake")])
    with pytest.raises(SystemExit):
        bones_seed.main(["download", "a.txt", "--publish-manifest-to-space"])


def test_upload_manifest_to_space_retries_with_create_pr(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(bones_seed, "HfHubHTTPError", RuntimeError)

    class FakeApi:
        def __init__(self, token=None):
            self.calls = []

        def upload_file(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise RuntimeError("Forbidden: pass `create_pr=1` as a query parameter to create a Pull Request.")
            return "https://huggingface.co/spaces/lablab-ai-amd-developer-hackathon/movimento/pull/1"

    api = FakeApi()
    monkeypatch.setattr(bones_seed, "HfApi", lambda token=None: api)

    result = bones_seed.upload_manifest_to_space(manifest, create_pr=True)

    assert result.endswith("/pull/1")
    assert api.calls[0]["create_pr"] is False
    assert api.calls[1]["create_pr"] is True


def test_main_list_handles_broken_pipe(monkeypatch):
    monkeypatch.setattr(bones_seed, "list_repo_files", lambda *args, **kwargs: ["a", "b"])
    monkeypatch.setattr("builtins.print", lambda *_args, **_kwargs: (_ for _ in ()).throw(BrokenPipeError()))

    assert bones_seed.main(["list"]) == 0