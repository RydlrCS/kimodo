"""Qwen planner adapter: story prompt -> validated multi-character motion scripts."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from huggingface_hub import InferenceClient

from kimodo.schemas import MotionSegment, PlannerRequest, PlannerResponse, TransitionPolicy

LOGGER = logging.getLogger(__name__)

_ALLOWED_TRANSITIONS = {item.value for item in TransitionPolicy}
_STATUS_VALUES = {"success", "partial", "error"}


class PlannerClient(Protocol):
    """Protocol for LLM client implementations."""

    def text_generation(self, prompt: str, model: str, max_new_tokens: int, temperature: float) -> str:
        """Return generated text for a given model and prompt."""


class HFInferencePlannerClient:
    """Hugging Face Inference client wrapper used in production."""

    def __init__(self, token: str | None = None):
        self._client = InferenceClient(token=token)

    def text_generation(self, prompt: str, model: str, max_new_tokens: int, temperature: float) -> str:
        return self._client.text_generation(
            model=model,
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )


@dataclass(frozen=True)
class PlannerConfig:
    """Runtime settings for Qwen planner generation."""

    model_candidates: tuple[str, ...] = (
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-3B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct",
    )
    max_retries_per_model: int = 2
    max_new_tokens: int = 700
    temperature: float = 0.2


class QwenPlannerAdapter:
    """Convert high-level scene prompts to schema-validated planner scripts."""

    def __init__(self, client: PlannerClient | None = None, config: PlannerConfig | None = None):
        self.client = client or HFInferencePlannerClient()
        self.config = config or PlannerConfig()

    def plan(self, request: PlannerRequest) -> PlannerResponse:
        """Generate a planner response; fallback template is used if model outputs are malformed."""
        LOGGER.info("planner.plan.start scene_id=%s chars=%d", request.scene_id, len(request.characters))
        prompt = self._build_prompt(request)

        errors: list[str] = []
        for model_name in self.config.model_candidates:
            for attempt in range(1, self.config.max_retries_per_model + 1):
                try:
                    raw = self.client.text_generation(
                        prompt=prompt,
                        model=model_name,
                        max_new_tokens=self.config.max_new_tokens,
                        temperature=self.config.temperature,
                    )
                    payload = self._parse_json_payload(raw)
                    normalized = self._normalize_payload(payload, request)
                    response = PlannerResponse(**normalized)
                    LOGGER.info(
                        "planner.plan.success scene_id=%s model=%s attempt=%d",
                        request.scene_id,
                        model_name,
                        attempt,
                    )
                    return response
                except Exception as exc:  # pylint: disable=broad-except
                    err = f"model={model_name} attempt={attempt} error={exc}"
                    LOGGER.warning("planner.plan.retry scene_id=%s %s", request.scene_id, err)
                    errors.append(err)

        fallback = self._fallback_response(request, errors)
        LOGGER.info("planner.plan.fallback scene_id=%s", request.scene_id)
        return fallback

    def _build_prompt(self, request: PlannerRequest) -> str:
        LOGGER.info("planner.build_prompt.start scene_id=%s", request.scene_id)
        char_block = "\n".join(
            f"- {c.character_id} (skeleton={c.skeleton_type}, desc={c.description or 'none'})"
            for c in request.characters
        )
        prompt = (
            "You are a motion-planning copilot. Return strict JSON only, no markdown.\\n"
            "Generate per-character motion segments for this scene.\\n"
            "Rules:\\n"
            "1) Return object keys: status, scripts, total_duration_sec.\\n"
            "2) status must be success|partial|error.\\n"
            "3) scripts is object mapping character_id -> list of segments.\\n"
            "4) segment keys: segment_id(int), action_text(str), duration_sec(float 0.5-30), transition_policy(smooth|cut|hold|overlap), interaction_target(optional str), constraints(optional object).\\n"
            "5) Use only provided character_ids.\\n"
            "6) Keep total duration <= duration_limit_sec.\\n\\n"
            f"scene_id: {request.scene_id}\\n"
            f"duration_limit_sec: {request.duration_limit_sec}\\n"
            f"user_prompt: {request.user_prompt}\\n"
            f"characters:\\n{char_block}\\n"
        )
        LOGGER.info("planner.build_prompt.exit scene_id=%s prompt_chars=%s", request.scene_id, len(prompt))
        return prompt

    def _parse_json_payload(self, raw_text: str) -> dict[str, Any]:
        LOGGER.info("planner.parse_json.start")
        text = raw_text.strip()
        if not text:
            raise ValueError("empty model response")

        # Accept plain JSON or fenced JSON blocks and parse strictly.
        if text.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
            if not match:
                raise ValueError("fenced block found without JSON object")
            text = match.group(1).strip()

        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("no JSON object found in model response")
            text = text[start : end + 1]

        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("planner response must be a JSON object")
        LOGGER.info("planner.parse_json.exit keys=%s", sorted(payload.keys()))
        return payload

    def _normalize_payload(self, payload: dict[str, Any], request: PlannerRequest) -> dict[str, Any]:
        LOGGER.info("planner.normalize_payload.start scene_id=%s", request.scene_id)
        normalized: dict[str, Any] = {
            "scene_id": request.scene_id,
            "status": self._normalize_status(payload.get("status")),
            "error_message": payload.get("error_message"),
            "scripts": {},
            "metadata": payload.get("metadata") or {},
            "total_duration_sec": float(payload.get("total_duration_sec") or 0.0),
        }

        requested_ids = [c.character_id for c in request.characters]
        requested_set = set(requested_ids)
        raw_scripts = payload.get("scripts") or {}

        if not isinstance(raw_scripts, dict):
            raise ValueError("scripts must be an object")

        for raw_char_id, raw_segments in raw_scripts.items():
            char_id = self._normalize_character_id(str(raw_char_id))
            if char_id not in requested_set:
                continue
            normalized["scripts"][char_id] = self._normalize_segments(raw_segments, requested_set, request.duration_limit_sec)

        # Guarantee all requested characters have at least one segment.
        for char_id in requested_ids:
            if char_id not in normalized["scripts"] or not normalized["scripts"][char_id]:
                normalized["scripts"][char_id] = self._default_segments(char_id, request.user_prompt)

        normalized["total_duration_sec"] = min(
            request.duration_limit_sec,
            max(
                sum(float(seg.duration_sec) for seg in segs)
                for segs in normalized["scripts"].values()
            ),
        )

        normalized["metadata"] = {
            **(normalized["metadata"] if isinstance(normalized["metadata"], dict) else {}),
            "normalized": True,
        }
        LOGGER.info(
            "planner.normalize_payload.exit scene_id=%s script_chars=%s total_duration=%.2f",
            request.scene_id,
            len(normalized["scripts"]),
            float(normalized["total_duration_sec"]),
        )
        return normalized

    def _normalize_status(self, value: Any) -> str:
        status = str(value or "success").strip().lower()
        return status if status in _STATUS_VALUES else "partial"

    def _normalize_character_id(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", value.strip())
        normalized = re.sub(r"_+", "_", normalized)
        normalized = normalized.strip("_")
        return normalized[:50] or "character"

    def _normalize_segments(
        self,
        raw_segments: Any,
        valid_ids: set[str],
        duration_limit_sec: float,
    ) -> list[MotionSegment]:
        LOGGER.info("planner.normalize_segments.start")
        if not isinstance(raw_segments, list):
            raise ValueError("character script must be a list")

        normalized: list[MotionSegment] = []
        total = 0.0
        for idx, seg in enumerate(raw_segments):
            if not isinstance(seg, dict):
                continue
            action_text = str(seg.get("action_text") or "hold idle stance").strip()
            if len(action_text) < 3:
                action_text = "hold idle stance"
            duration = self._clamp_duration(seg.get("duration_sec"))
            if total + duration > duration_limit_sec:
                duration = max(0.5, duration_limit_sec - total)
            total += duration

            interaction_target = seg.get("interaction_target")
            if interaction_target is not None:
                interaction_target = self._normalize_character_id(str(interaction_target))
                if interaction_target not in valid_ids:
                    interaction_target = None

            transition = str(seg.get("transition_policy") or TransitionPolicy.SMOOTH.value).lower()
            if transition not in _ALLOWED_TRANSITIONS:
                transition = TransitionPolicy.SMOOTH.value

            normalized.append(
                MotionSegment(
                    segment_id=idx,
                    action_text=action_text[:500],
                    duration_sec=duration,
                    transition_policy=TransitionPolicy(transition),
                    interaction_target=interaction_target,
                    constraints=seg.get("constraints") if isinstance(seg.get("constraints"), dict) else {},
                )
            )

        LOGGER.info("planner.normalize_segments.exit segment_count=%s", len(normalized))
        return normalized

    def _clamp_duration(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 2.0
        return min(30.0, max(0.5, number))

    def _default_segments(self, char_id: str, prompt: str) -> list[MotionSegment]:
        base_text = prompt.strip()[:120]
        return [
            MotionSegment(
                segment_id=0,
                action_text=f"{char_id} starts: {base_text}",
                duration_sec=2.0,
                transition_policy=TransitionPolicy.SMOOTH,
                interaction_target=None,
                constraints={},
            ),
            MotionSegment(
                segment_id=1,
                action_text=f"{char_id} continues with controlled motion and stable stance",
                duration_sec=2.0,
                transition_policy=TransitionPolicy.SMOOTH,
                interaction_target=None,
                constraints={},
            ),
        ]

    def _fallback_response(self, request: PlannerRequest, errors: Iterable[str]) -> PlannerResponse:
        LOGGER.info("planner.fallback_response.start scene_id=%s", request.scene_id)
        scripts = {
            c.character_id: self._default_segments(c.character_id, request.user_prompt)
            for c in request.characters
        }
        total_duration = max(sum(seg.duration_sec for seg in segs) for segs in scripts.values())
        response = PlannerResponse(
            scene_id=request.scene_id,
            status="partial",
            error_message="; ".join(errors)[:1200] if errors else "model output malformed; fallback used",
            scripts=scripts,
            metadata={"fallback_used": True, "normalized": True},
            total_duration_sec=min(request.duration_limit_sec, total_duration),
        )
        LOGGER.info("planner.fallback_response.exit scene_id=%s", request.scene_id)
        return response
