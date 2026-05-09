"""Hugging Face Space entrypoint for Movimento hackathon frontend."""

from __future__ import annotations

import os

# Configure environment for HF Spaces runtime.
os.environ.setdefault("HF_MODE", "1")
os.environ.setdefault("SERVER_NAME", "0.0.0.0")
os.environ.setdefault("SERVER_PORT", "7860")
os.environ.setdefault("MAX_ACTIVE_USERS", "5")
os.environ.setdefault("MAX_SESSION_MINUTES", "5.0")


def main() -> None:
    from kimodo.scripts.space_frontend import main as frontend_main

    frontend_main()


if __name__ == "__main__":
    main()
