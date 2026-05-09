# Copilot Skills: Verification Workflows for 24-Hour Sprint

This document defines reusable verification prompts and quality gates to run before completing each card. Use these skills as quality checkpoints before marking any card as done.

---

## Skill 1: Lint & Type Checking

**When to use**: After writing any Python module or modifying existing code.

**Prompt template**:
```
Run lint and type checking on the following files:
- {file_paths}

Use these tools:
1. flake8 with line length 120 (as per pyproject.toml config)
2. ruff check for import sorting
3. mypy for type hints (if applicable)
4. pylint for code complexity

Report any:
- PEP 8 violations
- Unused imports
- Type mismatches
- Cyclomatic complexity > 10
- Missing docstrings on public functions

Output format: [PASS] if all checks pass, or [FAIL] with itemized issues.
```

**Verification gate**: No high-severity lint errors allowed (warnings OK).

---

## Skill 2: Error Handling & Defensive Checks

**When to use**: Before integrating any API endpoint or request handler.

**Prompt template**:
```
Review the following code for error handling:
- {file_paths}

Check for:
1. All external inputs validated (HF Hub calls, user prompts, file paths)
2. All error paths have try/except or explicit error codes
3. Logging on entry/exit for critical paths
4. Graceful degradation (fallback behavior documented)
5. No silent failures or swallowed exceptions
6. Timeout handling for network calls
7. Resource cleanup (file handles, connections)

Output: [PASS] or [FAIL] with specific lines that need error handling.
```

**Verification gate**: 100% of external inputs must be validated. All exceptions explicitly handled.

---

## Skill 3: Schema Validation & API Contract

**When to use**: Before using any request/response schema (Pydantic models, JSON contracts).

**Prompt template**:
```
Validate the schema definitions in:
- {file_paths}

For each schema:
1. Test valid payload examples (3+ cases)
2. Test invalid payloads (type mismatch, missing required field, invalid enum)
3. Check field constraints (min/max length, regex patterns)
4. Verify error messages are clear for validation failures
5. Ensure schema is documented with field descriptions

Output format:
✓ Valid payload 1: {example}
✗ Invalid payload 1 (reason): {example}
[PASS] if all test cases behave correctly, or [FAIL] with details.
```

**Verification gate**: All schemas must reject invalid payloads and accept valid ones.

---

## Skill 4: Deterministic Behavior & Seeded Tests

**When to use**: Before any multi-character or stochastic component (scheduler, diffusion, random sampling).

**Prompt template**:
```
Test deterministic behavior for:
- {file_paths}

Procedure:
1. Initialize component with seed={seed}
2. Run scenario N times with identical inputs
3. Verify outputs are byte-identical across runs
4. Test at least 2 scenarios (two-character, three-character)
5. Log output hashes for audit trail

Output format:
Scenario 1 (2-char): Run 1={hash}, Run 2={hash}, Run 3={hash} -> [PASS] if all match
Scenario 2 (3-char): Run 1={hash}, Run 2={hash}, Run 3={hash} -> [PASS] if all match
[PASS] or [FAIL] with digest mismatch details.
```

**Verification gate**: Same seed must produce byte-identical outputs. No RNG leakage.

---

## Skill 5: Integration Smoke Test

**When to use**: After integrating two or more components (e.g., planner → Kimodo, scheduler + state).

**Prompt template**:
```
Run e2e smoke test for:
- {module_paths}

Test procedure:
1. Start fresh session/state
2. Call planner with sample prompt
3. Validate planner output (schema check)
4. Pass output to generator/scheduler
5. Verify no crashes, timeouts, or corrupted state
6. Check output format matches expected schema
7. Verify logging shows full request lifecycle

Test cases (minimum 3):
- Minimal valid input (1 character, 1 action)
- Normal case (2 characters, 3 actions)
- Extreme case (3 characters, 10 actions)

Output format:
Test 1 (minimal): [PASS] or [FAIL] with error
Test 2 (normal): [PASS] or [FAIL] with error
Test 3 (extreme): [PASS] or [FAIL] with error
Overall: [PASS] or [FAIL].
```

**Verification gate**: All 3 test cases must pass without crashes or state corruption.

---

## Skill 6: Code Quality Summary

**When to use**: Final check before submitting a card (lint + tests + coverage).

**Prompt template**:
```
Generate code quality report for:
- {module_paths}

Report should include:
1. Lint status: flake8 + ruff output (extract key metrics)
2. Type hints coverage: % of functions with type annotations
3. Docstring coverage: % of public functions with docstrings
4. Test coverage: % of code lines covered by unit tests
5. Error handling score: % of inputs validated
6. Naming consistency: any inconsistencies with convention (CamelCase classes, snake_case functions)
7. Logging summary: entry/exit logged on critical paths (list specific functions)

Output format:
| Metric | Status | Details |
|--------|--------|---------|
| Lint | PASS | 0 errors, 2 warnings |
| Type Hints | 85% | {list uncovered functions} |
| Docstrings | 90% | {list undocumented functions} |
| Test Coverage | 75% | {list low-coverage modules} |
| Error Handling | PASS | 100% input validation |
| Naming | PASS | Consistent conventions |
| Logging | PASS | 8/9 critical paths logged |

Final verdict: [PASS] if all major metrics >= threshold, or [FAIL] with required fixes.
```

**Verification gate**: Lint PASS, Type hints ≥70%, Docstrings ≥80%, Test coverage ≥60%, Error handling 100%.

---

## Skill 7: API Contract & Live Endpoint Test

**When to use**: After deploying a new endpoint or API method.

**Prompt template**:
```
Test API endpoint:
- {endpoint_url or function_path}

Test cases:
1. Valid request (all fields):
   Input: {example_valid_payload}
   Expected: {expected_response_schema}
   Verify: Response schema matches, HTTP 200/201

2. Invalid request (missing required field):
   Input: {example_invalid_payload}
   Expected: HTTP 400 with error message
   Verify: Error message is descriptive

3. Boundary case (edge values):
   Input: {example_boundary_payload}
   Expected: {expected_response}
   Verify: Handled gracefully (not crashed)

4. Concurrent requests (if applicable):
   Fire 5 parallel requests, verify no state corruption

Output format:
✓ Test 1 (valid): {actual_response}
✓ Test 2 (invalid): {actual_error}
✓ Test 3 (boundary): {actual_response}
✓ Test 4 (concurrent): All responses identical and correct
[PASS] or [FAIL] with mismatches.
```

**Verification gate**: All 4 test cases must pass. Responses match contract.

---

## Skill 8: Build & Deployment Readiness

**When to use**: Before pushing to GitHub or deploying to Space.

**Prompt template**:
```
Pre-deployment checklist:
- {repository_path}

Verify:
1. All imports resolve (no missing dependencies)
2. No hardcoded secrets or credentials
3. No NVIDIA-only assumptions (AMD path clean)
4. Environment variables documented (.env.example or README)
5. Docker/HF Space entrypoint defined if needed
6. No broken file paths (all relative or properly resolved)
7. Favicon and static assets included
8. README updated with new features or API changes

Output format:
✓ Imports: OK
✓ Secrets: No hardcoded credentials found
✓ AMD path: Device selection OS-agnostic
✓ Env vars: Documented in README
✓ Deployment: Entrypoint configured
✓ Paths: All resolved correctly
✓ Assets: Favicon present at {path}
✓ Docs: README current
[PASS] or [FAIL] with specific issues.
```

**Verification gate**: All checks must pass. No secrets, AMD-compatible, documented.

---

## Skill 9: Space Log Monitoring

**When to use**: After deploying to HF Space to verify health.

**Setup commands**:
```bash
# Monitor container logs (real-time)
curl -N \
     -H "Authorization: Bearer $HF_TOKEN" \
     "https://huggingface.co/api/spaces/lablab-ai-amd-developer-hackathon/movimento/logs/run"

# Monitor build logs
curl -N \
     -H "Authorization: Bearer $HF_TOKEN" \
     "https://huggingface.co/api/spaces/lablab-ai-amd-developer-hackathon/movimento/logs/build"

# Alternative: Check Space status via API
curl -H "Authorization: Bearer $HF_TOKEN" \
     "https://huggingface.co/api/spaces/lablab-ai-amd-developer-hackathon/movimento"
```

**Verification prompt**:
```
Monitor Space logs and report:
1. Build status: [BUILDING/RUNNING/FAILURE]
2. Runtime errors: Any exception traces in container logs
3. Startup time: Seconds to ready state
4. Memory usage: Approx. MB at idle
5. First request latency: Seconds for /run or inference endpoint
6. Graceful shutdown: Verify cleanup on restart

Output format:
Build: RUNNING (took 45s to ready)
Container logs: No errors
Startup: 12s
Memory: 4200 MB
First request: 2.3s
Shutdown: Clean
[PASS] or [FAIL] with specific issues.
```

**Verification gate**: Build succeeds, container runs without errors, first request succeeds.

---

## Running Skills in Sequence (Per Card Workflow)

**Before marking a card complete, run these skills in order**:

1. **Code-only cards** (schemas, adapters, utilities):
   - Skill 2 (Error Handling)
   - Skill 3 (Schema Validation) — if schemas defined
   - Skill 1 (Lint & Type)
   - Skill 6 (Code Quality Summary)

2. **Integration cards** (planner, generator, scheduler):
   - Skill 2 (Error Handling)
   - Skill 5 (Integration Smoke Test)
   - Skill 4 (Deterministic Behavior) — if applicable
   - Skill 1 (Lint & Type)
   - Skill 6 (Code Quality Summary)

3. **API/Endpoint cards** (Gradio UI, Space frontend):
   - Skill 7 (API Contract & Live Endpoint Test)
   - Skill 8 (Build & Deployment Readiness)
   - Skill 9 (Space Log Monitoring) — if Space deployed

4. **Dev/Demo cards** (notebooks, templates):
   - Skill 1 (Lint & Type)
   - Skill 5 (Integration Smoke Test, if runnable)
   - Skill 6 (Code Quality Summary)

---

## Thresholds & Acceptance Criteria

| Skill | Threshold | Action |
|-------|-----------|--------|
| Lint (flake8, ruff) | 0 high-severity | Fail card if violated |
| Type hints (mypy) | ≥70% coverage | Warning if <70%, fail if <50% |
| Docstrings | ≥80% public functions | Warning if <80%, fail if <60% |
| Test coverage | ≥60% of code | Warning if <60%, fail if <40% |
| Error handling | 100% input validation | Fail card if not met |
| Deterministic | Byte-identical outputs (same seed) | Fail card if not met |
| Smoke test | All 3 test cases pass | Fail card if any fail |
| API contract | All test cases match schema | Fail card if mismatches |
| Build & deploy | All checks pass | Fail card if any fail |
| Space health | Container runs, first request OK | Fail card if unavailable |

---

## Card Verification Checklist Template

Use this template at the end of each card before requesting approval:

```
## Card {N}: {Title}

### Code Quality (Skill 1, 6)
- [ ] Lint: flake8 + ruff PASS
- [ ] Type hints: {X}% coverage (>70%)
- [ ] Docstrings: {X}% documented (>80%)
- [ ] Naming: CamelCase classes, snake_case functions

### Error Handling (Skill 2)
- [ ] All external inputs validated
- [ ] All error paths handled with try/except
- [ ] Entry/exit logging on critical paths
- [ ] Graceful fallback behavior documented

### Schema/API (Skill 3, 7)
- [ ] Valid payloads accepted
- [ ] Invalid payloads rejected
- [ ] Error messages descriptive
- [ ] All test cases pass

### Integration (Skill 5)
- [ ] Minimal case passes
- [ ] Normal case passes
- [ ] Extreme case passes
- [ ] No state corruption

### Determinism (Skill 4)
- [ ] Byte-identical outputs with same seed (if applicable)
- [ ] Seeded replay test passes

### Deployment (Skill 8, 9)
- [ ] No hardcoded secrets
- [ ] AMD-compatible path
- [ ] Env vars documented
- [ ] Space health check passes (if deployed)

**Final verdict**: [PASS] Ready to merge PR, or [FAIL] with blockers listed.
```

---

## Notes

- All skills are self-contained and can be run in parallel after code completion.
- Use these skills before every PR submission to catch issues early.
- Update thresholds if team consensus shifts (e.g., test coverage ≥75%).
- Keep a log of skill runs and outcomes for auditing quality gates.

---

**Skills document created**: May 9, 2026  
**Last updated**: May 9, 2026  
**Status**: Ready for use in Card 2+ verification workflows
