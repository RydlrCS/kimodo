---
title: Movimento
emoji: 🎬
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 6.14.0
python_version: '3.12'
app_file: app.py
pinned: true
license: apache-2.0
short_description: Text-driven multi-character motion planning workspace
---

Movimento is a hackathon Space for multi-character motion planning and orchestration.

This Space currently runs a lightweight but feature-complete frontend shell for planning, execution trace, and playback controls.

Implemented pipeline milestones:
- Card 0: environment readiness gate
- Card 1: scope lock
- Card 2: service contracts
- Card 3: shared state deterministic loop
- Card 4: Qwen planner adapter
- Card 5: BONES-SEED ingestion flow
- Card 6: script-to-Kimodo mapping
- Card 7: blend quality guardrails
- Card 8: multi-character scheduler runtime
- Card 9: AMD runtime bootstrap and health checks
- Card 10: Gradio Space frontend shell

Next milestone:
- Card 11: notebook workflow and research pack

Runtime notes:
- HF bucket data is available for assets and repo snapshots.
- STL meshes are hosted in dataset `lablab-ai-amd-developer-hackathon/movimento-stl-assets`.
