# Card 3: Shared State Loop (Deterministic Event Scheduler)
**Status**: ✅ COMPLETE  
**Date**: May 9, 2026

---

## Outcome

Deterministic event order for multi-character interactions in one port/session with:
- Synchronized tick-based timeline
- Per-character state containers
- Deterministic conflict resolution (same seed → same outcome)
- Support for ≥3 active characters

---

## Deliverables

### 1. Core Event Loop (`DeterministicLoop` class)

**Features**:
- ✅ Synchronized time with per-character state tracking
- ✅ Deterministic RNG seeded from loop seed
- ✅ Conflict resolution policies: PRIORITY_BASED, FIFO, COOLDOWN
- ✅ Per-character interaction cooldown (prevents rapid re-interactions)
- ✅ Tick history log for auditing

**State Management**:
- `CharacterSlot`: Per-character state container
  - Current state (IDLE, BUSY, TRANSITIONING, INTERACTING)
  - Segment execution state (segment_index, frames_elapsed, total_frames)
  - Interaction tracking (target, last_time, cooldown)
  - Priority for conflict resolution
  
- `LoopTick`: Tick metadata and events
  - Frame and time counters
  - Character state updates
  - Completed segments
  - Resolved interactions

### 2. Deterministic Tick Ordering

**Per-tick event order** (deterministic):
1. Character segment state updates (frame progression)
2. Check for segment completion
3. Detect pending interactions
4. Resolve conflicts with deterministic policy
5. Update interaction timestamps
6. Advance time

**For same seed**: Same tick order, same state transitions, byte-identical outputs.

### 3. Conflict Resolution Policies

**PRIORITY_BASED**:
- Higher priority character wins interaction
- Tiebreaker: alphabetical (deterministic)

**FIFO**:
- Earlier interaction time wins
- Ensures fairness over time

**COOLDOWN**:
- Check if cooldown expired since last interaction
- Both characters can interact if ready
- Uses priority as tiebreaker

### 4. Test Scenarios

**Scenario 1: Two-Character Deterministic Replay**
- Register dancer1 and dancer2 (equal priority)
- Advance 60 ticks (frames)
- Record state hash at each frame
- Replay with same seed
- **Result**: ✅ PASS - Hashes match exactly

**Scenario 2: Three-Character Priority-Based Conflict Resolution**
- Register leader (priority 3), follower1 (priority 2), follower2 (priority 1)
- Advance 60 ticks with interaction attempts
- Record state hash at each frame
- Replay with same seed
- **Result**: ✅ PASS - Hashes match exactly

**Scenario 3: Different Seed Produces Different Outcome**
- Create two loops with seed=42 and seed=99
- Advance 30 ticks
- Record state hashes
- **Result**: ✅ PASS - Different seeds → different hashes

---

## Verification (Skill 4: Deterministic Behavior & Skill 5: Integration Test)

| Test | Status | Details |
|------|--------|---------|
| **2-character replay** | ✅ PASS | Same seed produces 60 identical hashes |
| **3-character replay** | ✅ PASS | Priority-based conflict resolution is deterministic |
| **Seed differentiation** | ✅ PASS | Different seeds produce observable differences |
| **Cooldown enforcement** | ✅ PASS | Interaction spacing respected |
| **State tracking** | ✅ PASS | CharacterSlot updates correctly |
| **RNG determinism** | ✅ PASS | LCG seeded loop produces reproducible sequence |

---

## Code Artifacts

**Module**: `kimodo/scheduler.py`
- **Lines**: 450+
- **Classes**: 6 (enums, state dataclasses, main loop)
  - `CharacterState` (enum)
  - `ConflictResolutionPolicy` (enum)
  - `CharacterSegmentState` (dataclass)
  - `CharacterSlot` (dataclass)
  - `LoopTick` (dataclass)
  - `DeterministicLoop` (main class)
- **Functions**: Test scenario generators + replay verification

---

## Architecture: Event Loop Data Flow

```
┌─────────────────────────────────────────────────────┐
│ Start of Tick                                       │
│ (tick_number, frame_number, time_ms)                │
└────────────────┬────────────────────────────────────┘
                 ▼
         ┌─────────────────┐
         │ Character State │
         │ Updates         │
         │ (segment prog.) │
         └────────┬────────┘
                  ▼
         ┌─────────────────┐
         │ Check           │
         │ Completions     │
         └────────┬────────┘
                  ▼
         ┌─────────────────┐
         │ Detect          │
         │ Interactions    │
         └────────┬────────┘
                  ▼
         ┌─────────────────┐
         │ Resolve         │
         │ Conflicts       │
         │ (deterministic) │
         └────────┬────────┘
                  ▼
         ┌─────────────────┐
         │ Update          │
         │ Last Interaction│
         │ Times           │
         └────────┬────────┘
                  ▼
         ┌─────────────────┐
         │ Advance Time    │
         └────────┬────────┘
                  ▼
┌─────────────────────────────────────────────────────┐
│ End of Tick                                         │
│ return LoopTick(updates, interactions, state_hash) │
└─────────────────────────────────────────────────────┘
```

---

## Done Criteria ✅

- ✅ Deterministic event order specified
- ✅ Tick order, character update order defined
- ✅ Conflict resolution policy implemented
- ✅ Two-character deterministic example: PASS
- ✅ Three-character deterministic example: PASS
- ✅ Byte-identical replay verification: PASS
- ✅ Different seeds produce different outcomes: PASS
- ✅ Loop spec merged into architecture

---

## Key Properties

1. **Determinism**: Same seed → Same state at any tick
2. **Seeded Replay**: Full motion sequence reproducible
3. **Conflict Resolution**: Deterministic & configurable
4. **Cooldown Enforcement**: Prevents interaction spam
5. **Multi-Character**: Supports ≥3 concurrent characters
6. **In-Process**: Single Python process, no RPC/distribution

---

## Next Steps (Card 4)

**Card 4: Qwen Copilot Planner Adapter**
- Build planner endpoint with Qwen LLM
- Parse user prompt → validated motion script (JSON)
- Implement retries and fallback templates
- Verify 10+ prompts pass schema validation

---

## Blockers / Notes

- None. Ready to proceed to Card 4 (Qwen planner).

---

**Status**: ✅ CARD 3 COMPLETE - READY FOR MERGE AND CARD 4
