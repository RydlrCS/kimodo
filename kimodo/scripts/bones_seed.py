"""Browse and download files from the BONES SEED Hugging Face dataset repository."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from huggingface_hub import HfApi, get_token, hf_hub_download
from huggingface_hub.errors import HfHubHTTPError


DEFAULT_REPO_ID = "bones-studio/seed"
DEFAULT_REPO_TYPE = "dataset"
DEFAULT_SPACE_ID = "lablab-ai-amd-developer-hackathon/movimento"

LOGGER = logging.getLogger(__name__)


def _resolve_token(token: str | None = None) -> str | None:
    LOGGER.info("bones_seed.resolve_token.start")
    if token:
        LOGGER.info("bones_seed.resolve_token.exit source=arg")
        return token
    for env_name in ("HUGGING_FACE_HUB_TOKEN", "HF_TOKEN", "HF_API_TOKEN"):
        value = os.environ.get(env_name)
        if value:
            LOGGER.info("bones_seed.resolve_token.exit source=env var=%s", env_name)
            return value
    resolved = get_token()
    LOGGER.info("bones_seed.resolve_token.exit source=cache found=%s", bool(resolved))
    return resolved


@dataclass(frozen=True)
class DownloadManifest:
    repo_id: str
    repo_type: str
    revision: str | None
    local_dir: str
    files: list[str]
    downloaded_at: str


@dataclass(frozen=True)
class SpaceLogCheckResult:
    space_id: str
    run_status_code: int
    build_status_code: int
    run_ok: bool
    build_ok: bool


def list_repo_files(
    repo_id: str = DEFAULT_REPO_ID,
    *,
    repo_type: str = DEFAULT_REPO_TYPE,
    revision: str | None = None,
    token: str | None = None,
) -> list[str]:
    """Return all files in a Hugging Face dataset repository."""
    LOGGER.info("bones_seed.list_repo_files.start repo_id=%s revision=%s", repo_id, revision)
    api = HfApi(token=_resolve_token(token))
    files = sorted(api.list_repo_files(repo_id=repo_id, repo_type=repo_type, revision=revision))
    LOGGER.info("bones_seed.list_repo_files.exit count=%s", len(files))
    return files


def download_repo_files(
    filenames: Sequence[str],
    *,
    repo_id: str = DEFAULT_REPO_ID,
    repo_type: str = DEFAULT_REPO_TYPE,
    revision: str | None = None,
    local_dir: str | Path = "bones_seed",
    token: str | None = None,
) -> list[Path]:
    """Download selected files from a Hugging Face dataset repository."""
    LOGGER.info("bones_seed.download_repo_files.start repo_id=%s files=%s", repo_id, len(filenames))
    resolved_token = _resolve_token(token)
    output_dir = Path(local_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    for filename in filenames:
        # Each file is downloaded independently so partial progress is visible in logs.
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type=repo_type,
            revision=revision,
            token=resolved_token,
            local_dir=output_dir,
        )
        downloaded.append(Path(local_path))
    LOGGER.info("bones_seed.download_repo_files.exit downloaded=%s", len(downloaded))
    return downloaded


def download_by_prefix(
    prefix: str,
    *,
    repo_id: str = DEFAULT_REPO_ID,
    repo_type: str = DEFAULT_REPO_TYPE,
    revision: str | None = None,
    local_dir: str | Path = "bones_seed",
    token: str | None = None,
) -> list[Path]:
    """Download files matching a prefix from the repository listing."""
    LOGGER.info("bones_seed.download_by_prefix.start prefix=%s", prefix)
    files = [name for name in list_repo_files(repo_id, repo_type=repo_type, revision=revision, token=token) if name.startswith(prefix)]
    if not files:
        raise ValueError(f"No files matched prefix '{prefix}' in {repo_id}.")
    downloaded = download_repo_files(
        files,
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        local_dir=local_dir,
        token=token,
    )
    LOGGER.info("bones_seed.download_by_prefix.exit matched=%s", len(downloaded))
    return downloaded


def write_manifest(
    local_dir: str | Path,
    files: Iterable[Path],
    *,
    repo_id: str = DEFAULT_REPO_ID,
    repo_type: str = DEFAULT_REPO_TYPE,
    revision: str | None = None,
) -> Path:
    """Write a manifest that records what was downloaded."""
    LOGGER.info("bones_seed.write_manifest.start local_dir=%s", local_dir)
    output_dir = Path(local_dir)
    manifest = DownloadManifest(
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        local_dir=str(output_dir),
        files=[str(path) for path in files],
        downloaded_at=datetime.now(timezone.utc).isoformat(),
    )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    LOGGER.info("bones_seed.write_manifest.exit path=%s", manifest_path)
    return manifest_path


def upload_manifest_to_space(
    manifest_path: str | Path,
    *,
    space_id: str = DEFAULT_SPACE_ID,
    token: str | None = None,
    path_in_repo: str = "data/bones_seed/manifest.json",
    commit_message: str = "Update BONES-SEED ingestion manifest",
    create_pr: bool = True,
) -> str:
    """Upload manifest file into a Space repository path for lablab ingestion traceability."""
    LOGGER.info("bones_seed.upload_manifest_to_space.start space_id=%s", space_id)
    manifest = Path(manifest_path)
    if not manifest.exists():
        raise FileNotFoundError(f"Manifest file does not exist: {manifest}")

    api = HfApi(token=_resolve_token(token))
    try:
        uploaded = api.upload_file(
            path_or_fileobj=str(manifest),
            path_in_repo=path_in_repo,
            repo_id=space_id,
            repo_type="space",
            commit_message=commit_message,
            create_pr=False,
        )
        LOGGER.info("bones_seed.upload_manifest_to_space.exit mode=direct")
        return uploaded
    except HfHubHTTPError as exc:
        if create_pr and "create_pr=1" in str(exc):
            uploaded = api.upload_file(
                path_or_fileobj=str(manifest),
                path_in_repo=path_in_repo,
                repo_id=space_id,
                repo_type="space",
                commit_message=commit_message,
                create_pr=True,
            )
            LOGGER.info("bones_seed.upload_manifest_to_space.exit mode=create_pr")
            return uploaded
        raise


def _check_logs_endpoint(url: str, token: str | None, timeout_sec: float) -> tuple[int, bool]:
    LOGGER.info("bones_seed.check_logs_endpoint.start url=%s", url)
    headers = {}
    resolved = _resolve_token(token)
    if resolved:
        headers["Authorization"] = f"Bearer {resolved}"
    request = Request(url=url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            status = int(getattr(response, "status", 0))
            LOGGER.info("bones_seed.check_logs_endpoint.exit status=%s", status)
            return status, 200 <= status < 300
    except HTTPError as exc:
        LOGGER.warning("bones_seed.check_logs_endpoint.http_error status=%s", exc.code)
        return int(exc.code), False
    except URLError:
        LOGGER.warning("bones_seed.check_logs_endpoint.network_error")
        return 0, False


def verify_space_logs(
    *,
    space_id: str = DEFAULT_SPACE_ID,
    token: str | None = None,
    timeout_sec: float = 10.0,
) -> SpaceLogCheckResult:
    """Verify build and runtime log endpoints are reachable for the target Space."""
    LOGGER.info("bones_seed.verify_space_logs.start space_id=%s", space_id)
    base = f"https://huggingface.co/api/spaces/{space_id}/logs"
    run_status, run_ok = _check_logs_endpoint(f"{base}/run", token, timeout_sec)
    build_status, build_ok = _check_logs_endpoint(f"{base}/build", token, timeout_sec)
    result = SpaceLogCheckResult(
        space_id=space_id,
        run_status_code=run_status,
        build_status_code=build_status,
        run_ok=run_ok,
        build_ok=build_ok,
    )
    LOGGER.info("bones_seed.verify_space_logs.exit run_ok=%s build_ok=%s", run_ok, build_ok)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Browse and download BONES SEED dataset files from Hugging Face.")
    parser.add_argument(
        "command",
        choices=("list", "download", "prefix", "verify-logs"),
        help="List files, download selected files, download files by prefix, or verify Space log endpoints.",
    )
    parser.add_argument("files", nargs="*", help="Exact file paths inside the dataset repository.")
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Hugging Face dataset repository id.")
    parser.add_argument("--repo-type", default=DEFAULT_REPO_TYPE, help="Hugging Face repo type.")
    parser.add_argument("--revision", default=None, help="Optional repository revision or branch.")
    parser.add_argument("--local-dir", default="bones_seed", help="Directory where files will be stored.")
    parser.add_argument("--token", default=None, help="Hugging Face token override.")
    parser.add_argument("--prefix", default=None, help="File prefix to match when using the prefix command.")
    parser.add_argument("--manifest", action="store_true", help="Write a manifest.json after download.")
    parser.add_argument("--space-id", default=DEFAULT_SPACE_ID, help="Target Space id for manifest publish or logs checks.")
    parser.add_argument(
        "--space-manifest-path",
        default="data/bones_seed/manifest.json",
        help="Path inside target Space repo where manifest will be uploaded.",
    )
    parser.add_argument(
        "--publish-manifest-to-space",
        action="store_true",
        help="Upload generated manifest to the Space repo destination.",
    )
    parser.add_argument(
        "--space-upload-create-pr",
        action="store_true",
        help="Force upload as a PR in target Space repo when direct commits are forbidden.",
    )
    parser.add_argument(
        "--logs-timeout-sec",
        type=float,
        default=10.0,
        help="Timeout for log endpoint verification requests.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    LOGGER.info("bones_seed.main.start")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        try:
            for name in list_repo_files(args.repo_id, repo_type=args.repo_type, revision=args.revision, token=args.token):
                print(name)
        except BrokenPipeError:
            LOGGER.info("bones_seed.main.exit broken_pipe")
            return 0
        LOGGER.info("bones_seed.main.exit command=list")
        return 0

    if args.command == "verify-logs":
        result = verify_space_logs(space_id=args.space_id, token=args.token, timeout_sec=args.logs_timeout_sec)
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        LOGGER.info("bones_seed.main.exit command=verify-logs")
        return 0 if (result.run_ok and result.build_ok) else 2

    if args.command == "download":
        if not args.files:
            raise SystemExit("download requires at least one file path")
        downloaded = download_repo_files(
            args.files,
            repo_id=args.repo_id,
            repo_type=args.repo_type,
            revision=args.revision,
            local_dir=args.local_dir,
            token=args.token,
        )
    else:
        if not args.prefix:
            raise SystemExit("prefix requires --prefix")
        downloaded = download_by_prefix(
            args.prefix,
            repo_id=args.repo_id,
            repo_type=args.repo_type,
            revision=args.revision,
            local_dir=args.local_dir,
            token=args.token,
        )

    for path in downloaded:
        print(path)

    if args.manifest:
        manifest_path = write_manifest(
            args.local_dir,
            downloaded,
            repo_id=args.repo_id,
            repo_type=args.repo_type,
            revision=args.revision,
        )
        print(manifest_path)
        if args.publish_manifest_to_space:
            uploaded = upload_manifest_to_space(
                manifest_path,
                space_id=args.space_id,
                token=args.token,
                path_in_repo=args.space_manifest_path,
                create_pr=args.space_upload_create_pr,
            )
            print(uploaded)
    elif args.publish_manifest_to_space:
        raise SystemExit("--publish-manifest-to-space requires --manifest")

    LOGGER.info("bones_seed.main.exit command=%s", args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())