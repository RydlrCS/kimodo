"""CLI entrypoint for Qwen planner adapter."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from kimodo.planner import QwenPlannerAdapter
from kimodo.schemas import CharacterDefinition, PlannerRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate planner scripts from a story prompt using Qwen.")
    parser.add_argument("--scene-id", required=True, help="Scene identifier.")
    parser.add_argument("--prompt", required=True, help="User story prompt.")
    parser.add_argument(
        "--character",
        action="append",
        required=True,
        help="Character definition in form id[:skeleton[:description]]. Repeat for multiple characters.",
    )
    parser.add_argument("--duration-limit-sec", type=float, default=60.0)
    return parser


def _parse_character_arg(raw: str) -> CharacterDefinition:
    parts = raw.split(":", 2)
    character_id = parts[0]
    skeleton_type = parts[1] if len(parts) >= 2 and parts[1] else "soma"
    description = parts[2] if len(parts) == 3 and parts[2] else None
    return CharacterDefinition(character_id=character_id, skeleton_type=skeleton_type, description=description)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = PlannerRequest(
        scene_id=args.scene_id,
        user_prompt=args.prompt,
        duration_limit_sec=args.duration_limit_sec,
        characters=[_parse_character_arg(item) for item in args.character],
    )

    adapter = QwenPlannerAdapter()
    response = adapter.plan(request)
    print(json.dumps(response.model_dump(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
