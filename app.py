"""Movimento Space entrypoint: run native Kimodo demo directly."""
from __future__ import annotations

import os
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
# Prefer CPU on ZeroGPU to avoid low-level CUDA init crashes during model load.
os.environ.setdefault("KIMODO_DEVICE", "cpu")


@spaces.GPU(duration=60)
def _gpu_healthcheck() -> str:
    # Required by ZeroGPU startup policy; native demo does not invoke this.
    return "ok"


def main() -> None:
    try:
        import kimodo
        from kimodo.demo.app import Demo

        print(f"[movimento][boot] kimodo_module={getattr(kimodo, '__file__', 'unknown')}")
        print(f"[movimento][boot] mode=native_direct port={PORT}")
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
