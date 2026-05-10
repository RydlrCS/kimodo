"""End-to-end text encoder smoke test for API/local/auto modes."""

from __future__ import annotations

import argparse
import json
import time

from kimodo.model.load_model import DEFAULT_TEXT_ENCODER_URL, _select_text_encoder_conf
from kimodo.model.loading import get_env_var, instantiate_from_dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kimodo text encoder smoke test")
    parser.add_argument(
        "--prompt",
        default="A person walks forward.",
        help="Prompt used for the end-to-end encoding call.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero if any step fails.",
    )
    parser.add_argument(
        "--retry-delay-sec",
        type=float,
        default=10.0,
        help="Delay before a single retry when the first cold-start attempt fails.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text_encoder_url = get_env_var("TEXT_ENCODER_URL", DEFAULT_TEXT_ENCODER_URL)
    mode = get_env_var("TEXT_ENCODER_MODE", "auto").lower()

    report = {
        "mode": mode,
        "text_encoder_url": text_encoder_url,
        "encoder_target": None,
        "ready": False,
        "encode_ok": False,
        "elapsed_ms": None,
        "output_shape": None,
        "lengths": None,
        "error": None,
    }

    started = time.time()
    conf = None
    encoder = None
    for attempt in range(2):
        try:
            if conf is None:
                conf = _select_text_encoder_conf(text_encoder_url)
                report["encoder_target"] = conf.get("_target_")
            if encoder is None:
                encoder = instantiate_from_dict(conf)

            # Probe readiness path first.
            encoder(["healthcheck"])
            report["ready"] = True

            encoded, lengths = encoder([args.prompt])
            report["encode_ok"] = True
            report["output_shape"] = tuple(encoded.shape)
            report["lengths"] = lengths
            report["attempts"] = attempt + 1
            break
        except Exception as error:  # pragma: no cover - runtime/network dependent
            report["error"] = f"{type(error).__name__}: {error}"
            report["attempts"] = attempt + 1
            if attempt == 0:
                time.sleep(max(0.0, args.retry_delay_sec))
                encoder = None
                continue

    report["elapsed_ms"] = int((time.time() - started) * 1000)

    print(json.dumps(report, indent=2, sort_keys=True))

    if args.strict and (not report["ready"] or not report["encode_ok"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
