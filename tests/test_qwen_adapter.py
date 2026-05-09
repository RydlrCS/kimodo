"""Tests for Qwen planner adapter with retries, strict parsing, and fallback behavior."""

from __future__ import annotations

from dataclasses import dataclass

from kimodo.planner.qwen_adapter import PlannerConfig, QwenPlannerAdapter
from kimodo.schemas import CharacterDefinition, PlannerRequest, TransitionPolicy


@dataclass
class FakeClient:
    """Deterministic fake client returning pre-seeded responses."""

    responses: list[str]

    def __post_init__(self):
        self.calls: list[dict] = []

    def text_generation(self, prompt: str, model: str, max_new_tokens: int, temperature: float) -> str:
        self.calls.append({
            "prompt": prompt,
            "model": model,
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
        })
        if not self.responses:
            raise RuntimeError("No fake responses left")
        return self.responses.pop(0)


def _request() -> PlannerRequest:
    return PlannerRequest(
        scene_id="scene_card4",
        user_prompt="Two performers greet each other then perform synchronized steps.",
        characters=[
            CharacterDefinition(character_id="lead", skeleton_type="soma"),
            CharacterDefinition(character_id="support", skeleton_type="soma"),
        ],
        duration_limit_sec=20.0,
    )


def test_valid_json_response_passes():
    client = FakeClient(
        responses=[
            '{"status":"success","scripts":{"lead":[{"segment_id":0,"action_text":"wave hand","duration_sec":2.0,"transition_policy":"smooth"}],"support":[{"segment_id":0,"action_text":"nod politely","duration_sec":2.0,"transition_policy":"cut"}]},"total_duration_sec":2.0}'
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    response = adapter.plan(_request())

    assert response.status == "success"
    assert set(response.scripts.keys()) == {"lead", "support"}
    assert response.scripts["support"][0].transition_policy == TransitionPolicy.CUT


def test_fenced_json_is_parsed():
    client = FakeClient(
        responses=[
            "```json\n{\"status\":\"success\",\"scripts\":{\"lead\":[{\"segment_id\":0,\"action_text\":\"step left\",\"duration_sec\":2.0,\"transition_policy\":\"smooth\"}],\"support\":[{\"segment_id\":0,\"action_text\":\"step right\",\"duration_sec\":2.0,\"transition_policy\":\"smooth\"}]},\"total_duration_sec\":2.0}\n```"
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    response = adapter.plan(_request())

    assert response.status == "success"
    assert len(response.scripts["lead"]) == 1


def test_retry_on_malformed_then_success():
    client = FakeClient(
        responses=[
            "not-json",
            '{"status":"success","scripts":{"lead":[{"segment_id":0,"action_text":"turn","duration_sec":1.0,"transition_policy":"smooth"}],"support":[{"segment_id":0,"action_text":"hold","duration_sec":1.0,"transition_policy":"smooth"}]}}',
        ]
    )
    adapter = QwenPlannerAdapter(client=client, config=PlannerConfig(max_retries_per_model=2))
    response = adapter.plan(_request())

    assert response.status == "success"
    assert len(client.calls) == 2


def test_fallback_when_all_attempts_fail():
    client = FakeClient(responses=["nope", "still nope", "bad", "bad2", "bad3", "bad4"])
    adapter = QwenPlannerAdapter(
        client=client,
        config=PlannerConfig(
            model_candidates=("m1", "m2", "m3"),
            max_retries_per_model=2,
        ),
    )
    response = adapter.plan(_request())

    assert response.status == "partial"
    assert response.metadata["fallback_used"] is True
    assert set(response.scripts.keys()) == {"lead", "support"}
    assert all(len(segs) >= 1 for segs in response.scripts.values())


def test_normalization_clamps_duration_and_transition():
    client = FakeClient(
        responses=[
            '{"status":"ok","scripts":{"lead":[{"segment_id":9,"action_text":"x","duration_sec":999,"transition_policy":"bad"}],"support":[{"segment_id":0,"action_text":"normal step","duration_sec":-10,"transition_policy":"hold"}]}}'
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    response = adapter.plan(_request())

    assert response.status == "partial"
    assert response.scripts["lead"][0].duration_sec == 20.0
    assert response.scripts["lead"][0].transition_policy == TransitionPolicy.SMOOTH
    assert response.scripts["support"][0].duration_sec == 0.5


def test_unknown_characters_are_dropped_and_defaulted():
    client = FakeClient(
        responses=[
            '{"status":"success","scripts":{"Lead !!!":[{"segment_id":0,"action_text":"hello there","duration_sec":2,"transition_policy":"smooth"}],"ghost":[{"segment_id":0,"action_text":"unused","duration_sec":1,"transition_policy":"smooth"}]}}'
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    response = adapter.plan(_request())

    assert set(response.scripts.keys()) == {"lead", "support"}


def test_interaction_target_normalization_to_valid_ids():
    client = FakeClient(
        responses=[
            '{"status":"success","scripts":{"lead":[{"segment_id":0,"action_text":"reach out","duration_sec":2,"transition_policy":"smooth","interaction_target":"support!!!"}],"support":[{"segment_id":0,"action_text":"respond","duration_sec":2,"transition_policy":"smooth","interaction_target":"unknown"}]}}'
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    response = adapter.plan(_request())

    assert response.scripts["lead"][0].interaction_target == "support"
    assert response.scripts["support"][0].interaction_target is None


def test_duration_limit_applied():
    client = FakeClient(
        responses=[
            '{"status":"success","scripts":{"lead":[{"segment_id":0,"action_text":"long segment","duration_sec":25,"transition_policy":"smooth"}],"support":[{"segment_id":0,"action_text":"long segment","duration_sec":25,"transition_policy":"smooth"}]}}'
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    response = adapter.plan(_request())

    assert response.total_duration_sec <= 20.0


def test_prompt_contains_character_context():
    client = FakeClient(
        responses=[
            '{"status":"success","scripts":{"lead":[{"segment_id":0,"action_text":"start","duration_sec":2,"transition_policy":"smooth"}],"support":[{"segment_id":0,"action_text":"start","duration_sec":2,"transition_policy":"smooth"}]}}'
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    adapter.plan(_request())

    sent_prompt = client.calls[0]["prompt"]
    assert "scene_id: scene_card4" in sent_prompt
    assert "- lead" in sent_prompt
    assert "- support" in sent_prompt


def test_metadata_marks_normalized():
    client = FakeClient(
        responses=[
            '{"status":"success","metadata":{"model":"custom"},"scripts":{"lead":[{"segment_id":0,"action_text":"start","duration_sec":2,"transition_policy":"smooth"}],"support":[{"segment_id":0,"action_text":"start","duration_sec":2,"transition_policy":"smooth"}]}}'
        ]
    )
    adapter = QwenPlannerAdapter(client=client)
    response = adapter.plan(_request())

    assert response.metadata["model"] == "custom"
    assert response.metadata["normalized"] is True
