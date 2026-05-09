"""Card 6 tests: script-to-Kimodo mapping and per-character generation flow."""

from __future__ import annotations

from dataclasses import dataclass

from kimodo.pipeline.script_to_kimodo import (
    build_character_plan,
    generator_request_to_plans,
    run_multi_character_generation,
    seconds_to_frames,
)
from kimodo.schemas import (
    CharacterGenerationState,
    GeneratorRequest,
    GenerationConstraint,
    MotionSegment,
    TransitionPolicy,
)


class FakeKimodoModel:
    """Fake model that records invocations and returns minimal motion payload."""

    def __init__(self):
        self.calls = []

    def __call__(self, prompts, num_frames, **kwargs):
        self.calls.append(
            {
                "prompts": prompts,
                "num_frames": num_frames,
                "kwargs": kwargs,
            }
        )
        return {
            "posed_joints": [[0.0]],
            "global_rot_mats": [[0.0]],
            "foot_contacts": [[0.0]],
            "num_frames": num_frames,
            "prompts": prompts,
        }


def _make_request() -> GeneratorRequest:
    return GeneratorRequest(
        scene_id="scene_card6",
        num_samples=1,
        characters=[
            CharacterGenerationState(
                character_id="char_a",
                segments=[
                    MotionSegment(
                        segment_id=0,
                        action_text="walk forward steadily",
                        duration_sec=2.0,
                        transition_policy=TransitionPolicy.SMOOTH,
                    ),
                    MotionSegment(
                        segment_id=1,
                        action_text="turn left and wave",
                        duration_sec=1.5,
                        transition_policy=TransitionPolicy.OVERLAP,
                    ),
                ],
            ),
            CharacterGenerationState(
                character_id="char_b",
                segments=[
                    MotionSegment(
                        segment_id=0,
                        action_text="step backward",
                        duration_sec=1.0,
                        transition_policy=TransitionPolicy.CUT,
                    ),
                    MotionSegment(
                        segment_id=1,
                        action_text="hold guard stance",
                        duration_sec=1.0,
                        transition_policy=TransitionPolicy.HOLD,
                    ),
                ],
            ),
        ],
    )


def test_seconds_to_frames_minimum_one_frame():
    assert seconds_to_frames(0.0001, 30.0) == 1


def test_character_plan_segment_counts_and_durations_match_script():
    request = _make_request()
    character = request.characters[0]

    plan = build_character_plan(character, fps=30.0)

    assert len(plan.prompts) == len(character.segments)
    assert len(plan.num_frames) == len(character.segments)
    expected = [60, 45]
    assert plan.num_frames == expected
    assert plan.total_frames == sum(expected)


def test_transition_mapping_applies_policy_overrides():
    request = _make_request()
    plan_a = build_character_plan(request.characters[0], fps=30.0)
    plan_b = build_character_plan(request.characters[1], fps=30.0)

    assert plan_a.share_transition is True
    assert plan_a.num_transition_frames == 8
    assert plan_a.percentage_transition_override == 0.2

    assert plan_b.share_transition is False
    assert plan_b.num_transition_frames == 1
    assert plan_b.percentage_transition_override == 0.0


def test_constraints_require_explicit_resolver():
    char = CharacterGenerationState(
        character_id="char_c",
        segments=[
            MotionSegment(
                segment_id=0,
                action_text="reach target",
                duration_sec=2.0,
                transition_policy=TransitionPolicy.SMOOTH,
            )
        ],
        constraints=[GenerationConstraint()],
    )

    try:
        build_character_plan(char, fps=30.0)
        assert False, "Expected ValueError when constraints exist without resolver"
    except ValueError as exc:
        assert "constraint_resolver" in str(exc)


def test_constraints_applied_via_resolver():
    char = CharacterGenerationState(
        character_id="char_d",
        segments=[
            MotionSegment(
                segment_id=0,
                action_text="lean right",
                duration_sec=1.0,
                transition_policy=TransitionPolicy.SMOOTH,
            )
        ],
        constraints=[GenerationConstraint()],
    )

    def resolver(state: CharacterGenerationState, total_frames: int):
        assert state.character_id == "char_d"
        assert total_frames == 30
        return ["fake_constraint"]

    plan = build_character_plan(char, fps=30.0, constraint_resolver=resolver)
    assert plan.constraint_lst == ["fake_constraint"]


def test_two_character_generation_runs_without_crash():
    request = _make_request()
    model = FakeKimodoModel()

    outputs, errors, plans = run_multi_character_generation(
        model,
        request,
        fps=30.0,
        diffusion_steps=20,
        continue_on_error=False,
    )

    assert len(errors) == 0
    assert set(outputs.keys()) == {"char_a", "char_b"}
    assert set(plans.keys()) == {"char_a", "char_b"}
    assert len(model.calls) == 2


def test_segment_frames_match_script_for_each_character_in_scene():
    request = _make_request()
    plans = generator_request_to_plans(request, fps=30.0)

    assert plans["char_a"].num_frames == [60, 45]
    assert plans["char_b"].num_frames == [30, 30]
