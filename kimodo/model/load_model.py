# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Load Kimodo diffusion models from local checkpoints or Hugging Face."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from huggingface_hub import snapshot_download
from omegaconf import OmegaConf

from .loading import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    DEFAULT_TEXT_ENCODER_URL,
    MODEL_NAMES,
    TMR_MODELS,
    get_env_var,
    instantiate_from_dict,
)
from .registry import get_model_info, resolve_model_name

DEFAULT_TEXT_ENCODER = "llm2vec"
TEXT_ENCODER_PRESETS = {
    "llm2vec": {
        "target": "kimodo.model.LLM2VecEncoder",
        "kwargs": {
            "base_model_name_or_path": "McGill-NLP/LLM2Vec-Meta-Llama-31-8B-Instruct-mntp",
            "peft_model_name_or_path": "McGill-NLP/LLM2Vec-Meta-Llama-31-8B-Instruct-mntp-supervised",
            "dtype": "bfloat16",
            "llm_dim": 4096,
        },
    }
}

_TEXT_ENCODER_SERVER_PROCESS: subprocess.Popen | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = get_env_var(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _is_local_text_encoder_url(text_encoder_url: str) -> bool:
    parsed = urlparse(text_encoder_url)
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "0.0.0.0"}


def _is_port_open(text_encoder_url: str, timeout_sec: float = 1.0) -> bool:
    parsed = urlparse(text_encoder_url)
    host = parsed.hostname or "127.0.0.1"
    if host == "0.0.0.0":
        host = "127.0.0.1"
    port = parsed.port or 9550
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_sec)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _is_http_ready(text_encoder_url: str, timeout_sec: float = 3.0) -> bool:
    """Return True when the Gradio server at *text_encoder_url* responds to HTTP (serves /info)."""
    try:
        import urllib.request

        info_url = text_encoder_url.rstrip("/") + "/info"
        req = urllib.request.urlopen(info_url, timeout=timeout_sec)  # noqa: S310
        return req.status == 200
    except Exception:
        return False

def _build_text_encoder_env() -> dict[str, str]:
    env = os.environ.copy()
    token = (
        env.get("HF_TOKEN")
        or env.get("HUGGING_FACE_HUB_TOKEN")
        or env.get("HF_HUB_TOKEN")
        or env.get("HUGGINGFACEHUB_API_TOKEN")
    )
    if token:
        env.setdefault("HF_TOKEN", token)
        env.setdefault("HUGGING_FACE_HUB_TOKEN", token)
        env.setdefault("HF_HUB_TOKEN", token)
        env.setdefault("HUGGINGFACEHUB_API_TOKEN", token)
    return env


def _ensure_text_encoder_server(text_encoder_url: str) -> None:
    global _TEXT_ENCODER_SERVER_PROCESS

    if not _is_local_text_encoder_url(text_encoder_url):
        return
    if _is_port_open(text_encoder_url):
        return

    if _TEXT_ENCODER_SERVER_PROCESS is not None and _TEXT_ENCODER_SERVER_PROCESS.poll() is None:
        return

    startup_timeout_sec = int(get_env_var("TEXT_ENCODER_STARTUP_TIMEOUT_SEC", "90"))
    print(f"Starting local text encoder server for URL {text_encoder_url}...")
    _TEXT_ENCODER_SERVER_PROCESS = subprocess.Popen(
        [sys.executable, "-m", "kimodo.scripts.run_text_encoder_server"],
        env=_build_text_encoder_env(),
    )

    deadline = time.time() + startup_timeout_sec
    while time.time() < deadline:
        if _is_port_open(text_encoder_url):
            # Port is open — wait for HTTP layer to be ready (Gradio SSR init can lag)
            http_deadline = min(time.time() + 30, deadline)
            while time.time() < http_deadline:
                if _is_http_ready(text_encoder_url):
                    print("Text encoder server is HTTP-ready.")
                    return
                time.sleep(1.0)
            # HTTP not ready yet but deadline not reached — keep outer loop going
        if _TEXT_ENCODER_SERVER_PROCESS.poll() is not None:
            raise RuntimeError(
                "Text encoder server process exited during startup. "
                "Check server logs for details from kimodo.scripts.run_text_encoder_server."
            )
        time.sleep(1.0)

    raise RuntimeError(
        "Timed out waiting for local text encoder server to open its port. "
        "Adjust TEXT_ENCODER_STARTUP_TIMEOUT_SEC if cold starts are slow."
    )


def _resolve_hf_model_path(modelname: str) -> Path:
    """Resolve model name to a local path, using Hugging Face cache or CHECKPOINT_DIR."""
    try:
        repo_id = MODEL_NAMES[modelname]
    except KeyError:
        raise ValueError(f"Model '{modelname}' not found. Available models: {MODEL_NAMES.keys()}")

    local_cache = get_env_var("LOCAL_CACHE", "False").lower() == "true"
    if not local_cache:
        snapshot_dir = snapshot_download(repo_id=repo_id)  # will check online no matter what
        return Path(snapshot_dir)

    try:
        snapshot_dir = snapshot_download(repo_id=repo_id, local_files_only=True)  # will check local cache only
        return Path(snapshot_dir)
    except Exception:
        # if local cache is not found, download from online
        try:
            snapshot_dir = snapshot_download(repo_id=repo_id)
            return Path(snapshot_dir)
        except Exception:
            raise RuntimeError(f"Could not resolve model '{modelname}' from Hugging Face (repo: {repo_id}). ") from None


def _build_api_text_encoder_conf(text_encoder_url: str) -> dict:
    return {
        "_target_": "kimodo.model.text_encoder_api.TextEncoderAPI",
        "url": text_encoder_url,
    }


def _probe_api_text_encoder(text_encoder_url: str, autostart_enabled: bool) -> None:
    """Instantiate and probe a text encoder API endpoint, raising on failure."""
    if autostart_enabled:
        _ensure_text_encoder_server(text_encoder_url)
    api_conf = _build_api_text_encoder_conf(text_encoder_url)
    text_encoder = instantiate_from_dict(api_conf)
    text_encoder(["healthcheck"])


def _build_local_text_encoder_conf() -> dict:
    text_encoder_name = get_env_var("TEXT_ENCODER", DEFAULT_TEXT_ENCODER)
    if text_encoder_name not in TEXT_ENCODER_PRESETS:
        available = ", ".join(sorted(TEXT_ENCODER_PRESETS))
        raise ValueError(f"Unknown TEXT_ENCODER='{text_encoder_name}'. Available: {available}")

    preset = TEXT_ENCODER_PRESETS[text_encoder_name]
    return {
        "_target_": preset["target"],
        **preset["kwargs"],
    }


def _select_text_encoder_conf(text_encoder_url: str) -> dict:
    # TEXT_ENCODER_MODE options:
    # - "api": force TextEncoderAPI
    # - "local": force local LLM2VecEncoder
    # - "auto": try API first, fallback to local if unreachable
    mode = get_env_var("TEXT_ENCODER_MODE", "auto").lower()
    autostart_enabled = _env_bool("TEXT_ENCODER_AUTOSTART", True)
    local_api_url = get_env_var("TEXT_ENCODER_LOCAL_URL", DEFAULT_TEXT_ENCODER_URL)
    if mode == "local":
        return _build_local_text_encoder_conf()
    if mode == "api":
        try:
            _probe_api_text_encoder(text_encoder_url, autostart_enabled)
            return _build_api_text_encoder_conf(text_encoder_url)
        except Exception as error:
            # In native/direct runtimes a local encoder process may be running while
            # TEXT_ENCODER_URL points to a remote service. Prefer local API fallback.
            if (
                not _is_local_text_encoder_url(text_encoder_url)
                and local_api_url
                and _is_local_text_encoder_url(local_api_url)
                and _is_port_open(local_api_url)
            ):
                print(
                    "Configured remote text encoder is unreachable; retrying against local "
                    f"encoder URL {local_api_url}. ({type(error).__name__}: {error})"
                )
                _probe_api_text_encoder(local_api_url, autostart_enabled=False)
                return _build_api_text_encoder_conf(local_api_url)
            raise

    api_conf = _build_api_text_encoder_conf(text_encoder_url)
    try:
        _probe_api_text_encoder(text_encoder_url, autostart_enabled)
        return api_conf
    except Exception as error:
        print(
            "Text encoder service is unreachable, falling back to local LLM2Vec "
            f"encoder. ({type(error).__name__}: {error})"
        )
        return _build_local_text_encoder_conf()


def load_model(
    modelname=None,
    device=None,
    eval_mode: bool = True,
    default_family: Optional[str] = "Kimodo",
    return_resolved_name: bool = False,
):
    """Load a kimodo model by name (e.g. 'g1', 'soma').

    Resolution of partial/full names (e.g. Kimodo-SOMA-RP-v1, SOMA) is done
    inside this function using default_family when the name is not a known
    short key.

    Args:
        modelname: Model identifier; uses DEFAULT_MODEL if None. Can be a short key,
            a full name (e.g. Kimodo-SOMA-RP-v1), or a partial name; unknown names
            are resolved via resolve_model_name using default_family.
        device: Target device for the model (e.g. 'cuda', 'cpu').
        eval_mode: If True, set model to eval mode.
        default_family: Used when modelname is not in AVAILABLE_MODELS to resolve
            partial names ("Kimodo" for demo/generation, "TMR" for embed script).
            Default "Kimodo".
        return_resolved_name: If True, return (model, resolved_short_key). If False,
            return only the model.

    Returns:
        Loaded model in eval mode, or (model, resolved short key) if
        return_resolved_name is True.

    Raises:
        ValueError: If modelname is not in AVAILABLE_MODELS and cannot be resolved.
        FileNotFoundError: If config.yaml is missing in the checkpoint folder.
    """
    if modelname is None:
        modelname = DEFAULT_MODEL
    if modelname not in AVAILABLE_MODELS:
        if default_family is not None:
            modelname = resolve_model_name(modelname, default_family)
        else:
            raise ValueError(
                f"""The model is not recognized.
            Please choose between: {AVAILABLE_MODELS}"""
            )

    resolved_modelname = modelname

    # In case, we specify a custom checkpoint directory
    configured_checkpoint_dir = get_env_var("CHECKPOINT_DIR")
    if configured_checkpoint_dir:
        print(f"CHECKPOINT_DIR is set to {configured_checkpoint_dir}, checking the local cache...")
        # Checkpoint folders are named by display name (e.g. Kimodo-SOMA-RP-v1)
        info = get_model_info(modelname)
        checkpoint_folder_name = info.display_name if info is not None else modelname
        model_path = Path(configured_checkpoint_dir) / checkpoint_folder_name
        if not model_path.exists() and modelname != checkpoint_folder_name:
            # Fallback: try short_key for backward compatibility
            model_path = Path(configured_checkpoint_dir) / modelname
        if not model_path.exists():
            print(f"Model folder not found at '{model_path}', downloading it from Hugging Face...")
            model_path = _resolve_hf_model_path(modelname)
    else:
        # Otherwise, we load the model from the local cache or download it from Hugging Face.
        model_path = _resolve_hf_model_path(modelname)

    model_config_path = model_path / "config.yaml"
    if not model_config_path.exists():
        raise FileNotFoundError(f"The model checkpoint folder exists but config.yaml is missing: {model_config_path}")

    model_conf = OmegaConf.load(model_config_path)

    if modelname in TMR_MODELS:
        # Same process at the moment for TMR and Kimodo
        pass

    text_encoder_url = get_env_var("TEXT_ENCODER_URL", DEFAULT_TEXT_ENCODER_URL)
    try:
        text_encoder_conf = _select_text_encoder_conf(text_encoder_url)
    except Exception as error:
        raise RuntimeError(
            "Failed to prepare the text encoder while loading the model. "
            "Check TEXT_ENCODER_MODE, TEXT_ENCODER_URL, HF_TOKEN/HUGGING_FACE_HUB_TOKEN, "
            "and whether the text encoder server is running or the local model cache is complete. "
            f"Original error: {type(error).__name__}: {error}"
        ) from error

    runtime_conf = OmegaConf.create(
        {
            "checkpoint_dir": str(model_path),
            "text_encoder": text_encoder_conf,
        }
    )
    model_cfg = OmegaConf.to_container(OmegaConf.merge(model_conf, runtime_conf), resolve=True)
    model_cfg.pop("checkpoint_dir", None)

    try:
        model = instantiate_from_dict(model_cfg, overrides={"device": device})
    except Exception as error:
        raise RuntimeError(
            "Kimodo model initialization failed after text encoder setup. "
            "This usually means the base checkpoint, text encoder, or adapter could not be loaded. "
            f"Original error: {type(error).__name__}: {error}"
        ) from error
    if eval_mode:
        model = model.eval()
    if return_resolved_name:
        return model, resolved_modelname
    return model
