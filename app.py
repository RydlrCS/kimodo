"""Movimento — single-character multi-text-prompt loop powered by Qwen on Fireworks."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Generator

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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_MODEL = "accounts/fireworks/models/qwen3p6-27b"
_BASE  = "https://api.fireworks.ai/inference/v1"

# Colors cycle per batch: blue → red → yellow → green
_BATCH_COLORS = ["#4a90d9", "#e05252", "#f0b429", "#4caf50"]

_SYSTEM = """\
You are a motion-description writer for a single humanoid character in a 3D animation system.
Given a scene context and the character's recent motion history, output ONLY a JSON object:

{"texts": ["<action phrase 1>", ...], "durations": [<seconds float>, ...]}

Rules:
- Return 3 to 5 short, vivid action phrases that flow naturally from each other.
- Each phrase describes one distinct physical motion (e.g. "walks forward briskly", "pivots left and crouches").
- Each duration is between 2.0 and 8.0 seconds.
- texts and durations must have the same length.
- Do NOT repeat phrases from history.
- Return raw JSON only — no markdown, no explanation.
"""

# ---------------------------------------------------------------------------
# Qwen via Fireworks
# ---------------------------------------------------------------------------

def _call_qwen(messages: list[dict]) -> str:
    api_key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FIREWORKS_API_KEY is not set")
    body = json.dumps({
        "model": _MODEL,
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.85,
    }).encode()
    req = urllib.request.Request(
        f"{_BASE}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Fireworks {e.code}: {e.read().decode(errors='ignore')}") from e


def _parse(raw: str) -> dict:
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    text = m.group(1) if m else text
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


def _fallback_batch(offset: int) -> dict:
    phrases = [
        "walks forward at a steady pace",
        "turns smoothly to the left",
        "pauses and surveys the surroundings",
        "steps forward and gestures expressively",
        "crouches down then rises back up",
        "sidesteps to the right with purpose",
    ]
    n = len(phrases)
    return {
        "texts": [phrases[(offset + i) % n] for i in range(3)],
        "durations": [3.0, 3.5, 3.0],
    }


@spaces.GPU(duration=120)
def _generate_next_batch(scene: str, history_json: str) -> tuple[str, str]:
    history: list[str] = json.loads(history_json) if history_json else []
    user_msg = (
        f"Scene: {scene or 'a character moving continuously in 3D space'}\n"
        f"Motion history (do not repeat): {json.dumps(history[-12:])}\n\n"
        "Generate the next batch of motion prompts."
    )
    try:
        raw = _call_qwen([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}])
        batch = _parse(raw)
        if not isinstance(batch.get("texts"), list) or not isinstance(batch.get("durations"), list):
            raise ValueError("Missing texts or durations in response")
        n = min(len(batch["texts"]), len(batch["durations"]))
        batch["texts"] = batch["texts"][:n]
        batch["durations"] = batch["durations"][:n]
    except Exception as exc:  # noqa: BLE001
        batch = _fallback_batch(len(history))
        batch["_error"] = str(exc)

    new_history = history + list(batch["texts"])
    return json.dumps(batch), json.dumps(new_history)


# ---------------------------------------------------------------------------
# Timeline renderer
# ---------------------------------------------------------------------------

def _render_timeline(segments: list[dict]) -> str:
    """Render a Kimodo-style horizontal colored timeline from all segments so far."""
    if not segments:
        return (
            "<div style='padding:20px;color:#6b7280;font-family:monospace;background:#111827;"
            "border-radius:10px;text-align:center;font-size:13px'>"
            "Click Generate — prompts will appear as a coloured timeline</div>"
        )

    total_dur = sum(s["duration"] for s in segments) or 1.0

    blocks = []
    for seg in segments:
        pct = max(4.0, (seg["duration"] / total_dur) * 100)
        color = seg["color"]
        dur_label = f"{seg['duration']:.1f}s"
        text = seg["text"]
        blocks.append(
            f"<div style='flex:{pct:.2f};min-width:90px;background:{color};border-radius:6px;"
            f"margin-right:4px;padding:7px 10px;box-sizing:border-box;overflow:hidden;"
            f"display:flex;flex-direction:column;justify-content:center'>"
            f"<span style='color:rgba(255,255,255,0.85);font-size:11px;font-weight:700;"
            f"font-family:monospace'>{dur_label}</span>"
            f"<span style='color:#fff;font-size:12px;white-space:nowrap;overflow:hidden;"
            f"text-overflow:ellipsis;margin-top:3px'>{text}</span>"
            f"</div>"
        )

    return (
        "<div style='background:#111827;border-radius:10px;padding:14px;overflow-x:auto'>"
        "<div style='font-size:11px;color:#6b7280;font-family:monospace;margin-bottom:8px;"
        "letter-spacing:0.08em'>PROMPTS</div>"
        f"<div style='display:flex;flex-direction:row;align-items:stretch;min-height:68px'>"
        + "".join(blocks) +
        "</div></div>"
    )


# ---------------------------------------------------------------------------
# Generator — loops until Gradio cancels on Stop click
# ---------------------------------------------------------------------------

def generate_loop(
    scene: str,
    history_json: str,
    segments_json: str,
    batch_idx_json: str,
) -> Generator:
    history = history_json or "[]"
    segments: list[dict] = json.loads(segments_json) if segments_json else []
    batch_idx: int = json.loads(batch_idx_json) if batch_idx_json else 0

    while True:
        color = _BATCH_COLORS[batch_idx % len(_BATCH_COLORS)]

        # Emit "thinking" status before the GPU call so the user sees feedback
        yield (
            _render_timeline(segments),
            f"⏳ Generating batch {batch_idx + 1}…",
            history,
            json.dumps(segments),
            json.dumps(batch_idx),
        )

        batch_json, history = _generate_next_batch(scene, history)
        batch = json.loads(batch_json)
        texts    = batch.get("texts", [])
        durations = batch.get("durations", [])
        error    = batch.get("_error")

        for t, d in zip(texts, durations):
            segments.append({"text": t, "duration": d, "color": color})

        status = (
            f"✓ Batch {batch_idx + 1} — {len(texts)} prompts via {_MODEL.split('/')[-1]}"
            if not error
            else f"⚠ Batch {batch_idx + 1} fallback — {error}"
        )

        batch_idx += 1
        yield (
            _render_timeline(segments),
            status,
            history,
            json.dumps(segments),
            json.dumps(batch_idx),
        )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

_KIMODO_SRC = os.environ.get("KIMODO_UI_URL", "https://nvidia-kimodo.hf.space").strip()

_empty_timeline = _render_timeline([])

with gr.Blocks(title="Movimento") as demo:

    gr.HTML("""
    <div style="background:linear-gradient(135deg,#0d3b66,#1b6ca8);padding:16px 22px;
                border-radius:10px;margin-bottom:10px">
      <h2 style="color:#fff;margin:0;font-size:22px">Movimento</h2>
      <p style="color:#c8e6ff;margin:4px 0 0;font-size:13px">
        Single character &middot; <strong>Qwen3&#8209;p6&nbsp;27B</strong> on Fireworks AI &middot;
        Generates motion prompts continuously — click&nbsp;<strong>Stop</strong> to pause
      </p>
    </div>
    """)

    history_state   = gr.State("[]")
    segments_state  = gr.State("[]")
    batch_idx_state = gr.State("0")

    scene_box = gr.Textbox(
        label="Scene / character context",
        value="A lone figure moving through an empty plaza",
        lines=2,
    )

    with gr.Row():
        generate_btn = gr.Button("▶  Generate", variant="primary",    scale=4, min_width=160)
        stop_btn     = gr.Button("⏹  Stop",     variant="stop",       scale=1, min_width=100)
        clear_btn    = gr.Button("✕  Clear",    variant="secondary",  scale=1, min_width=100)

    timeline_html = gr.HTML(_empty_timeline)
    status_line   = gr.Textbox(label="Status", interactive=False, lines=1)

    gr.HTML(
        "<div style='border:1px solid #c0d8ea;border-radius:10px;overflow:hidden;margin-top:14px'>"
        f"<iframe src='{_KIMODO_SRC}' style='width:100%;border:0' height='820' "
        "loading='lazy' title='Kimodo 3D'></iframe></div>"
    )

    # Wiring
    click_event = generate_btn.click(
        fn=generate_loop,
        inputs=[scene_box, history_state, segments_state, batch_idx_state],
        outputs=[timeline_html, status_line, history_state, segments_state, batch_idx_state],
    )

    stop_btn.click(fn=None, cancels=[click_event])

    def _clear():
        return _render_timeline([]), "", "[]", "[]", "0"

    clear_btn.click(
        fn=_clear,
        inputs=[],
        outputs=[timeline_html, status_line, history_state, segments_state, batch_idx_state],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
