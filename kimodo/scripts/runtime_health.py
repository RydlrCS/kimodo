"""Card 9 runtime health check entrypoint for backend startup validation."""

from __future__ import annotations

import argparse
import json

from kimodo.runtime import runtime_health_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kimodo runtime/backend health check")
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Requested device (auto, rocm, cuda, amd, cpu, mps, cuda:0, etc.)",
    )
    parser.add_argument(
        "--require-accelerator",
        action="store_true",
        help="Fail if selected runtime device is CPU.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = runtime_health_report(args.device)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))

    if args.require_accelerator and report.selected_device == "cpu":
        print("ERROR: accelerator required but runtime selected CPU")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())