"""Movimento Space: boot native Kimodo demo UI and embed via proxy."""
from __future__ import annotations

import importlib.util
import os
import threading
import traceback

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
os.environ.setdefault("SERVER_PORT", str(NATIVE_PORT))
os.environ.setdefault("HF_MODE", "1")

_state: dict[str, object] = {
    "ok": False,
    "error": None,
    "trace": None,
    "demo": None,
}


def _boot_native_demo() -> None:
    try:
        if importlib.util.find_spec("viser") is None:
            raise RuntimeError("Missing dependency: viser")

        from kimodo.demo.app import Demo

        _state["demo"] = Demo()
        _state["ok"] = True
        _state["error"] = None
        _state["trace"] = None
    except Exception as exc:  # noqa: BLE001
        _state["ok"] = False
        _state["error"] = str(exc)
        _state["trace"] = traceback.format_exc(limit=8)


threading.Thread(target=_boot_native_demo, daemon=True).start()


# Keep a GPU-decorated function so HF startup checks pass.
@spaces.GPU(duration=60)
def _gpu_healthcheck() -> str:
    return "ok"


def _viewer_html() -> str:
    if bool(_state.get("ok")):
        src = f"/proxy/{NATIVE_PORT}/"
    else:
        src = os.environ.get("KIMODO_UI_URL", "https://nvidia-kimodo.hf.space").strip()
    return (
        "<div style='border:1px solid #d9e7ef;border-radius:12px;overflow:hidden;'>"
        f"<iframe src='{src}' title='Kimodo UI' style='width:100%;border:0' "
        "height='920' loading='lazy'></iframe>"
        "</div>"
    )


def _status_markdown() -> str:
    if bool(_state.get("ok")):
        return f"Native demo running on /proxy/{NATIVE_PORT}/."
    err = _state.get("error")
    if err:
        return (
            "Native demo unavailable, showing fallback UI.  "
            f"Reason: {err}"
        )
    return "Starting native demo..."


def _refresh() -> tuple[str, str]:
    return _status_markdown(), _viewer_html()


with gr.Blocks(title="Movimento") as demo:
    gr.Markdown("# Movimento")
    status_md = gr.Markdown(_status_markdown())
    viewer = gr.HTML(_viewer_html())
    refresh_btn = gr.Button("Refresh UI Status")
    refresh_btn.click(fn=_refresh, inputs=[], outputs=[status_md, viewer])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
