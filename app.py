"""Movimento Space: lightweight host for NVIDIA Kimodo native UI."""
from __future__ import annotations

import os
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


# Keep a GPU-decorated function so HF Spaces startup checks pass on zero-a10g.
@spaces.GPU(duration=60)
def _gpu_healthcheck() -> str:
    return "ok"


def _viewer_html() -> str:
    src = os.environ.get("KIMODO_UI_URL", "https://nvidia-kimodo.hf.space").strip()
    return (
        "<div style='border:1px solid #d9e7ef;border-radius:12px;overflow:hidden;'>"
        f"<iframe src='{src}' title='Kimodo Native UI' style='width:100%;border:0' "
        "height='900' loading='lazy'></iframe>"
        "</div>"
    )


with gr.Blocks(title="Movimento") as demo:
    gr.Markdown("# Movimento")
    gr.Markdown("Native NVIDIA Kimodo UI is embedded below.")
    gr.HTML(_viewer_html())


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
