"""Card 10: Gradio Space frontend shell for prompt->script->execution flow."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import gradio as gr

from kimodo.model import DEFAULT_MODEL, load_model
from kimodo.pipeline.scheduler_runtime import run_scheduled_scene
from kimodo.planner import QwenPlannerAdapter
from kimodo.runtime import runtime_health_report
from kimodo.schemas import CharacterDefinition, CharacterGenerationState, GeneratorRequest, PlannerRequest, PlannerResponse

from .gradio_theme import get_gradio_theme


@dataclass
class FrontendConfig:
    execution_mode: str
    default_model: str
    default_scene_id: str = "space_scene"


class _FakeKimodoModel:
    """Fast fallback model for cold-start demo flow."""

    def __call__(self, prompts, num_frames, **kwargs):
        return {
            "posed_joints": [[0.0]],
            "global_rot_mats": [[0.0]],
            "foot_contacts": [[0.0]],
            "prompts": prompts,
            "num_frames": num_frames,
            "meta": kwargs,
        }


_MODEL_CACHE: dict[str, Any] = {}


def build_kimodo_iframe_html(space_url: str, *, height_px: int = 760) -> str:
    """Build embeddable iframe HTML for the upstream Kimodo UI."""
    url = (space_url or "").strip() or "https://nvidia-kimodo.hf.space"
    height = max(480, int(height_px))
    return (
        "<div style='border:1px solid #d0dde6;border-radius:12px;overflow:hidden;'>"
        f"<iframe src='{url}' title='Kimodo UI' "
        "style='width:100%;border:0;' "
        f"height='{height}' loading='lazy' referrerpolicy='origin'></iframe>"
        "</div>"
    )


def _parse_character_ids(raw: str, count: int) -> list[str]:
    items = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if not items:
        items = [f"char_{i+1}" for i in range(count)]
    if len(items) < count:
        items.extend(f"char_{i+1}" for i in range(len(items), count))
    return items[:count]


def _build_planner_request(scene_id: str, prompt: str, character_ids: list[str], duration_limit_sec: float) -> PlannerRequest:
    return PlannerRequest(
        scene_id=scene_id,
        user_prompt=prompt,
        duration_limit_sec=duration_limit_sec,
        characters=[CharacterDefinition(character_id=item, skeleton_type="soma") for item in character_ids],
    )


def _planner_response_to_generator_request(response: PlannerResponse, seed: int) -> GeneratorRequest:
    characters: list[CharacterGenerationState] = []
    for character_id, segments in response.scripts.items():
        characters.append(
            CharacterGenerationState(
                character_id=character_id,
                skeleton_type="soma",
                segments=segments,
            )
        )
    return GeneratorRequest(
        scene_id=response.scene_id,
        characters=characters,
        seed=seed,
        num_samples=1,
    )


def _get_or_load_model(config: FrontendConfig, requested_model: str, requested_device: Optional[str]) -> Any:
    if config.execution_mode == "simulate":
        return _FakeKimodoModel()

    cache_key = f"{requested_model}:{requested_device or 'auto'}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    report = runtime_health_report(requested_device)
    model = load_model(requested_model, device=report.selected_device)
    _MODEL_CACHE[cache_key] = model
    return model


def plan_script(
    scene_id: str,
    prompt: str,
    character_count: int,
    character_ids_raw: str,
    duration_limit_sec: float,
) -> tuple[str, str]:
    start = time.time()
    character_ids = _parse_character_ids(character_ids_raw, int(character_count))
    request = _build_planner_request(scene_id.strip() or "space_scene", prompt, character_ids, duration_limit_sec)
    adapter = QwenPlannerAdapter()
    response = adapter.plan(request)
    payload = json.dumps(response.model_dump(), indent=2)
    elapsed_ms = int((time.time() - start) * 1000)
    status = f"Planner: {response.status.upper()} in {elapsed_ms} ms | characters={len(response.scripts)}"
    return payload, status


def execute_script(
    planned_script_json: str,
    seed: int,
    fps: int,
    requested_device: str,
    execution_mode: str,
    model_name: str,
) -> tuple[str, dict[str, Any], str]:
    if not planned_script_json.strip():
        return "", {"timeline": []}, "Execution failed: script preview is empty"

    try:
        response = PlannerResponse.model_validate_json(planned_script_json)
    except Exception as exc:  # pylint: disable=broad-except
        return "", {"timeline": []}, f"Execution failed: invalid planner JSON ({exc})"

    try:
        config = FrontendConfig(execution_mode=execution_mode, default_model=model_name)
        model = _get_or_load_model(config, model_name, requested_device)
        request = _planner_response_to_generator_request(response, seed=seed)
        result = run_scheduled_scene(model, request, fps=float(fps), seed=seed)

        summary = {
            "scene_id": response.scene_id,
            "characters": list(result.outputs.keys()),
            "errors": result.errors,
            "state_hash_count": len(result.state_hashes),
            "interaction_count": len(result.interactions),
            "completed_segments": result.completed_segments,
        }

        timeline = [
            {
                "frame": index,
                "state_hash": state_hash,
            }
            for index, state_hash in enumerate(result.state_hashes)
        ]

        status = (
            f"Execution: OK | chars={len(summary['characters'])} "
            f"frames={summary['state_hash_count']} interactions={summary['interaction_count']}"
        )
        return json.dumps(summary, indent=2), {"timeline": timeline}, status
    except Exception as exc:  # pylint: disable=broad-except
        return "", {"timeline": []}, f"Execution failed: {exc}"


def render_frame(frame_idx: int, playback_state: dict[str, Any]) -> str:
    timeline = playback_state.get("timeline") or []
    if not timeline:
        return "No execution timeline yet. Click Execute Scene first."
    bounded = max(0, min(int(frame_idx), len(timeline) - 1))
    frame = timeline[bounded]
    return f"Frame {frame['frame']} | state_hash={frame['state_hash']}"


def create_app() -> gr.Blocks:
    theme, css = get_gradio_theme(remove_gradio_footer=True)

    execution_mode = os.environ.get("SPACE_EXECUTION_MODE", "simulate").strip().lower()
    default_model = os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL)
    kimodo_ui_url = os.environ.get("KIMODO_UI_URL", "https://nvidia-kimodo.hf.space").strip()

    app_css = css + """
    :root {
      --brand-primary: #0d3b66;
      --brand-accent: #f95738;
      --brand-muted: #faf6f1;
    }
    .movimento-hero {
      background: linear-gradient(130deg, var(--brand-muted) 0%, #e5f4f9 100%);
      border: 1px solid #d9e7ef;
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 12px;
    }
    .movimento-hero h1 {
      color: var(--brand-primary);
      margin: 0;
    }
    .movimento-hero p {
      margin: 6px 0 0 0;
      color: #264653;
    }
    """

    with gr.Blocks(title="Movimento", css=app_css, theme=theme) as demo:
        gr.HTML(
            """
            <div class=\"movimento-hero\">
              <h1>Movimento - Multi-Character Motion Copilot</h1>
              <p>Prompt -> Qwen script plan -> scheduled execution trace. Built for lablab.ai x AMD.</p>
            </div>
            """
        )

        playback_state = gr.State({"timeline": []})

        with gr.Tabs():
            with gr.Tab("Multi-Character Copilot"):
                with gr.Row():
                    scene_id = gr.Textbox(label="Scene ID", value="space_scene")
                    model_name = gr.Textbox(label="Model", value=default_model)
                    requested_device = gr.Textbox(label="Device (auto/cpu/amd/rocm/cuda)", value="auto")

                prompt = gr.Textbox(
                    label="Story Prompt",
                    lines=4,
                    value="Two characters meet, greet each other, and walk in sync while a third observes.",
                )

                with gr.Row():
                    character_count = gr.Slider(label="Characters", minimum=1, maximum=6, value=3, step=1)
                    character_ids = gr.Textbox(label="Character IDs (comma-separated)", value="lead,support,observer")
                    duration_limit_sec = gr.Slider(label="Duration Limit (sec)", minimum=10, maximum=180, value=60, step=5)

                plan_button = gr.Button("Plan Script", variant="primary")
                script_preview = gr.Code(label="Script Preview (JSON)", language="json")
                status_line = gr.Textbox(label="Status", interactive=False)

                with gr.Row():
                    seed = gr.Number(label="Seed", value=42, precision=0)
                    fps = gr.Slider(label="Playback FPS", minimum=10, maximum=60, value=30, step=1)
                    execution_mode_box = gr.Dropdown(
                        label="Execution Mode",
                        choices=["simulate", "model"],
                        value=execution_mode if execution_mode in {"simulate", "model"} else "simulate",
                    )

                execute_button = gr.Button("Execute Scene")
                execution_summary = gr.Code(label="Execution Summary", language="json")

                with gr.Row():
                    frame_slider = gr.Slider(label="Frame", minimum=0, maximum=1, value=0, step=1)
                    frame_info = gr.Textbox(label="Playback", interactive=False)

                prev_btn = gr.Button("Prev Frame")
                next_btn = gr.Button("Next Frame")

            with gr.Tab("Kimodo Native UI"):
                gr.Markdown(
                    "Use the original Kimodo UI for visual authoring, while keeping multi-character planning "
                    "and scheduler flow in this Space."
                )
                gr.Markdown(f"Kimodo UI URL: {kimodo_ui_url}")
                gr.HTML(build_kimodo_iframe_html(kimodo_ui_url, height_px=820))

        def _update_frame_slider(playback: dict[str, Any]) -> gr.Slider:
            timeline = playback.get("timeline") or []
            max_frame = max(0, len(timeline) - 1)
            return gr.Slider(label="Frame", minimum=0, maximum=max_frame, value=0, step=1)

        def _prev_frame(cur: float) -> float:
            return max(0, int(cur) - 1)

        def _next_frame(cur: float, playback: dict[str, Any]) -> float:
            max_frame = max(0, len((playback or {}).get("timeline") or []) - 1)
            return min(max_frame, int(cur) + 1)

        plan_button.click(
            fn=plan_script,
            inputs=[scene_id, prompt, character_count, character_ids, duration_limit_sec],
            outputs=[script_preview, status_line],
        )

        execute_button.click(
            fn=execute_script,
            inputs=[script_preview, seed, fps, requested_device, execution_mode_box, model_name],
            outputs=[execution_summary, playback_state, status_line],
        ).then(
            fn=_update_frame_slider,
            inputs=[playback_state],
            outputs=[frame_slider],
        ).then(
            fn=render_frame,
            inputs=[frame_slider, playback_state],
            outputs=[frame_info],
        )

        frame_slider.change(fn=render_frame, inputs=[frame_slider, playback_state], outputs=[frame_info])
        prev_btn.click(fn=_prev_frame, inputs=[frame_slider], outputs=[frame_slider]).then(
            fn=render_frame,
            inputs=[frame_slider, playback_state],
            outputs=[frame_info],
        )
        next_btn.click(fn=_next_frame, inputs=[frame_slider, playback_state], outputs=[frame_slider]).then(
            fn=render_frame,
            inputs=[frame_slider, playback_state],
            outputs=[frame_info],
        )

    return demo


def main() -> None:
    server_name = os.environ.get("GRADIO_SERVER_NAME", os.environ.get("SERVER_NAME", "0.0.0.0"))
    server_port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT", "7860"))
    favicon_path = Path(__file__).resolve().parents[1] / "assets" / "demo" / "nvidia_logo.png"

    demo = create_app()
    launch_kwargs = {
        "server_name": server_name,
        "server_port": server_port,
    }
    if favicon_path.exists():
        launch_kwargs["favicon_path"] = str(favicon_path)

    demo.launch(**launch_kwargs)


if __name__ == "__main__":
    main()