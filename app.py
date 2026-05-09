"""Movimento Space: bootstrap native Kimodo demo and redirect to proxy."""
from __future__ import annotations

import importlib.util
import os
import traceback
import threading

import gradio as gr

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

NATIVE_PORT = int(os.environ.get("KIMODO_NATIVE_PORT", "8080"))
os.environ.setdefault("SERVER_NAME", "0.0.0.0")
os.environ["SERVER_PORT"] = str(NATIVE_PORT)
os.environ.setdefault("HF_MODE", "1")
# Avoid local LLM2Vec fallback on Spaces (requires gated Llama weights).
os.environ.setdefault("TEXT_ENCODER_MODE", "api")
# Prefer CPU on ZeroGPU to avoid low-level CUDA init crashes during model load.
os.environ.setdefault("KIMODO_DEVICE", "cpu")

_state: dict[str, object] = {
    "ok": False,
    "error": None,
    "trace": None,
    "demo": None,
}


@spaces.GPU(duration=60)
def _gpu_healthcheck() -> str:
    # Required by ZeroGPU startup policy; native demo does not invoke this.
    return "ok"


def _boot_native_demo() -> None:
    try:
        if importlib.util.find_spec("viser") is None:
            raise RuntimeError("Missing dependency: viser")

        import kimodo
        from kimodo.demo.app import Demo

        print(f"[movimento][boot] kimodo_module={getattr(kimodo, '__file__', 'unknown')}")
        print(f"[movimento][boot] demo_module={getattr(importlib.util.find_spec('kimodo.demo.app'), 'origin', 'unknown')}")
        _state["demo"] = Demo()
        _state["ok"] = True
        _state["error"] = None
        _state["trace"] = None
    except Exception as exc:  # noqa: BLE001
        _state["ok"] = False
        _state["error"] = str(exc)
        _state["trace"] = traceback.format_exc(limit=12)
        print("[movimento][boot][fatal] native demo failed to start")
        print(_state["trace"])


threading.Thread(target=_boot_native_demo, daemon=True).start()


def _status_markdown() -> str:
    if bool(_state.get("ok")):
        return f"Native demo ready. Redirecting to /proxy/{NATIVE_PORT}/ ..."
    err = _state.get("error")
    if err:
        return f"Native demo failed to start: {err}"
    return f"Starting native demo on /proxy/{NATIVE_PORT}/ ..."


def _redirect_html() -> str:
    target = f"/proxy/{NATIVE_PORT}/"
    return (
        "<div style='padding:8px 0;color:#4d6372;font-size:13px;'>Preparing native UI...</div>"
        f"<div><a href='{target}' target='_self' style='font-size:14px;'>Open native UI now</a></div>"
        "<script>"
        "(function(){"
        f"const target='{target}';"
        "async function step(){"
        "try{"
        "const r=await fetch(target,{method:'GET',cache:'no-store'});"
        "if(r.ok){window.top.location.href=target;return;}"
        "}catch(e){}"
        "setTimeout(step,2500);"
        "}"
        "step();"
        "})();"
        "</script>"
    )


def _refresh() -> tuple[str, str]:
    return _status_markdown(), _redirect_html()


with gr.Blocks(title="Movimento") as demo:
    gr.Markdown("# Movimento")
    status_md = gr.Markdown(_status_markdown())
    viewer = gr.HTML(_redirect_html())
    refresh_btn = gr.Button("Refresh UI Status")
    refresh_btn.click(fn=_refresh, inputs=[], outputs=[status_md, viewer])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
