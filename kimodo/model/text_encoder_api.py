# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Remote text encoder API client (Gradio) for motion generation."""

import logging

import os

import numpy as np
import torch
from gradio_client import Client

# Suppress the [httpx] logs (GET requests)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Suppress internal gradio_client logs
logging.getLogger("gradio_client").setLevel(logging.WARNING)


class TextEncoderAPI:
    """Text encoder API client for motion generation."""

    def __init__(self, url: str):
        self.url = url
        self.client = None
        self.device = "cpu"
        self.dtype = torch.float

    def _get_client(self) -> Client:
        """Lazily create the Gradio client, retrying until the server is ready."""
        if self.client is not None:
            return self.client
        import time

        client_timeout_sec = int(os.environ.get("TEXT_ENCODER_CLIENT_TIMEOUT_SEC", "180"))
        deadline = time.monotonic() + client_timeout_sec
        last_exc: Exception | None = None
        delay = 2.0
        while time.monotonic() < deadline:
            try:
                self.client = Client(self.url, verbose=False)
                return self.client
            except Exception as exc:
                last_exc = exc
                print(f"[text_encoder_api] Client init failed ({exc}), retrying in {delay:.0f}s …")
                time.sleep(delay)
                delay = min(delay * 1.5, 20.0)
        raise RuntimeError(
            f"Text encoder at {self.url!r} did not become ready within {client_timeout_sec}s. "
            f"Last error: {last_exc}"
        )

    def _create_np_random_name(self):
        import uuid

        return str(uuid.uuid4()) + ".npy"

    def to(self, device=None, dtype=None):
        if device is not None:
            self.device = device
        if dtype is not None:
            self.dtype = dtype
        return self

    def _extract_result_path(self, result):
        """Extract npy path from heterogeneous gradio_client responses with error detection."""
        candidates = []
        if isinstance(result, (list, tuple)):
            candidates = list(result)
        elif result is not None:
            candidates = [result]

        for item in candidates:
            # Check for error messages first (e.g., "## Encoder initialization failed")
            if isinstance(item, str):
                if item and item.startswith("##"):
                    # This is an error message from the Gradio server
                    error_msg = item.replace("##", "").strip()
                    if "initialization failed" in error_msg.lower():
                        raise RuntimeError(
                            f"Text encoder initialization failed. This usually indicates:\n"
                            f"  - Missing or invalid HF_TOKEN for gated models (Llama-3)\n"
                            f"  - Poor network connectivity during model download\n"
                            f"  Original error: {error_msg}"
                        )
                    raise RuntimeError(f"Text encoder API error: {error_msg}")
                if "failed" in item.lower() or "error" in item.lower():
                    raise RuntimeError(f"Text encoder API error: {item}")
                if item and item.endswith(".npy"):
                    return item
                if item:
                    # Log unexpected string for debugging
                    print(f"[text_encoder_api] unexpected string response: {item[:100]}")
                    
            if isinstance(item, dict):
                for key in ("value", "path", "name"):
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        # Check for errors in dict values too
                        if "initialization failed" in value.lower():
                            raise RuntimeError(
                                f"Text encoder initialization failed. This usually indicates:\n"
                                f"  - Missing or invalid HF_TOKEN for gated models (Llama-3)\n"
                                f"  - Poor network connectivity during model download"
                            )
                        if value.startswith("##") or "failed" in value.lower() or "error" in value.lower():
                            raise RuntimeError(f"Text encoder API error: {value}")
                        if value.endswith(".npy"):
                            return value

        raise RuntimeError(f"Text encoder API returned unexpected payload: {result!r}")

    def __call__(self, texts):
        """Encode text prompts into tensors.

        Args:
            texts (str | list[str]): text prompts to encode

        Returns:
            tuple[torch.Tensor, list[int]]: encoded text tensors and their lengths
        """
        if isinstance(texts, str):
            texts = [texts]

        tensors = []
        lengths = []
        for text in texts:
            filename = self._create_np_random_name()

            # Use a long result timeout to tolerate text-encoder cold-start (LLM2Vec model load ~60-120s).
            result = self._get_client().submit(
                text=text,
                filename=filename,
                api_name="/DemoWrapper",
            ).result(timeout=300)
            path = self._extract_result_path(result)
            tensor = np.load(path)
            length = tensor.shape[0]

            tensors.append(tensor)
            lengths.append(length)

        padded_tensor = np.zeros((len(lengths), max(lengths), tensors[0].shape[-1]), dtype=tensors[0].dtype)
        for idx, (tensor, length) in enumerate(zip(tensors, lengths)):
            padded_tensor[idx, :length] = tensor

        padded_tensor = torch.from_numpy(padded_tensor)
        padded_tensor = padded_tensor.to(device=self.device, dtype=self.dtype)
        return padded_tensor, lengths
