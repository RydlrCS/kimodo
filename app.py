import os

import gradio as gr


def generate_plan(prompt: str, characters: int, transition: str) -> str:
    cleaned = (prompt or "").strip() or "Two characters wave and then walk together"
    return (
        "Movimento deployment is live on Hugging Face Spaces.\n\n"
        "Requested scene:\n"
        f"- Prompt: {cleaned}\n"
        f"- Characters: {characters}\n"
        f"- Transition preference: {transition}\n\n"
        "Card 0-6 status:\n"
        "- Qwen planning adapter implemented\n"
        "- Deterministic loop scheduler implemented\n"
        "- BONES-SEED ingestion flow implemented\n"
        "- Script-to-Kimodo mapping implemented\n\n"
        "Next step: Card 7 blend quality guardrails with constraint-aware multi-character transitions."
    )


with gr.Blocks(title="Movimento") as demo:
    gr.Markdown("# Movimento")
    gr.Markdown("Text-driven multi-character motion planning for the lablab.ai AMD hackathon.")

    with gr.Row():
        prompt = gr.Textbox(label="Scene Prompt", lines=3, placeholder="Two characters greet and sit down")

    with gr.Row():
        characters = gr.Slider(label="Characters", minimum=1, maximum=6, step=1, value=2)
        transition = gr.Dropdown(
            label="Transition Policy",
            choices=["smooth", "overlap", "hold", "cut"],
            value="smooth",
        )

    run = gr.Button("Generate Plan")
    output = gr.Textbox(label="Planner Output", lines=16)

    run.click(generate_plan, inputs=[prompt, characters, transition], outputs=output)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
