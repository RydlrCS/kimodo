"""Card 7 blend quality guardrails for transition blending safety and consistency."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionSettings:
    """Transition settings passed to Kimodo generation."""

    num_transition_frames: int
    share_transition: bool
    percentage_transition_override: float


@dataclass(frozen=True)
class BlendGuardrailConfig:
    """Runtime safety bounds for transition blending."""

    min_transition_frames: int = 1
    max_transition_frames: int = 12
    min_segment_frames_for_share: int = 12
    max_transition_ratio: float = 0.30
    max_shared_window_frames: int = 24
    harmonize_window: int = 2


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def apply_transition_guardrails(
    segment_frames: list[int],
    policies: list[str],
    requested: TransitionSettings,
    *,
    config: BlendGuardrailConfig = BlendGuardrailConfig(),
) -> TransitionSettings:
    """Clamp transition settings to safe ranges for short/long segments.

    Guardrails avoid transition windows that dominate short segments and reduce blending artifacts
    for scripted interactions.
    """
    if len(segment_frames) < 2:
        safe_frames = int(_clamp(requested.num_transition_frames, config.min_transition_frames, config.max_transition_frames))
        return TransitionSettings(
            num_transition_frames=safe_frames,
            share_transition=False,
            percentage_transition_override=0.0,
        )

    min_prev = min(segment_frames[:-1])
    min_next = min(segment_frames[1:])
    # Keep at least one non-transition frame in the shortest pair.
    shortest_pair_budget = max(config.min_transition_frames, min(min_prev, min_next) - 1)

    safe_frames = int(
        _clamp(
            requested.num_transition_frames,
            config.min_transition_frames,
            min(config.max_transition_frames, shortest_pair_budget),
        )
    )

    has_cut = "cut" in policies
    can_share = (
        requested.share_transition
        and not has_cut
        and min_prev >= config.min_segment_frames_for_share
        and min_next >= config.min_segment_frames_for_share
    )

    if not can_share:
        return TransitionSettings(
            num_transition_frames=safe_frames,
            share_transition=False,
            percentage_transition_override=0.0,
        )

    safe_pct = _clamp(requested.percentage_transition_override, 0.0, config.max_transition_ratio)

    # Cap shared overlap by configured hard ceiling and shortest-pair budget.
    max_pct_from_shared_window = max(0.0, (config.max_shared_window_frames - safe_frames) / max(1, min_prev))
    max_pct_from_shortest_pair = max(0.0, (shortest_pair_budget - safe_frames) / max(1, min_prev))
    safe_pct = min(safe_pct, max_pct_from_shared_window, max_pct_from_shortest_pair)

    return TransitionSettings(
        num_transition_frames=safe_frames,
        share_transition=True,
        percentage_transition_override=float(safe_pct),
    )


def harmonize_scene_transitions(
    settings_by_character: dict[str, TransitionSettings],
    *,
    config: BlendGuardrailConfig = BlendGuardrailConfig(),
) -> dict[str, TransitionSettings]:
    """Nudge transition-frame counts toward a scene median for multi-character consistency."""
    if len(settings_by_character) < 2:
        return settings_by_character

    frame_values = sorted(setting.num_transition_frames for setting in settings_by_character.values())
    median = frame_values[len(frame_values) // 2]
    low = max(config.min_transition_frames, median - config.harmonize_window)
    high = min(config.max_transition_frames, median + config.harmonize_window)

    harmonized: dict[str, TransitionSettings] = {}
    for character_id, setting in settings_by_character.items():
        harmonized[character_id] = TransitionSettings(
            num_transition_frames=int(_clamp(setting.num_transition_frames, low, high)),
            share_transition=setting.share_transition,
            percentage_transition_override=setting.percentage_transition_override,
        )
    return harmonized