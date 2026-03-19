---
phase: 1
slug: runpod-worker
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-18
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds (mocked model) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | GEN-01 | unit | `pytest tests/test_handler.py -k input` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GEN-02 | unit | `pytest tests/test_generator.py -k model_load` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | BATCH-01 | unit | `pytest tests/test_handler.py -k batch` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | BATCH-02 | unit | `pytest tests/test_handler.py -k error_isolation` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | BATCH-04 | unit | `pytest tests/test_handler.py -k response` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | STOR-01 | unit | `pytest tests/test_generator.py -k upload` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_handler.py` — stubs for handler input parsing, batch processing, error isolation
- [ ] `tests/test_generator.py` — stubs for model loading, generation, upload
- [ ] `tests/conftest.py` — shared fixtures (mock model, mock Supabase client)
- [ ] `pytest` install — no framework detected yet

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WAV generation quality | GEN-03, GEN-04 | Requires actual GPU + model | Deploy to RunPod, submit test batch, listen to output |
| VRAM usage on A5000/3090 | GEN-05, GEN-07 | Requires actual GPU | Monitor `nvidia-smi` during generation on RunPod |
| Docker cold start time | GEN-06 | Requires RunPod deployment | Time from endpoint creation to first successful job |
| Supabase public URL accessible | STOR-02 | Requires live Supabase bucket | curl the returned URL, verify audio plays |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
