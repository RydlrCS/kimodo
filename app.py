"""Movimento Space entrypoint: run native Kimodo demo directly."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import traceback
import time

try:
    import spaces  # type: ignore
except Exception:
    class _SpacesFallback:
        @staticmethod
        def GPU(*args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

    spaces = _SpacesFallback()

PORT = int(os.environ.get("PORT", "7860"))
os.environ.setdefault("SERVER_NAME", "0.0.0.0")
os.environ["SERVER_PORT"] = str(PORT)
os.environ.setdefault("HF_MODE", "1")
# Avoid local LLM2Vec fallback on Spaces (requires gated Llama weights).
os.environ.setdefault("TEXT_ENCODER_MODE", "api")
os.environ.setdefault("TEXT_ENCODER", "llm2vec")
os.environ.setdefault("LLM2VEC_BASE_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
os.environ.setdefault(
    "LLM2VEC_PEFT_MODEL",
    "McGill-NLP/LLM2Vec-Meta-Llama-31-8B-Instruct-mntp-supervised",
)
hf_token = os.environ.get("HF_TOKEN")
if hf_token:
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", hf_token)
    os.environ.setdefault("HF_HUB_TOKEN", hf_token)
    os.environ.setdefault("HUGGINGFACEHUB_API_TOKEN", hf_token)
TEXT_ENCODER_PORT = int(os.environ.get("TEXT_ENCODER_PORT", "9550"))
TEXT_ENCODER_SOURCE = os.environ.get("TEXT_ENCODER_SOURCE", "local").strip().lower()
if TEXT_ENCODER_SOURCE not in {"local", "remote"}:
    raise RuntimeError("TEXT_ENCODER_SOURCE must be 'local' or 'remote'.")
if TEXT_ENCODER_SOURCE == "local":
    os.environ.setdefault("TEXT_ENCODER_URL", f"http://127.0.0.1:{TEXT_ENCODER_PORT}/")
elif "TEXT_ENCODER_URL" not in os.environ:
    raise RuntimeError("TEXT_ENCODER_URL is required when TEXT_ENCODER_SOURCE=remote.")
# Prefer CPU on ZeroGPU to avoid low-level CUDA init crashes during model load.
os.environ.setdefault("KIMODO_DEVICE", "cpu")


@spaces.GPU(duration=60)
def _gpu_healthcheck() -> str:
    # Required by ZeroGPU startup policy; native demo does not invoke this.
    return "ok"


def _wait_for_port(port: int, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.5):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Text encoder server failed to bind on 127.0.0.1:{port}")


def _start_text_encoder_server() -> subprocess.Popen:
    env = os.environ.copy()
    env["GRADIO_SERVER_NAME"] = "127.0.0.1"
    env["GRADIO_SERVER_PORT"] = str(TEXT_ENCODER_PORT)
    
    # Ensure HF_TOKEN is explicitly passed to text encoder subprocess
    hf_token = os.environ.get("HF_TOKEN")
    if hf_token:
        env["HF_TOKEN"] = hf_token
        env["HUGGING_FACE_HUB_TOKEN"] = hf_token
        env["HF_HUB_TOKEN"] = hf_token
        env["HUGGINGFACEHUB_API_TOKEN"] = hf_token
        print(f"[movimento][boot] HF_TOKEN set for text encoder (len={len(hf_token)})")
    else:
        print(f"[movimento][boot] WARNING: HF_TOKEN not found in environment")

    print(f"[movimento][boot] starting text encoder server at 127.0.0.1:{TEXT_ENCODER_PORT}")
    proc = subprocess.Popen([sys.executable, "-m", "kimodo.scripts.run_text_encoder_server"], env=env)
    _wait_for_port(TEXT_ENCODER_PORT, timeout_s=45.0)
    print(f"[movimento][boot] text encoder server ready at 127.0.0.1:{TEXT_ENCODER_PORT}")
    return proc


def main() -> None:
    try:
        # Invoke GPU function to satisfy HF Spaces startup requirement.
        _gpu_healthcheck()

        text_encoder_proc = None
        if TEXT_ENCODER_SOURCE == "local":
            # Keep existing embedding pipeline (TextEncoderAPI -> local llm2vec server).
            text_encoder_proc = _start_text_encoder_server()
        else:
            print(f"[movimento][boot] using remote text encoder: {os.environ['TEXT_ENCODER_URL']}")

        import kimodo
        from kimodo.demo.app import Demo

        print(f"[movimento][boot] kimodo_module={getattr(kimodo, '__file__', 'unknown')}")
        print(f"[movimento][boot] mode=native_direct port={PORT}")
        if text_encoder_proc is not None:
            print(f"[movimento][boot] text_encoder_pid={text_encoder_proc.pid}")
        Demo()

        # Keep the process alive while Viser serves on SERVER_PORT.
        while True:
            time.sleep(3600)
    except Exception:  # noqa: BLE001
        print("[movimento][boot][fatal] native demo failed to start")
        print(traceback.format_exc(limit=12))
        raise


if __name__ == "__main__":
    main()
