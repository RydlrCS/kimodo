"""Card 8 runtime orchestration: deterministic multi-character scheduling."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from kimodo.pipeline.script_to_kimodo import run_multi_character_generation
from kimodo.schemas import GeneratorRequest
from kimodo.scheduler import (
    CharacterState,
    CharacterSegmentState,
    ConflictResolutionPolicy,
    DeterministicLoop,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SceneScheduleResult:
    """Structured result for scheduled scene execution."""

    outputs: dict[str, dict[str, Any]]
    errors: dict[str, str]
    plans: dict[str, Any]
    state_hashes: list[str]
    interactions: list[tuple[int, str, str]]
    completed_segments: dict[str, int]


def _activate_next_segment(loop: DeterministicLoop, character_id: str, plan: Any, segment_index: int) -> None:
    """Set active segment in loop state for one character."""
    slot = loop.characters[character_id]
    slot.segment_state = CharacterSegmentState(
        character_id=character_id,
        segment_index=segment_index,
        frames_elapsed=0,
        total_frames=plan.num_frames[segment_index],
    )
    segment = plan.segment_transition_policies[segment_index]
    # Interaction target is encoded in planner request segments; set later in per-tick update.
    slot.current_state = CharacterState.BUSY if segment != "cut" else CharacterState.TRANSITIONING


def run_scheduled_scene(
    model: Any,
    request: GeneratorRequest,
    *,
    fps: float,
    seed: int = 42,
    conflict_policy: ConflictResolutionPolicy = ConflictResolutionPolicy.COOLDOWN,
    diffusion_steps: int = 100,
    cfg_weight: Optional[list[float]] = None,
    cfg_type: Optional[str] = None,
    post_processing: bool = True,
    root_margin: float = 0.04,
    constraint_resolver: Optional[Any] = None,
    continue_on_error: bool = False,
) -> SceneScheduleResult:
    """Run generation then deterministic timeline scheduling for all characters in a scene."""
    LOGGER.info("card8.run_scheduled_scene.start scene_id=%s chars=%s", request.scene_id, len(request.characters))

    outputs, errors, plans = run_multi_character_generation(
        model,
        request,
        fps=fps,
        diffusion_steps=diffusion_steps,
        cfg_weight=cfg_weight,
        cfg_type=cfg_type,
        post_processing=post_processing,
        root_margin=root_margin,
        constraint_resolver=constraint_resolver,
        continue_on_error=continue_on_error,
    )

    loop = DeterministicLoop(
        fps=int(fps),
        seed=seed,
        conflict_policy=conflict_policy,
    )

    for priority, character in enumerate(request.characters):
        loop.register_character(character.character_id, character.skeleton_type, priority=priority)

    segment_indices = {character.character_id: 0 for character in request.characters}
    completed_segments = {character.character_id: 0 for character in request.characters}

    for character in request.characters:
        plan = plans.get(character.character_id)
        if plan is None:
            continue
        if not plan.num_frames:
            continue
        _activate_next_segment(loop, character.character_id, plan, segment_index=0)
        first_segment = character.segments[0]
        loop.characters[character.character_id].interaction_target = first_segment.interaction_target

    total_scene_frames = max((plan.total_frames for plan in plans.values()), default=0)
    state_hashes: list[str] = []
    interactions: list[tuple[int, str, str]] = []

    for _ in range(total_scene_frames):
        tick = loop.advance_tick({})
        state_hashes.append(loop.get_state_hash())

        for winner, loser in tick.interactions:
            interactions.append((tick.tick_number, winner, loser))

        for character_id in tick.completed_segments:
            plan = plans.get(character_id)
            if plan is None:
                continue
            completed_segments[character_id] += 1
            next_index = segment_indices[character_id] + 1
            if next_index < len(plan.num_frames):
                segment_indices[character_id] = next_index
                _activate_next_segment(loop, character_id, plan, next_index)
                source_char = next(c for c in request.characters if c.character_id == character_id)
                loop.characters[character_id].interaction_target = source_char.segments[next_index].interaction_target
            else:
                loop.characters[character_id].segment_state = None
                loop.characters[character_id].interaction_target = None

    LOGGER.info(
        "card8.run_scheduled_scene.exit scene_id=%s hashes=%s interactions=%s",
        request.scene_id,
        len(state_hashes),
        len(interactions),
    )
    return SceneScheduleResult(
        outputs=outputs,
        errors=errors,
        plans=plans,
        state_hashes=state_hashes,
        interactions=interactions,
        completed_segments=completed_segments,
    )