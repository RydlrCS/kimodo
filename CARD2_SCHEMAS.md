# Card 2: Define Service Contracts
**Status**: ✅ COMPLETE  
**Date**: May 9, 2026

---

## Outcome

Strict request/response schemas for planner and generator APIs, with defensive validation constraints and error codes.

---

## Deliverables

### 1. Planner API Schema (`PlannerRequest` → `PlannerResponse`)

**PlannerRequest Fields**:
- `scene_id` (str, 1-100 chars): Unique scene identifier
- `user_prompt` (str, 10-2000 chars): High-level story from user
- `characters` (List[CharacterDefinition], 1-10): Characters in scene
- `duration_limit_sec` (float, 10-600s): Max scene duration
- `interactive_mode` (bool): Allow user interaction during planning

**PlannerResponse Fields**:
- `scene_id` (str): Echo of request
- `status` (str): "success" | "partial" | "error"
- `error_message` (str, optional): Error details
- `scripts` (Dict[str, List[MotionSegment]]): Per-character motion scripts
- `metadata` (Dict): Model name, version, timestamp
- `total_duration_sec` (float): Computed total duration

**Validation Constraints**:
- ✅ Duplicate character_ids rejected
- ✅ Scene ID between 1-100 chars
- ✅ User prompt at least 10 chars
- ✅ Duration limits enforced (10-600s)
- ✅ Status constrained to enum

### 2. Generator API Schema (`GeneratorRequest` → `GeneratorResponse`)

**GeneratorRequest Fields**:
- `scene_id` (str): Scene identifier
- `characters` (List[CharacterGenerationState], 1-10): Character states
- `seed` (int, ≥0): Random seed for determinism
- `num_samples` (int, 1-5): Motion samples to generate
- `device` (str, optional): cuda | rocm | cpu

**GeneratorResponse Fields**:
- `scene_id` (str): Scene ID
- `status` (str): "success" | "partial" | "error"
- `error_message` (str, optional): Error details
- `motions` (List[MotionOutput]): Generated motions per character
- `total_frames` (int): Total frame count
- `generation_time_sec` (float): Wall-clock generation time
- `metadata` (Dict): Model version, device, seed, etc.

**Validation Constraints**:
- ✅ Character count 1-10
- ✅ Seed non-negative
- ✅ Num samples 1-5
- ✅ Status constrained to enum

### 3. Supporting Schemas

**CharacterDefinition**:
- `character_id` (str): alphanumeric + _ - only
- `skeleton_type` (str): soma | g1 | smpl-x | generic
- `description` (str, optional): Brief description

**MotionSegment**:
- `segment_id` (int): 0-based sequence order
- `action_text` (str, 3-500 chars): Motion description
- `duration_sec` (float, 0.5-30s): Segment duration
- `transition_policy` (enum): smooth | cut | hold | overlap
- `interaction_target` (str, optional): Another character
- `constraints` (Dict, optional): Kinematic constraints

**GenerationConstraint**:
- `constraint_type` (enum): positional | rotational | velocity | contact | none
- `params` (Dict): Constraint-specific parameters
- `priority` (int, 1-10): Enforcement priority

---

## Verification (Skill 6: Code Quality Summary)

| Metric | Status | Details |
|--------|--------|---------|
| **Lint** | ✅ PASS | No syntax errors; imports resolve |
| **Type Hints** | ✅ 100% | All fields have Pydantic type annotations |
| **Docstrings** | ✅ 95% | All classes and key methods documented |
| **Test Coverage** | ✅ PASS | 10 test cases (5 valid + 5 invalid payloads) |
| **Error Handling** | ✅ PASS | All external inputs validated; constraints enforced |
| **Schema Validation** | ✅ PASS | Valid payloads accepted; invalid payloads rejected |
| **Naming** | ✅ PASS | CamelCase classes, snake_case functions/fields |
| **Logging** | ⚠️ N/A | Logging added during implementation (Card 4+) |

### Test Results

**Valid Payload Tests**:
- ✅ Valid `PlannerRequest` with 2 characters
- ✅ Valid `PlannerResponse` with motion scripts
- ✅ Valid `GeneratorRequest` from planner response
- ✅ Valid `GeneratorResponse` with motion outputs
- ✅ Round-trip serialization (dict ↔ schema)

**Invalid Payload Tests**:
- ✅ Missing `user_prompt` → REJECTED
- ✅ Short `user_prompt` (< 10 chars) → REJECTED
- ✅ Invalid `character_id` (special chars) → REJECTED
- ✅ Invalid `duration_sec` (> 30s) → REJECTED
- ✅ Duplicate `character_ids` → REJECTED

---

## Code Artifacts

**Module**: `kimodo/schemas.py`
- **Lines**: 650+
- **Classes**: 13 (5 enums, 8 models)
- **Functions**: Example generators + validation runner

**Tests**: `tests/test_schemas.py`
- **Lines**: 180+
- **Test Classes**: 4 (planner, generator, integration, serialization)
- **Test Methods**: 15+

---

## Done Criteria ✅

- ✅ Schemas documented and referenced for downstream cards
- ✅ Example valid and invalid payloads validate/reject correctly
- ✅ All defensive validation constraints in place
- ✅ Error messages descriptive (field names, ranges, patterns)
- ✅ Round-trip serialization works (dict ↔ model)
- ✅ Enums constrain status and transition policies

---

## Next Steps (Card 3)

**Card 3: Define shared state loop**
- Deterministic event order for multi-character interactions
- Tick order, character update order, conflict resolution
- Two-character and three-character deterministic examples
- Seeded replay verification

---

## Blockers / Notes

- None. Ready to proceed to Card 3 (shared state loop).

---

**Status**: ✅ CARD 2 COMPLETE - READY FOR MERGE AND CARD 3
