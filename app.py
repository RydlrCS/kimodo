import os
import json
from typing import Any

import gradio as gr


def _parse_character_ids(raw: str, count: int) -> list[str]:
    items = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if not items:
        items = [f"char_{i + 1}" for i in range(count)]
    if len(items) < count:
        items.extend(f"char_{i + 1}" for i in range(len(items), count))
    return items[:count]


def plan_script(scene_id: str, prompt: str, characters: int, character_ids_raw: str, transition: str, duration_sec: int) -> str:
    cleaned = (prompt or "").strip() or "Two characters wave and then walk together"
    count = max(1, int(characters))
    ids = _parse_character_ids(character_ids_raw, count)

    segments = []
    segment_duration = max(1.0, float(duration_sec) / 2.0)
    for idx, cid in enumerate(ids):
        target = ids[(idx + 1) % len(ids)] if len(ids) > 1 else None
        segments.append(
            {
                "character_id": cid,
                "segments": [
                    {
                        "segment_id": 0,
                        "action_text": f"{cid} starts: {cleaned}",
                        "duration_sec": segment_duration,
                        "transition_policy": "smooth",
                        "interaction_target": target,
                    },
                    {
                        "segment_id": 1,
                        "action_text": f"{cid} continues with {transition} transition",
                        "duration_sec": segment_duration,
                        "transition_policy": transition,
                        "interaction_target": target,
                    },
                ],
            }
        )

    payload = {
        "scene_id": scene_id.strip() or "space_scene",
        "status": "success",
        "scripts": segments,
        "metadata": {
            "source": "space_frontend_simulation",
            "cards_complete": list(range(0, 11)),
        },
    }
    return json.dumps(payload, indent=2)


def execute_scene(script_json: str, fps: int, seed: int) -> tuple[str, dict[str, Any], str]:
    if not script_json.strip():
        return "", {"timeline": []}, "Execution failed: no script"

    try:
        payload = json.loads(script_json)
    except json.JSONDecodeError as exc:
        return "", {"timeline": []}, f"Execution failed: invalid JSON ({exc})"

    scripts = payload.get("scripts") or []
    characters = [item.get("character_id") for item in scripts if item.get("character_id")]
    frame_count = max(1, int(fps) * 4)
    timeline = [{"frame": i, "state_hash": f"{seed:04d}-{i:05d}"} for i in range(frame_count)]

    summary = {
        "scene_id": payload.get("scene_id", "space_scene"),
        "characters": characters,
        "planner_status": payload.get("status", "unknown"),
        "state_hash_count": len(timeline),
        "interaction_count": max(0, len(characters) - 1),
        "execution_mode": "space-simulated",
    }
    status = (
        f"Execution OK | chars={len(characters)} "
        f"frames={summary['state_hash_count']} interactions={summary['interaction_count']}"
    )
    return json.dumps(summary, indent=2), {"timeline": timeline}, status


def render_frame(frame_idx: int, playback_state: dict[str, Any]) -> str:
    timeline = playback_state.get("timeline") or []
    if not timeline:
        return "No execution timeline yet. Click Execute Scene first."
    bounded = max(0, min(int(frame_idx), len(timeline) - 1))
    frame = timeline[bounded]
    return f"Frame {frame['frame']} | state_hash={frame['state_hash']}"


def _update_slider(playback_state: dict[str, Any]) -> gr.Slider:
    timeline = playback_state.get("timeline") or []
    max_frame = max(0, len(timeline) - 1)
    return gr.Slider(label="Frame", minimum=0, maximum=max_frame, value=0, step=1)


def _prev_frame(current: float) -> float:
    return max(0, int(current) - 1)


def _next_frame(current: float, playback_state: dict[str, Any]) -> float:
    max_frame = max(0, len((playback_state or {}).get("timeline") or []) - 1)
    return min(max_frame, int(current) + 1)


with gr.Blocks(title="Movimento") as demo:
    gr.Markdown("# Movimento")
    gr.Markdown(
        "Card 10 Space frontend: prompt input, script preview, execution status, and playback controls."
    )

    playback_state = gr.State({"timeline": []})

    with gr.Row():
        scene_id = gr.Textbox(label="Scene ID", value="space_scene")
        seed = gr.Number(label="Seed", value=42, precision=0)
        fps = gr.Slider(label="FPS", minimum=10, maximum=60, value=30, step=1)

    with gr.Row():
        prompt = gr.Textbox(label="Scene Prompt", lines=4, placeholder="Two characters greet and sit down")

    with gr.Row():
        characters = gr.Slider(label="Characters", minimum=1, maximum=6, step=1, value=2)
        character_ids = gr.Textbox(label="Character IDs (comma-separated)", value="lead,support")
        transition = gr.Dropdown(
            label="Transition Policy",
            choices=["smooth", "overlap", "hold", "cut"],
            value="smooth",
        )
        duration_sec = gr.Slider(label="Duration (sec)", minimum=10, maximum=120, step=5, value=30)

    plan_btn = gr.Button("Plan Script", variant="primary")
    script_preview = gr.Code(label="Script Preview (JSON)", language="json")
    status = gr.Textbox(label="Status", interactive=False)

    execute_btn = gr.Button("Execute Scene")
    summary = gr.Code(label="Execution Summary", language="json")

    with gr.Row():
        frame_slider = gr.Slider(label="Frame", minimum=0, maximum=1, value=0, step=1)
        frame_info = gr.Textbox(label="Playback", interactive=False)

    prev_btn = gr.Button("Prev Frame")
    next_btn = gr.Button("Next Frame")

    plan_btn.click(
        plan_script,
        inputs=[scene_id, prompt, characters, character_ids, transition, duration_sec],
        outputs=[script_preview],
    ).then(
        lambda: "Planner: SUCCESS",
        outputs=[status],
    )

    execute_btn.click(
        execute_scene,
        inputs=[script_preview, fps, seed],
        outputs=[summary, playback_state, status],
    ).then(
        _update_slider,
        inputs=[playback_state],
        outputs=[frame_slider],
    ).then(
        render_frame,
        inputs=[frame_slider, playback_state],
        outputs=[frame_info],
    )

    frame_slider.change(render_frame, inputs=[frame_slider, playback_state], outputs=[frame_info])
    prev_btn.click(_prev_frame, inputs=[frame_slider], outputs=[frame_slider]).then(
        render_frame,
        inputs=[frame_slider, playback_state],
        outputs=[frame_info],
    )
    next_btn.click(_next_frame, inputs=[frame_slider, playback_state], outputs=[frame_slider]).then(
        render_frame,
        inputs=[frame_slider, playback_state],
        outputs=[frame_info],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
