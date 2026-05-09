# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Qwen-on-Fireworks helper for auto-generating multi-text-prompt batches."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

_MODEL = "accounts/fireworks/models/qwen3p6-27b"
_BASE  = "https://api.fireworks.ai/inference/v1"

_SYSTEM = """\
You are a motion-description writer for a single humanoid character in a 3D animation system.
Given a scene context and the character's recent motion history, output ONLY a JSON object:

{"texts": ["<action phrase 1>", ...], "durations": [<seconds float>, ...]}

Rules:
- Return between 1 and requested_actions short, vivid action phrases that flow naturally from each other.
- Each phrase describes one distinct physical motion (e.g. "walks forward briskly", "pivots left and crouches").
- Each duration is between 2.0 and 8.0 seconds.
- texts and durations must have the same length.
- Do NOT repeat phrases from history.
- Return raw JSON only — no markdown, no explanation.
"""


def _call_fireworks(messages: list[dict]) -> str:
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


def _fallback(offset: int) -> dict:
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


def call_qwen_for_prompts(
    scene: str,
    history: list[str],
    requested_actions: int = 5,
) -> tuple[dict, list[str]]:
    """Call Qwen to produce the next batch of motion prompts.

    Returns (batch_dict, updated_history).
    batch_dict has keys "texts" and "durations".
    Raises RuntimeError on API failure (caller may fall back).
    """
    user_msg = (
        f"Scene: {scene or 'a character moving continuously in 3D space'}\n"
        f"Motion history (do not repeat): {json.dumps(history[-12:])}\n\n"
        f"requested_actions: {max(1, min(10, int(requested_actions)))}\n"
        "Generate the next batch of motion prompts."
    )
    try:
        raw = _call_fireworks([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}])
        batch = _parse(raw)
        if not isinstance(batch.get("texts"), list) or not isinstance(batch.get("durations"), list):
            raise ValueError("Missing texts or durations")
        n = min(len(batch["texts"]), len(batch["durations"]))
        batch["texts"] = batch["texts"][:n]
        batch["durations"] = batch["durations"][:n]
    except Exception:
        batch = _fallback(len(history))

    new_history = history + list(batch["texts"])
    return batch, new_history
