"""Text encoder preflight health check for gated Hugging Face access and local cache paths."""

from __future__ import annotations

import argparse
import json
import os

from huggingface_hub import HfApi, hf_hub_download
from transformers import AutoConfig


TEXT_ENCODER_PRESETS = {
    "llm2vec": {
        "base_model_name_or_path": "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp",
        "peft_model_name_or_path": "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised",
    }
}


def _get_hf_token() -> str | None:
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("HF_HUB_TOKEN")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    )


def _check_repo_access(repo_id: str, token: str) -> tuple[bool, str]:
    api = HfApi()
    try:
        api.model_info(repo_id=repo_id, token=token)
        return True, "ok"
    except Exception as error:  # pragma: no cover - depends on runtime/network/auth
        return False, f"{type(error).__name__}: {error}"


def _check_gated_base_access(repo_id: str, token: str) -> tuple[bool, str, str | None]:
    """Resolve adapter base model and verify config download entitlement."""
    try:
        adapter_cfg_path = hf_hub_download(repo_id, "adapter_config.json", token=token)
        with open(adapter_cfg_path, "r", encoding="utf-8") as f:
            adapter_cfg = json.load(f)
        base_model = adapter_cfg.get("base_model_name_or_path")
        if not isinstance(base_model, str) or not base_model:
            return False, "adapter_config missing base_model_name_or_path", None
        AutoConfig.from_pretrained(base_model, token=token)
        return True, "ok", base_model
    except Exception as error:  # pragma: no cover - depends on runtime/network/auth
        return False, f"{type(error).__name__}: {error}", None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kimodo text encoder health check")
    parser.add_argument(
        "--text-encoder",
        default="llm2vec",
        choices=sorted(TEXT_ENCODER_PRESETS.keys()),
        help="Text encoder preset to validate.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero if any check fails.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preset = TEXT_ENCODER_PRESETS[args.text_encoder]
    base_repo = preset["base_model_name_or_path"]
    peft_repo = preset["peft_model_name_or_path"]

    token = _get_hf_token()
    text_encoders_dir = os.environ.get("TEXT_ENCODERS_DIR")

    report = {
        "text_encoder": args.text_encoder,
        "token_present": bool(token),
        "token_length": len(token) if token else 0,
        "text_encoders_dir": text_encoders_dir,
        "checks": {},
    }

    failed = False

    if text_encoders_dir:
        base_path = os.path.join(text_encoders_dir, base_repo)
        peft_path = os.path.join(text_encoders_dir, peft_repo)
        base_ok = os.path.exists(base_path)
        peft_ok = os.path.exists(peft_path)
        report["checks"]["base_local_path"] = {"ok": base_ok, "path": base_path}
        report["checks"]["peft_local_path"] = {"ok": peft_ok, "path": peft_path}
        if not base_ok or not peft_ok:
            failed = True
    else:
        if not token:
            report["checks"]["token"] = {
                "ok": False,
                "error": "No HF token found in HF_TOKEN/HUGGING_FACE_HUB_TOKEN/HF_HUB_TOKEN/HUGGINGFACEHUB_API_TOKEN",
            }
            failed = True
        else:
            base_ok, base_error = _check_repo_access(base_repo, token)
            peft_ok, peft_error = _check_repo_access(peft_repo, token)
            report["checks"]["base_repo_access"] = {"ok": base_ok, "repo": base_repo, "detail": base_error}
            report["checks"]["peft_repo_access"] = {"ok": peft_ok, "repo": peft_repo, "detail": peft_error}

            gated_ok, gated_detail, gated_base = _check_gated_base_access(base_repo, token)
            report["checks"]["gated_base_config_access"] = {
                "ok": gated_ok,
                "adapter_repo": base_repo,
                "base_model": gated_base,
                "detail": gated_detail,
            }

            if not base_ok or not peft_ok:
                failed = True
            if not gated_ok:
                failed = True

    print(json.dumps(report, indent=2, sort_keys=True))
    if args.strict and failed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
