# Kimodo Copilot: 24-Hour Hackathon Scope Lock

**Product Scope (Single Sentence):**
Ship a public Hugging Face Space (Gradio SDK) where users input story prompts, Qwen LLM converts them to multi-character motion scripts, Kimodo generates and blends motions, and interactions play synchronously in one shared session on AMD hardware.

---

## Locked Decisions

| Decision | Value | Rationale |
|----------|-------|-----------|
| **Hackathon Track** | Track 1: AI Agents & Agentic Workflows | Qwen copilot is the core value; copilot-first UX is primary. |
| **Frontend SDK** | Gradio (HF Space SDK) | Fastest polished UX, native HF integration, clean Space submission. |
| **Compute Backend** | AMD Developer Cloud + ROCm | Hackathon sponsor compute, non-NVIDIA path, 17GB VRAM target. |
| **LLM Engine** | Qwen (priority: 7B → 3B → 1.5B) | Alibaba open-source, instruction-tuned, agentic-ready. |
| **Model Inference** | Kimodo (existing nv-tlabs/kimodo) | Production-ready motion diffusion, multi-skeleton support. |
| **Dataset Showcase** | BONES SEED (HF: bones-studio/seed) | Public 288-hour mocap, dataset integration proof required. |
| **Organization** | lablab-ai-amd-developer-hackathon | Hackathon sponsor space. |

---

## Included Scope

1. **Qwen Planner Layer** (Card 4)
   - Qwen adapter: parse story prompts → validated motion scripts (JSON).
   - Retry and fallback templates for robustness.
   - Sanitization and naming normalization.

2. **Multi-Character Motion Execution** (Cards 6-8)
   - Per-character script-to-Kimodo mapping.
   - Deterministic shared event loop (synchronized tick).
   - Transition quality guardrails.
   - Support for ≥3 active characters in one session.

3. **Dataset Integration** (Card 5)
   - BONES SEED browser and downloader utility.
   - Metadata listing, targeted file pull, manifest output.
   - HF Hub token and caching support via HF_HOME.

4. **Gradio Space Frontend** (Card 10)
   - Prompt entry, script preview, execute button.
   - Playback controls, session status, error notifications.
   - Favicon and clear lablab branding.
   - Cold-start usability without local setup.

5. **AMD Backend Path** (Card 9)
   - ROCm-compatible runtime configuration.
   - Device selection via environment (no hardcoded NVIDIA).
   - Proof-of-health check on AMD target.

6. **Jupyter Research Notebooks** (Card 11)
   - A) Dataset inspection and sampling.
   - B) Prompt-to-script debugging and LLM behavior.
   - C) Multi-character blending experiments.

7. **Orchestration Templates** (Cards 12-13)
   - Kubernetes deployment, service, secret manifests.
   - Slurm sbatch scripts for batch scene runs.
   - Templates for AMD cluster adaptation.

8. **Quality & Engineering** (Card 14)
   - Naming consistency (CamelCase classes, snake_case functions).
   - Defensive input validation, fail-fast error messages.
   - Entry/exit logging on critical request paths.
   - Favicon serving and static asset management.
   - Unit and smoke test coverage.

9. **Build-in-Public Artifacts** (Card 15-16)
   - 2-3 curated storyline prompts for demo.
   - Screenshots, gifs, architecture diagram.
   - Concise README quick start for judges.

---

## Excluded Scope (Unless Ahead of Schedule)

1. **Model Fine-Tuning**
   - Full Kimodo training pipeline on MI300X.
   - Reason: 24-hour window prioritizes integration and UX over training depth.

2. **Deep Benchmarking Framework**
   - Extensive metric collection or comparative studies.
   - Reason: Scope focuses on shipping a working demo, not a research pipeline.

3. **Full Production Security Hardening**
   - Rate limiting, certificate management, advanced auth integrations.
   - Reason: Hackathon demo prioritizes functionality over enterprise hardening.

4. **Extended Orchestration Testing**
   - Full K8s cluster rollout or Slurm job farm validation.
   - Reason: Templates only; one method (K8s or Slurm) actively demonstrated if time permits.

5. **Advanced NLP Features**
   - Character voice synthesis, detailed emotion modeling, dynamic constraint negotiation.
   - Reason: Out of scope for 24-hour sprint; LLM planner output is deterministic script format only.

---

## Architecture Boundaries

```
┌─────────────────────────────────────────────────────┐
│  Gradio Space (Frontend, HF Hub)                    │
│  - Prompt input, script preview, playback timeline  │
│  - User interactions and session management         │
└────────────────┬────────────────────────────────────┘
                 │
                 │ HTTP/REST API
                 ▼
┌─────────────────────────────────────────────────────┐
│  AMD Backend (ROCm, lablab AMD Developer Cloud)     │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                │
│  │ Qwen Planner │  │ Kimodo Gen   │                │
│  │ (LLM)        │  │ (Diffusion)  │                │
│  └──────────────┘  └──────────────┘                │
│         ▲                  ▲                         │
│         └──────┬───────────┘                        │
│                ▼                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │ Multi-Character Scheduler + State Loop       │  │
│  │ (Deterministic ticks, conflict resolution)   │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ Ingestion & Caching Layer                    │  │
│  │ (BONES SEED, HF Hub, Model Weights)          │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Key Constraint**: Single port, one shared timeline, no inter-node RPC (all characters synchronized in-process).

---

## Success Criteria (Gate 16)

1. ✅ Copilot-first flow: prompt → script → motion.
2. ✅ Multi-character interaction in one session (≥2 characters).
3. ✅ BONES SEED ingestion demonstrated (list + download).
4. ✅ AMD backend path demonstrated (device detection, model load).
5. ✅ Space link public, responsive, cold-start usable.
6. ✅ Build-in-public update posted (architecture + lessons learned).

---

## Signatures / Approval

- **Scope Locked**: 24-hour sprint board approved.
- **Track 1 Confirmed**: AI Agents & Agentic Workflows.
- **No Scope Creep**: All excluded items deferred or rejected.
- **Ready for Card 2**: Architecture and contracts phase begins.

---

**Date**: May 9, 2026  
**Status**: APPROVED FOR EXECUTION
## Plan: 24-Hour Sprint Board (Qwen + Kimodo + AMD)

Primary recommendation: target Track 1 (AI Agents & Agentic Workflows) with a motion-planning copilot, while borrowing selective Track 3 elements (multimodal storyline framing) only if time remains. Keep Track 2 fine-tuning out of critical path for a 24-hour ship window.

Space SDK selection: Gradio.
Reason: fastest path to a polished public demo, easiest integration with existing Kimodo UX and timeline interactions, and clean separation where AMD backend does heavy compute while the Space serves as UX and submission surface.

## Sprint Objective
Ship an end-to-end public demo where:
1) User enters a high-level story prompt.
2) Qwen copilot converts it into a validated multi-character motion script.
3) Kimodo generates and blends motions per character.
4) Shared loop executes interactions in one session/port.
5) Demo is published as a Hugging Face Space under the lablab organization (Gradio SDK), with AMD-hosted backend inference.

## Board Structure
Each card includes: Outcome, Owner (Copilot/Human), Inputs, Actions, Verification, Done criteria.
No card may be marked complete without passing its verification block.

## Hour-by-Hour Execution Board (24h)


### Preflight: Environment Readiness Gate
Card 0: Verify all working environments before coding begins.
- Outcome: every required environment is provisioned, reachable, and documented.
- Owner: Human + Copilot.
- Environments to check:
  - Local dev shell with repo dependencies installed.
  - Hugging Face access with the movimiento token and lablab Space permissions.
  - AMD Developer Cloud or ROCm-capable backend target.
  - Jupyter notebook runtime.
  - Kubernetes access if that path is chosen.
  - Slurm access if that path is chosen.
- Checklist, in order:
  1. Confirm the local Python environment matches the repo requirements and can import Kimodo modules.
  2. Confirm Hugging Face authentication is available, the movimiento token is loaded, and access to the lablab Space org is granted.
  3. Confirm Hugging Face Hub access to BONES SEED works for listing and downloading the target files.
  4. Confirm the selected model cache path is writable and the Hugging Face cache directory is mounted or configured.
  5. Confirm the AMD backend target is reachable and that the runtime can select a valid device without NVIDIA-only assumptions.
  6. Confirm notebook support is available for the research workflow and can access the same cache and auth context.
  7. If Kubernetes is used, confirm cluster access, namespace access, image pull access, and secret creation access.
  8. If Slurm is used, confirm scheduler access, account/partition access, and job submission permissions.
  9. Record a single pass/fail note for each environment and block coding until all required items pass.

  - Local dev shell with repo dependencies installed.
  - Hugging Face access with the movimiento token and lablab Space permissions.
  - AMD Developer Cloud or ROCm-capable backend target.
  - Jupyter notebook runtime.
  - Kubernetes access if that path is chosen.
  - Slurm access if that path is chosen.
- Actions:
  - Confirm Python/tooling versions match repo requirements.
  - Confirm Hugging Face auth, cache location, and dataset access.
  - Confirm AMD device/runtime visibility and model download path.
  - Confirm notebook, K8s, and Slurm entrypoints or fallback templates exist.
  - Record any missing dependencies or blocked services before coding.
- Verification:
  - A single preflight checklist passes or blocks the sprint with explicit reasons.
  - Each environment has a documented start command or access note.
- Done criteria:
  - No coding card starts until this gate is green.

### H00-H01: Sprint Kickoff and Scope Lock
Card 1: Freeze scope and track selection.
- Outcome: Single-sentence product scope and architecture boundaries approved.
- Owner: Human + Copilot.
- Inputs: prior plan, hackathon tracks, deployment constraints.
- Actions:
  - Lock Track 1 as primary.
  - Lock Gradio Space SDK.
  - Lock AMD backend as compute host.
  - Defer fine-tuning unless all critical cards complete early.
- Verification:
  - Written scope includes included and excluded items.
- Done criteria:
  - Scope statement signed off and copied into README sprint section.

### H01-H03: Architecture and Contracts
Card 2: Define service contracts.
- Outcome: strict request/response schemas for planner and generator APIs.
- Owner: Copilot.
- Inputs: Kimodo generation call shape, multi-character loop requirements.
- Actions:
  - Define planner schema fields: scene_id, character_id, intent, action_text, duration_sec, transition_policy, interaction_target, constraints.
  - Define generator schema fields: prompts, per-segment durations, character states, transition params.
  - Add defensive validation constraints and error codes.
- Verification:
  - Schema examples validate both valid and invalid payloads.
- Done criteria:
  - Schemas documented and referenced by all downstream cards.

Card 3: Define shared state loop.
- Outcome: deterministic event order for multi-character interactions in one port.
- Owner: Copilot.
- Actions:
  - Specify tick order, character update order, conflict resolution, cooldown policy.
- Verification:
  - Simulated two-character and three-character examples show deterministic outcomes.
- Done criteria:
  - Loop spec merged into architecture note.

### H03-H05: Qwen Copilot Layer
Card 4: Build copilot prompt-to-script conversion path.
- Outcome: Qwen generates structured script, not raw prose.
- Owner: Copilot.
- Inputs: Qwen model endpoint from Hugging Face collection selection.
- Actions:
  - Implement planner adapter with retries and strict JSON parse.
  - Add fallback template when model output is malformed.
  - Add sanitization and naming normalization.
- Verification:
  - 10 prompt tests produce schema-valid scripts.
  - malformed responses are recovered or rejected with explicit message.
- Done criteria:
  - Planner endpoint stable with deterministic parser behavior.

Recommended Qwen choices (priority order):
1) Qwen2.5-7B-Instruct for quality.
2) Qwen2.5-3B-Instruct for latency/cost fallback.
3) Qwen2.5-1.5B-Instruct as emergency fallback.

### H05-H07: Hugging Face Dataset Ingestion (BONES SEED)
Card 5: Add dataset browser/downloader utility.
- Outcome: list and download from https://huggingface.co/datasets/bones-studio/seed.
- Owner: Copilot.
- Actions:
  - Implement metadata listing mode.
  - Implement targeted file pull mode.
  - Implement subset pull mode with manifest output.
  - Add token/caching behavior aligned with existing HF_HOME conventions.
- Verification:
  - listing works.
  - one targeted file fetch succeeds.
  - manifest records revision and local file paths.
- Done criteria:
  - ingestion utility usable from CLI and notebook.

### H07-H09: Kimodo Integration and Motion Blending
Card 6: Wire script segments into Kimodo generation path.
- Outcome: each character script is translated into Kimodo prompt segments and transition settings.
- Owner: Copilot.
- Actions:
  - map script actions to prompt strings and durations.
  - pass transition controls explicitly.
  - apply per-character constraints.
- Verification:
  - two-character interaction run finishes with no crashes.
  - segment counts and durations match script.
- Done criteria:
  - generated outputs replay end-to-end in shared timeline.

Card 7: Blend quality guardrails.
- Outcome: transitions stay smooth under scripted interactions.
- Owner: Copilot.
- Actions:
  - tune transition frames and sharing policy defaults.
  - add bounds checks for extreme durations.
- Verification:
  - run 3 scripted scenes and inspect transition continuity.
- Done criteria:
  - default settings produce stable transitions.

### H09-H11: Shared Loop and Multi-Character Port
Card 8: Multi-character scheduler implementation.
- Outcome: multiple characters run in one session/port with synchronized time.
- Owner: Copilot.
- Actions:
  - add per-character state containers.
  - enforce deterministic scheduler and conflict policy.
  - ensure no cross-character state corruption.
- Verification:
  - deterministic replay test passes for same seed and script.
- Done criteria:
  - shared loop supports at least 3 active characters.

### H11-H13: AMD Runtime Path
Card 9: AMD backend bootstrap path.
- Outcome: backend runs on AMD cloud with clear hardware config.
- Owner: Human + Copilot.
- Actions:
  - configure runtime for ROCm-compatible stack.
  - externalize device selection via env settings.
  - remove hardcoded NVIDIA-only assumptions from critical startup path.
- Verification:
  - backend startup health check passes on AMD environment.
- Done criteria:
  - generation endpoint healthy and callable from frontend.

### H13-H15: Space Frontend (Gradio SDK)
Card 10: Build Gradio Space shell.
- Outcome: public UI with copilot-first flow and run controls.
- Owner: Copilot.
- Actions:
  - add prompt entry, script preview, execute button, playback controls.
  - include favicon and clear branding.
  - show session status and error notifications.
- Verification:
  - manual smoke test from fresh session works end-to-end.
- Done criteria:
  - Space UI usable without local setup.

### H15-H17: Jupyter Research Notebook Pack
Card 11: Add notebook workflow.
- Outcome: reproducible notebooks for exploration and validation.
- Owner: Copilot.
- Actions:
  - notebook A: dataset inspection and sampling.
  - notebook B: prompt-to-script debugging.
  - notebook C: multi-character blending experiments.
- Verification:
  - each notebook runs top-to-bottom with documented prerequisites.
- Done criteria:
  - notebook outputs match API behavior.

### H17-H19: Orchestration Templates (K8s + Slurm)
Card 12: Kubernetes template pack.
- Outcome: deployable manifests for planner and generator services.
- Owner: Copilot.
- Actions:
  - add deployment, service, secret, and health check templates.
- Verification:
  - config lint passes and endpoints resolve in staging.
- Done criteria:
  - manifests ready for AMD cluster adaptation.

Card 13: Slurm template pack.
- Outcome: sbatch scripts for batch scene runs.
- Owner: Copilot.
- Actions:
  - add scripts for single run, parameter sweep, and retry-safe batch.
- Verification:
  - dry-run and one sample job submission command documented.
- Done criteria:
  - batch artifacts path and logs are deterministic.

### H19-H21: Quality Pass (Code + Reliability)
Card 14: Engineering quality enforcement.
- Outcome: code quality, naming conventions, defensive checks, and logging complete.
- Owner: Copilot.
- Actions:
  - enforce naming consistency.
  - add entry/exit logging on critical request paths.
  - validate all external inputs and fail fast with readable errors.
  - add or confirm favicon serving behavior.
- Verification:
  - lint/test/smoke suite passes.
  - logs show full request lifecycle.
- Done criteria:
  - zero high-severity runtime errors in test pass.

### H21-H23: Demo Hardening and Submission Assets
Card 15: Demo script and submission prep.
- Outcome: stable public demo plus concise walkthrough.
- Owner: Human + Copilot.
- Actions:
  - prepare 2-3 curated storyline prompts.
  - capture screenshots/gifs and architecture diagram.
  - finalize README quick start for judges.
- Verification:
  - cold-start trial by another tester succeeds.
- Done criteria:
  - submission package complete.

### H23-H24: Buffer and Final Gate
Card 16: Final validation gate.
- Outcome: go/no-go decision for submission.
- Owner: Human.
- Verification checklist:
  - copilot-first flow works.
  - multi-character interaction works in one session.
  - BONES SEED ingestion demonstrated.
  - AMD backend path demonstrated.
  - Space link public and responsive.
  - build-in-public update drafted and posted.
- Done criteria:
  - final submission sent.

## Copilot Task Queue (Execution Order)
1. Contracts and schema card.
2. Planner adapter card.
3. Dataset ingestion card.
4. Kimodo mapping card.
5. Scheduler card.
6. UI integration card.
7. Quality pass card.
8. Docs and submission card.

## Verification Commands and Gates (High Level)
1. Unit tests for schema validation and parser robustness.
2. Smoke tests for planner endpoint and generator endpoint.
3. Scenario tests for two-character and three-character deterministic interactions.
4. Frontend end-to-end run from blank session.
5. One AMD runtime proof check.
6. One dataset ingestion proof check against BONES SEED.

## Scope Boundaries
Included:
- Track 1 agentic workflow with Qwen planner.
- Kimodo-based multi-character motion execution and blending.
- BONES SEED dataset browsing/downloading integration.
- Gradio Space frontend published under the lablab organization.
- AMD backend runtime path.
- Jupyter notebooks.
- K8s and Slurm templates.

Excluded unless ahead of schedule:
- Full model fine-tuning pipeline on MI300X.
- Deep benchmark framework.
- Full production security hardening.

## Risks and Mitigations
1. Qwen output inconsistency.
Mitigation: strict schema parser and fallback templates.
2. AMD runtime dependency mismatches.
Mitigation: isolate hardware settings and keep CPU-safe fallback for non-critical tests.
3. Time overrun from orchestration complexity.
Mitigation: keep K8s and Slurm as templates; only one must be actively demonstrated.
4. Multi-character drift.
Mitigation: deterministic scheduler and seeded replay tests.

## Build in Public Checklist (Extra Challenge)
1. Post update 1: architecture decision and first demo clip.
2. Post update 2: AMD runtime notes and lessons learned.
3. Publish repo or technical walkthrough with reproducible steps.
4. Include meaningful ROCm and AMD Developer Cloud feedback notes.
# Get container logs (SSE)
curl -N \
     -H "Authorization: Bearer $HF_TOKEN" \
     "https://huggingface.co/api/spaces/lablab-ai-amd-developer-hackathon/movimento/logs/run"

# Get build logs (SSE)
curl -N \
     -H "Authorization: Bearer $HF_TOKEN" \
     "https://huggingface.co/api/spaces/lablab-ai-amd-developer-hackathon/movimento/logs/build"