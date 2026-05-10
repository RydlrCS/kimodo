# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import os

import gradio as gr
import numpy as np
from huggingface_hub import HfApi

from kimodo.model import resolve_target

from .gradio_theme import get_gradio_theme

os.environ["HF_ENABLE_PARALLEL_LOADING"] = "YES"
DEFAULT_TEXT = "A person walks and falls to the ground."
DEFAULT_SERVER_NAME = "0.0.0.0"
DEFAULT_SERVER_PORT = 9550
DEFAULT_TMP_FOLDER = "/tmp/text_encoder/"
DEFAULT_TEXT_ENCODER = "llm2vec"
TEXT_ENCODER_PRESETS = {
    "llm2vec": {
        "target": "kimodo.model.LLM2VecEncoder",
        "kwargs": {
            "base_model_name_or_path": "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp",
            "peft_model_name_or_path": "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised",
            "dtype": "bfloat16",
            "llm_dim": 4096,
        },
        "display_name": "LLM2Vec",
    }
}


def _get_hf_token() -> str | None:
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("HF_HUB_TOKEN")
        or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    )


def _validate_text_encoder_startup(text_encoder_name: str) -> None:
    """Fail fast before launching Gradio if the text encoder cannot be resolved."""
    if text_encoder_name not in TEXT_ENCODER_PRESETS:
        available = ", ".join(sorted(TEXT_ENCODER_PRESETS))
        raise ValueError(f"Unknown TEXT_ENCODER='{text_encoder_name}'. Available: {available}")

    preset = TEXT_ENCODER_PRESETS[text_encoder_name]
    token = _get_hf_token()
    text_encoders_dir = os.environ.get("TEXT_ENCODERS_DIR")

    if text_encoders_dir:
        base_model_path = os.path.join(text_encoders_dir, preset["kwargs"]["base_model_name_or_path"])
        peft_model_path = os.path.join(text_encoders_dir, preset["kwargs"]["peft_model_name_or_path"])
        missing = [path for path in (base_model_path, peft_model_path) if not os.path.exists(path)]
        if missing:
            raise RuntimeError(
                "TEXT_ENCODERS_DIR is set, but the following local model paths are missing: "
                + ", ".join(missing)
            )
        return

    if not token:
        raise RuntimeError(
            "HF token is missing. Set one of HF_TOKEN, HUGGING_FACE_HUB_TOKEN, HF_HUB_TOKEN, or "
            "HUGGINGFACEHUB_API_TOKEN before starting the text encoder server."
        )

    api = HfApi()
    for repo_id, label in (
        (preset["kwargs"]["base_model_name_or_path"], "base model"),
        (preset["kwargs"]["peft_model_name_or_path"], "PEFT adapter"),
    ):
        try:
            api.model_info(repo_id=repo_id, token=token)
        except Exception as error:
            raise RuntimeError(f"Failed to access {label} '{repo_id}' with the configured HF token: {error}") from error


class DemoWrapper:
    def __init__(self, text_encoder_name, tmp_folder):
        self.text_encoder_name = text_encoder_name
        self.text_encoder = None
        self.init_error = None
        self.tmp_folder = tmp_folder

    def _get_text_encoder(self):
        if self.text_encoder is not None:
            return self.text_encoder
        if self.init_error is not None:
            raise RuntimeError(self.init_error)
        try:
            self.text_encoder = _build_text_encoder(self.text_encoder_name)
            return self.text_encoder
        except Exception as error:
            self.init_error = error
            raise

    def __call__(self, text, filename, progress=gr.Progress()):
        try:
            text_encoder = self._get_text_encoder()
        except Exception as error:
            output_title = gr.Markdown(visible=True, value="## Encoder initialization failed")
            output_text = gr.Markdown(
                visible=True,
                value=(
                    "Text encoder could not initialize. "
                    "If you use gated Hugging Face models, configure a valid HF token in the runtime env.\n\n"
                    f"Error: `{type(error).__name__}: {error}`"
                ),
            )
            download = gr.DownloadButton(visible=False)
            return download, output_title, output_text

        # Compute text embedding
        tensor, length = text_encoder(text)
        embedding = tensor[:length]
        embedding = embedding.cpu().numpy()

        # Save text embedding
        path = os.path.join(self.tmp_folder, filename)
        np.save(path, embedding)

        output_title = gr.Markdown(visible=True)
        output_text = gr.Markdown(visible=True, value=f"Text: {text}")
        download = gr.DownloadButton(visible=True, value=path)
        return download, output_title, output_text


def _get_env(name: str, default):
    return os.getenv(name, default)


def _build_text_encoder(name: str):
    if name not in TEXT_ENCODER_PRESETS:
        available = ", ".join(sorted(TEXT_ENCODER_PRESETS))
        raise ValueError(f"Unknown TEXT_ENCODER='{name}'. Available: {available}")
    preset = TEXT_ENCODER_PRESETS[name]
    target_cls = resolve_target(preset["target"])
    return target_cls(**preset["kwargs"])


def parse_args():
    parser = argparse.ArgumentParser(description="Run text encoder Gradio server.")
    parser.add_argument(
        "--text-encoder",
        default=_get_env("TEXT_ENCODER", DEFAULT_TEXT_ENCODER),
        choices=sorted(TEXT_ENCODER_PRESETS.keys()),
        help="Text encoder preset.",
    )
    parser.add_argument(
        "--tmp-folder",
        default=_get_env("TEXT_ENCODER_TMP_FOLDER", DEFAULT_TMP_FOLDER),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    server_name = _get_env("GRADIO_SERVER_NAME", DEFAULT_SERVER_NAME)
    server_port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT", str(DEFAULT_SERVER_PORT)))
    theme, css = get_gradio_theme()
    os.makedirs(args.tmp_folder, exist_ok=True)
    display_name = TEXT_ENCODER_PRESETS[args.text_encoder]["display_name"]

    if _get_env("TEXT_ENCODER_VALIDATE_STARTUP", "1") != "0":
        _validate_text_encoder_startup(args.text_encoder)
    
    # Suppress model loading during DemoWrapper initialization to allow graceful degradation
    # Model will be loaded lazily on first request
    demo_wrapper_fn = DemoWrapper(args.text_encoder, args.tmp_folder)

    with gr.Blocks(title="Text encoder", css=css, theme=theme) as demo:
        gr.Markdown(f"# Text encoder: {display_name}")
        gr.Markdown("## Description")
        gr.Markdown("Get a embeddings from a text.")

        gr.Markdown("## Inputs")
        with gr.Row():
            text = gr.Textbox(
                placeholder="Type the motion you want to generate with a sentence",
                show_label=True,
                label="Text prompt",
                value=DEFAULT_TEXT,
                type="text",
            )
        with gr.Row(scale=3):
            with gr.Column(scale=1):
                btn = gr.Button("Encode", variant="primary")
            with gr.Column(scale=1):
                clear = gr.Button("Clear", variant="secondary")
            with gr.Column(scale=3):
                pass

        output_title = gr.Markdown("## Outputs", visible=False)
        output_text = gr.Markdown("", visible=False)
        with gr.Row(scale=3):
            with gr.Column(scale=1):
                download = gr.DownloadButton("Download", variant="primary", visible=False)
            with gr.Column(scale=4):
                pass

        filename = gr.Textbox(
            visible=False,
            value="embedding.npy",
        )

        def clear_fn():
            return [
                gr.DownloadButton(visible=False),
                gr.Markdown(visible=False),
                gr.Markdown(visible=False),
            ]

        outputs = [download, output_title, output_text]

        gr.on(
            triggers=[text.submit, btn.click],
            fn=clear_fn,
            inputs=None,
            outputs=outputs,
        ).then(
            fn=demo_wrapper_fn,
            inputs=[text, filename],
            outputs=outputs,
        )

        def download_file():
            return gr.DownloadButton()

        download.click(
            fn=download_file,
            inputs=None,
            outputs=[download],
        )
        clear.click(fn=clear_fn, inputs=None, outputs=outputs)

    demo.launch(server_name=server_name, server_port=server_port)


if __name__ == "__main__":
    main()
