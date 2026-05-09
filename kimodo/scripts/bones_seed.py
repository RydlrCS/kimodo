"""Browse and download files from the BONES SEED Hugging Face dataset repository."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from huggingface_hub import HfApi, hf_hub_download


DEFAULT_REPO_ID = "bones-studio/seed"
DEFAULT_REPO_TYPE = "dataset"


def _resolve_token(token: str | None = None) -> str | None:
    if token:
        return token
    for env_name in ("HUGGING_FACE_HUB_TOKEN", "HF_TOKEN", "HF_API_TOKEN"):
        value = os.environ.get(env_name)
        if value:
            return value
    return None


@dataclass(frozen=True)
class DownloadManifest:
    repo_id: str
    repo_type: str
    revision: str | None
    local_dir: str
    files: list[str]
    downloaded_at: str


def list_repo_files(
    repo_id: str = DEFAULT_REPO_ID,
    *,
    repo_type: str = DEFAULT_REPO_TYPE,
    revision: str | None = None,
    token: str | None = None,
) -> list[str]:
    """Return all files in a Hugging Face dataset repository."""
    api = HfApi(token=_resolve_token(token))
    return sorted(api.list_repo_files(repo_id=repo_id, repo_type=repo_type, revision=revision))


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
    resolved_token = _resolve_token(token)
    output_dir = Path(local_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    for filename in filenames:
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type=repo_type,
            revision=revision,
            token=resolved_token,
            local_dir=output_dir,
            local_dir_use_symlinks=False,
        )
        downloaded.append(Path(local_path))
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
    files = [name for name in list_repo_files(repo_id, repo_type=repo_type, revision=revision, token=token) if name.startswith(prefix)]
    if not files:
        raise ValueError(f"No files matched prefix '{prefix}' in {repo_id}.")
    return download_repo_files(
        files,
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        local_dir=local_dir,
        token=token,
    )


def write_manifest(
    local_dir: str | Path,
    files: Iterable[Path],
    *,
    repo_id: str = DEFAULT_REPO_ID,
    repo_type: str = DEFAULT_REPO_TYPE,
    revision: str | None = None,
) -> Path:
    """Write a manifest that records what was downloaded."""
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
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Browse and download BONES SEED dataset files from Hugging Face.")
    parser.add_argument(
        "command",
        choices=("list", "download", "prefix"),
        help="List files, download selected files, or download files by prefix.",
    )
    parser.add_argument("files", nargs="*", help="Exact file paths inside the dataset repository.")
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Hugging Face dataset repository id.")
    parser.add_argument("--repo-type", default=DEFAULT_REPO_TYPE, help="Hugging Face repo type.")
    parser.add_argument("--revision", default=None, help="Optional repository revision or branch.")
    parser.add_argument("--local-dir", default="bones_seed", help="Directory where files will be stored.")
    parser.add_argument("--token", default=None, help="Hugging Face token override.")
    parser.add_argument("--prefix", default=None, help="File prefix to match when using the prefix command.")
    parser.add_argument("--manifest", action="store_true", help="Write a manifest.json after download.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        for name in list_repo_files(args.repo_id, repo_type=args.repo_type, revision=args.revision, token=args.token):
            print(name)
        return 0

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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())