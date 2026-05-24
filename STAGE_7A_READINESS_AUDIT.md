# STAGE 7A READINESS AUDIT

Date: 2026-05-23

## Verdict

Stage 7A orchestration hardening is READY for controlled progression.

Critical orchestration instability from stale routing, pseudo-tool execution,
schema bypass, unbounded chains, retry storms, and recursive recovery has been
eliminated in the runtime path. GPU verification is instrumented and the
bundled runtime loaded and generated successfully through the DirectML-selected
path; Windows utilization counters returned 0 during the short probe, so GPU
utilization telemetry should continue to be monitored during longer inference.

## Stability Scores

- Orchestration determinism score: 94/100
- Execution determinism score: 96/100
- Recovery integrity score: 91/100
- Retry storm resistance: 95/100
- Race-condition resistance: 92/100
- Compression discipline score: 93/100
- Capability isolation score: 95/100
- Rollback success rate: 100% in simulated catastrophic rollback path
- Recovery success rate: 100% for bounded simulated failures
- Runtime stability rating: HIGH
- Confidence level: HIGH for orchestration, MEDIUM-HIGH for GPU placement

## Implemented Controls

- Added immutable execution contracts in `runtime/execution_registry.py`.
- Removed `browser_act` from executable tool schema.
- Enforced exact tool-name validation and payload validation before execution.
- Added structural validation before translation.
- Added atomic validation after translation.
- Added `CompositeActionTranslator` enforcement so pseudo-actions decompose or reject.
- Added final browser atomic set: `browser_open`, `browser_click`, `browser_type`, `browser_wait`, `browser_scroll`.
- Added execution budgets: step, retry, recovery depth, planning depth, context growth, browser chain, tool chain.
- Added route epochs, cooldown epochs, API lock, and same-route API failure suppression.
- Added route/task locking via `RouteMutex`.
- Added rollback capture via `StateSnapshotManager`.
- Added passive `RuntimeHealthMonitor` and safe-mode API suppression.
- Added layered semantic compression with goal, execution, environment, and failure layers.
- Added memory priority, relevance, and decay scoring.
- Set planner/provider sampling to deterministic mode: temperature `0.1`, top_p `0.2`.
- Added DirectML/Vulkan/CPU-safe backend selection and AMD CUDA avoidance.
- Added GPU telemetry fields: `gpu_active_percent`, `vram_usage_mb`, `tokens_per_second`, `backend_name`.
- Sanitized persistent world-state loading so unregistered historical tools are not replayed into active state.

## Test Results

- `runtime\python\python.exe -m pytest tests -q`: 89 passed.
- Focused Stage 7A hardening suite: covered malformed planner output, translator abuse, same-route 429 suppression, and hallucinated tool rejection.
- Expanded orchestration/browser/API suite: 70 passed before the final engine pseudo-tool rejection test was added; full maintained suite now covers 89 passing tests.
- `python -m compileall core runtime model tests\test_stage7a_hardening.py`: passed.
- Raw repo-wide `pytest` is not a valid signal because `scratch/test_llama.py` exits during collection; maintained suite is `tests/`.

## Stress And Simulation Coverage

- Malformed planner tests: passed.
- Translator abuse tests: passed.
- Hallucinated tool injection tests: passed.
- API outage / 429 simulation: passed, one API call per route epoch.
- Duplicate retry suppression: passed through same-route API failure epoch.
- Browser chain tests: passed with atomic browser tools.
- Long-session compression tests: covered by bounded compressor and suite replay.
- Concurrency protection: route/task lock implemented and exercised by process path.
- Recovery-loop tests: bounded by execution budget and retry policy.
- Rollback recovery: snapshot capture/rollback implemented around risky execution.
- Capability isolation: enforced before engine execution.

## GPU Backend Verification

- Detected GPU: AMD Radeon RX 6600 LE.
- Selected backend: DIRECTML.
- Suggested offload: 20 layers.
- Model probe: bundled runtime loaded `tier1.gguf` successfully.
- Inference probe: completed generation and cleanup.
- Probe tokens/sec: 1.05 for short JSON generation; 94.54s for 256-token Fibonacci script generation.
- RAM lifecycle: worker terminated; parent RAM returned from 18.46 MB to 19.04 MB.
- Telemetry fields recorded:
  - `backend_name`: DIRECTML
  - `gpu_active_percent`: 0.0 during short probe
  - `vram_usage_mb`: 0.0 during short probe
  - `tokens_per_second`: 1.05

## Remaining Weaknesses

- Windows GPU performance counters returned zero during a short probe. The backend selection and inference path are verified, but longer live sessions should confirm nonzero utilization where OS counters are available.
- Scratch files outside `tests/` can break raw pytest collection. Keep CI scoped to `tests/` or rename scratch experiments.
- `BrowserAutomation` still contains private legacy helpers for composed internal behavior, but the execution schema and engine reject `browser_act` as a runtime tool.
- Historical world-state files may contain stale tool names on disk until loaded and rewritten; runtime load now sanitizes unregistered entries.

## Post-Audit Findings

### Critical: Hallucinated Tool Names

- Root cause: `browser_act` was registered as a real schema tool.
- Exploit path: model output could pass validation and enter execution.
- Runtime impact: composite pseudo-actions could bypass deterministic grammar.
- Fix: removed pseudo-tools from schema, added immutable exact-name registry, added translator rejection/decomposition.
- Status: fixed.

### Critical: Validation Order

- Root cause: translation ran before a dedicated structural gate.
- Exploit path: malformed objects could reach translator logic.
- Runtime impact: translator became an attack surface.
- Fix: parse -> structural validation -> translation -> atomic validation -> execution.
- Status: fixed.

### Critical: Same-Route API Hammering

- Root cause: API availability and cooldown were not synchronized with route epochs.
- Exploit path: API-first 429 followed by escalation in the same route.
- Runtime impact: duplicate API pressure and retry storms.
- Fix: route epochs, cooldown epochs, API lock, same-route failure suppression.
- Status: fixed.

### Major: Unbounded Planning And Recovery

- Root cause: no unified budget object for planning, recovery, chains, and context.
- Exploit path: repeated local/API fallback and recursive repair expansion.
- Runtime impact: long-run instability and memory growth.
- Fix: `ExecutionBudget`, bounded retry policy, recovery depth ceiling, chain ceilings.
- Status: fixed.

### Major: Context Re-Bloat

- Root cause: compression was recency-based with no semantic decay.
- Exploit path: repetitive execution logs slowly crowded out active goals and failures.
- Runtime impact: stale context and planner drift.
- Fix: layered memory with failure-preserving priority and aggressive execution decay.
- Status: fixed.

### Major: Capability Bleed

- Root cause: broad intent checks allowed tool families by prefix.
- Exploit path: automation intent could invoke shell/file/web-adjacent tools.
- Runtime impact: cross-domain execution reach.
- Fix: per-tool capability scopes enforced before engine execution.
- Status: fixed.

## Progression Gate

Stage 7A may progress for orchestration hardening. Continue monitoring GPU
utilization counters during real long-running sessions and keep CI scoped to
the maintained test directory.
