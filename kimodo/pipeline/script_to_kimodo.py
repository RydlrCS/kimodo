"""Card 6 mapping layer: planner scripts -> Kimodo generation inputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from kimodo.pipeline.blend_quality import (
    TransitionSettings,
    apply_transition_guardrails,
    harmonize_scene_transitions,
)
from kimodo.schemas import CharacterGenerationState, GeneratorRequest, MotionSegment

LOGGER = logging.getLogger(__name__)

ConstraintResolver = Callable[[CharacterGenerationState, int], list[Any]]


@dataclass(frozen=True)
class CharacterKimodoPlan:
    """Resolved per-character generation plan consumable by Kimodo model(...)."""

    character_id: str
    prompts: list[str]
    num_frames: list[int]
    total_frames: int
    constraint_lst: list[Any]
    num_transition_frames: int
    share_transition: bool
    percentage_transition_override: float
    segment_transition_policies: list[str]


def seconds_to_frames(duration_sec: float, fps: float) -> int:
    """Convert segment duration in seconds to frames with a hard minimum of one frame."""
    return max(1, int(round(float(duration_sec) * float(fps))))


def _transition_from_segments(segments: list[MotionSegment]) -> tuple[int, bool, float]:
    """Aggregate segment transition policy into model-level transition parameters.

    Kimodo applies transition settings at call-level, so we choose a conservative aggregate:
    - If any segment requests cut, disable shared transitions and lower overlap.
    - If any segment requests overlap, increase transition blending.
    - Otherwise use smooth defaults.
    """
    policies = {segment.transition_policy.value for segment in segments}

    if "cut" in policies:
        return 1, False, 0.0
    if "overlap" in policies:
        return 8, True, 0.2
    if "hold" in policies:
        return 3, False, 0.05
    return 5, True, 0.10


def build_character_plan(
    character: CharacterGenerationState,
    *,
    fps: float,
    constraint_resolver: Optional[ConstraintResolver] = None,
    apply_blend_guardrails: bool = True,
) -> CharacterKimodoPlan:
    """Build one character generation plan from script segments.

    Entry/exit logs are intentionally verbose to make runtime mapping diagnostics explicit.
    """
    LOGGER.info(
        "card6.build_character_plan.start character_id=%s segments=%s fps=%.2f",
        character.character_id,
        len(character.segments),
        fps,
    )

    prompts = [segment.action_text for segment in character.segments]
    num_frames = [seconds_to_frames(segment.duration_sec, fps) for segment in character.segments]
    total_frames = sum(num_frames)

    if character.constraints:
        if constraint_resolver is None:
            raise ValueError(
                f"Constraints were provided for character '{character.character_id}' but no constraint_resolver was supplied"
            )
        # Constraint translation is caller-owned because target constraint classes are model/skeleton specific.
        constraint_lst = constraint_resolver(character, total_frames)
    else:
        constraint_lst = []

    num_transition_frames, share_transition, percentage_transition_override = _transition_from_segments(character.segments)

    if apply_blend_guardrails:
        guarded = apply_transition_guardrails(
            num_frames,
            [segment.transition_policy.value for segment in character.segments],
            TransitionSettings(
                num_transition_frames=num_transition_frames,
                share_transition=share_transition,
                percentage_transition_override=percentage_transition_override,
            ),
        )
        num_transition_frames = guarded.num_transition_frames
        share_transition = guarded.share_transition
        percentage_transition_override = guarded.percentage_transition_override

    plan = CharacterKimodoPlan(
        character_id=character.character_id,
        prompts=prompts,
        num_frames=num_frames,
        total_frames=total_frames,
        constraint_lst=constraint_lst,
        num_transition_frames=num_transition_frames,
        share_transition=share_transition,
        percentage_transition_override=percentage_transition_override,
        segment_transition_policies=[segment.transition_policy.value for segment in character.segments],
    )

    LOGGER.info(
        "card6.build_character_plan.exit character_id=%s total_frames=%s transitions=(frames=%s share=%s pct=%.2f)",
        plan.character_id,
        plan.total_frames,
        plan.num_transition_frames,
        plan.share_transition,
        plan.percentage_transition_override,
    )
    return plan


def generator_request_to_plans(
    request: GeneratorRequest,
    *,
    fps: float,
    constraint_resolver: Optional[ConstraintResolver] = None,
    apply_blend_guardrails: bool = True,
) -> dict[str, CharacterKimodoPlan]:
    """Map all characters in a generator request to executable per-character Kimodo plans."""
    LOGGER.info("card6.generator_request_to_plans.start scene_id=%s chars=%s", request.scene_id, len(request.characters))

    plans = {
        character.character_id: build_character_plan(
            character,
            fps=fps,
            constraint_resolver=constraint_resolver,
            apply_blend_guardrails=apply_blend_guardrails,
        )
        for character in request.characters
    }

    if apply_blend_guardrails and len(plans) > 1:
        harmonized = harmonize_scene_transitions(
            {
                character_id: TransitionSettings(
                    num_transition_frames=plan.num_transition_frames,
                    share_transition=plan.share_transition,
                    percentage_transition_override=plan.percentage_transition_override,
                )
                for character_id, plan in plans.items()
            }
        )
        plans = {
            character_id: CharacterKimodoPlan(
                character_id=plan.character_id,
                prompts=plan.prompts,
                num_frames=plan.num_frames,
                total_frames=plan.total_frames,
                constraint_lst=plan.constraint_lst,
                num_transition_frames=harmonized[character_id].num_transition_frames,
                share_transition=harmonized[character_id].share_transition,
                percentage_transition_override=harmonized[character_id].percentage_transition_override,
                segment_transition_policies=plan.segment_transition_policies,
            )
            for character_id, plan in plans.items()
        }

    LOGGER.info("card6.generator_request_to_plans.exit scene_id=%s plans=%s", request.scene_id, len(plans))
    return plans


def run_character_generation(
    model: Any,
    plan: CharacterKimodoPlan,
    *,
    diffusion_steps: int,
    num_samples: int,
    cfg_weight: Optional[list[float]] = None,
    cfg_type: Optional[str] = None,
    post_processing: bool = True,
    root_margin: float = 0.04,
) -> dict[str, Any]:
    """Execute Kimodo generation for one character plan."""
    LOGGER.info(
        "card6.run_character_generation.start character_id=%s prompts=%s total_frames=%s",
        plan.character_id,
        len(plan.prompts),
        plan.total_frames,
    )

    result = model(
        plan.prompts,
        plan.num_frames,
        constraint_lst=plan.constraint_lst,
        num_denoising_steps=diffusion_steps,
        num_samples=num_samples,
        multi_prompt=True,
        cfg_weight=cfg_weight or [2.0, 2.0],
        cfg_type=cfg_type,
        num_transition_frames=plan.num_transition_frames,
        share_transition=plan.share_transition,
        percentage_transition_override=plan.percentage_transition_override,
        post_processing=post_processing,
        root_margin=root_margin,
    )

    LOGGER.info("card6.run_character_generation.exit character_id=%s", plan.character_id)
    return result


def run_multi_character_generation(
    model: Any,
    request: GeneratorRequest,
    *,
    fps: float,
    diffusion_steps: int = 100,
    cfg_weight: Optional[list[float]] = None,
    cfg_type: Optional[str] = None,
    post_processing: bool = True,
    root_margin: float = 0.04,
    constraint_resolver: Optional[ConstraintResolver] = None,
    continue_on_error: bool = False,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, CharacterKimodoPlan]]:
    """Run per-character Kimodo generation for all scripts in a scene.

    Returns:
        outputs: per-character model outputs.
        errors: per-character error message for failed runs.
        plans: resolved per-character plans for auditing and verification.
    """
    LOGGER.info("card6.run_multi_character_generation.start scene_id=%s", request.scene_id)

    plans = generator_request_to_plans(request, fps=fps, constraint_resolver=constraint_resolver)
    outputs: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    for character_id, plan in plans.items():
        try:
            outputs[character_id] = run_character_generation(
                model,
                plan,
                diffusion_steps=diffusion_steps,
                num_samples=request.num_samples,
                cfg_weight=cfg_weight,
                cfg_type=cfg_type,
                post_processing=post_processing,
                root_margin=root_margin,
            )
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("card6.run_multi_character_generation.error character_id=%s", character_id)
            errors[character_id] = str(exc)
            if not continue_on_error:
                break

    LOGGER.info(
        "card6.run_multi_character_generation.exit scene_id=%s success=%s errors=%s",
        request.scene_id,
        len(outputs),
        len(errors),
    )
    return outputs, errors, plans
