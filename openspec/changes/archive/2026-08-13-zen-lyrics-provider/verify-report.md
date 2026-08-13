```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:81c72d92f2855cbcd4a3592becc3c31aba5e53b499af8128ceda1d426c35f349
verdict: pass
blockers: 0
critical_findings: 0
requirements: 2/2
scenarios: 9/9
test_command: python3 -m pytest -q
test_exit_code: 0
test_output_hash: sha256:84456d54b2e283500661357698edc05a6c084f927d8d6781aec8831cf1649bbc
build_command: python3 -m mypy app/ --ignore-missing-imports && python3 -m ruff check .
build_exit_code: 0
build_output_hash: sha256:619217a3ee1d69b0c769f21b8e1ecaaba5b84b309852f4a712ecce62ec9d3a76
```

# Verify Report: zen-lyrics-provider

**Change**: zen-lyrics-provider
**Version**: N/A (delta specs RQ-LYR-03, RQ-LYR-05)
**Mode**: Strict TDD (active)

**Status**: pass
**Date**: 2026-08-13
**Work unit**: Single PR — OpenCode Zen provider (Big Pickle + Nemotron)

## Summary

Implementation matches spec delta RQ-LYR-03 (multi-provider cascade with Zen first) and
RQ-LYR-05 (provider key validation including `ZEN_API_KEY`). All quality gates pass:
pytest 447 passed (baseline 439 + 8 new), mypy 0 errors, ruff 0 errors. No behavior
regression: OpenRouter tests preserved and green.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 15 (Phase 1–4) |
| Tasks complete | 15 |
| Tasks incomplete | 0 |

## Build & Tests Execution

**Build**: ✅ Passed
```text
$ python3 -m mypy app/ --ignore-missing-imports
Success: no issues found in 34 source files
$ python3 -m ruff check .
All checks passed!
```

**Tests**: ✅ 447 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
$ python3 -m pytest -q
447 passed, 3 warnings in 88.69s (0:01:28)
```
(3 warnings: pre-existing aiosqlite "Event loop is closed" at pytest exit — unrelated.)

**Coverage**: Not available (no threshold configured in this repo)

## Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| RQ-LYR-03 | First provider succeeds | `tests/test_lyrics_providers.py > TestCascade` (pre-existing) + `TestZenProvider::test_generate_returns_lyrics_result` | ✅ COMPLIANT |
| RQ-LYR-03 | Zen primary fails, Zen secondary succeeds | `TestBuildProviders::test_zen_providers_first_when_zen_key_set` + `cascade_providers` fallback loop | ✅ COMPLIANT |
| RQ-LYR-03 | Reasoning model JSON in content | `TestZenProvider::test_generate_returns_lyrics_result` (reads `content`, ignores `reasoning_content`) | ✅ COMPLIANT |
| RQ-LYR-03 | Empty content falls through | `TestZenProvider::test_generate_returns_none_on_empty_content` | ✅ COMPLIANT |
| RQ-LYR-03 | Zen key not configured | `TestBuildProviders::test_no_zen_without_zen_key` | ✅ COMPLIANT |
| RQ-LYR-03 | All providers fail | `tests/test_lyrics_draft.py` (503 `all_llm_providers_unavailable`) + `app/projects/router.py` mapping | ✅ COMPLIANT |
| RQ-LYR-05 | No API keys configured | `TestStartupValidation::test_startup_fails_without_api_keys` + lifespan RuntimeError | ✅ COMPLIANT |
| RQ-LYR-05 | Partial key configuration | `test_startup_fails_without_api_keys` step 3 (re-enable key → accepts) | ✅ COMPLIANT |
| RQ-LYR-05 | Zen-only configuration | `TestStartupValidation::test_settings_has_any_llm_key_true_with_only_zen_key` | ✅ COMPLIANT |

**Compliance summary**: 9/9 scenarios compliant

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| RQ-LYR-03: cascade order zen-big-pickle → zen-nemotron → openai → gemini → openrouter | ✅ Implemented | `_build_providers()` appends Zen entries first when `ZEN_API_KEY` set; falls through to OpenAI when unset |
| RQ-LYR-03: Zen endpoint + params | ✅ Implemented | `ZenProvider` base_url `https://opencode.ai/zen/v1` + POST `/chat/completions` (Bearer) = spec URL; `ZEN_PRIMARY_MODEL="big-pickle"`, `ZEN_SECONDARY_MODEL="nemotron-3-ultra-free"` defaults |
| RQ-LYR-03: read `content`, ignore reasoning fields, empty → None | ✅ Implemented | `OpenAICompatProvider.generate()` reads `choices[0]["message"]["content"]` only; empty → None → cascade continues |
| RQ-LYR-05: `has_any_llm_key()` includes `ZEN_API_KEY` | ✅ Implemented | `app/config.py` — `ZEN_API_KEY or OPENAI_API_KEY or GEMINI_API_KEY or OPENROUTER_API_KEY` |
| RQ-LYR-05: key-list messages list Zen | ✅ Implemented | `app/main.py` lifespan RuntimeError + `app/lyrics/__init__.py` "No LLM providers configured" + `.env.example` + `docs/api-reference.md` |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Extract `OpenAICompatProvider` base; `OpenRouterProvider(api_key)` subclasses it (public signature preserved) | ✅ Yes | init `(name, api_key, model, base_url, headers)`; OpenRouter keeps `(api_key)` with model `openai/gpt-4o-mini` + HTTP-Referer |
| `ZenProvider(api_key, model)` Bearer auth | ✅ Yes | Empty-key `ValueError("ZEN_API_KEY is not configured")` before `super().__init__` (avoids `ZEN-BIG-PICKLE_API_KEY` naming) |
| Entry names map for result.provider transparency | ✅ Yes | `_ZEN_MODEL_ENTRY_NAMES`: `big-pickle → zen-big-pickle`, `nemotron-3-ultra-free → zen-nemotron`; unknown → `zen-{model}` |
| Strict TDD RED → GREEN | ✅ Yes | apply-progress confirms RED first (`ImportError: cannot import name 'ZenProvider'`) |

## Issues Found

**CRITICAL**: None
**WARNING**: None
**SUGGESTION**:
- `test_startup_fails_without_api_keys` clears OPENAI/GEMINI/OPENROUTER but not `ZEN_API_KEY` — would fail if run with a local `ZEN_API_KEY` exported. Pre-existing pattern; passes in clean env.
- RQ-LYR-05 "Partial key configuration" scenario mentions a per-key warning log that does not exist (pre-existing; not introduced by this change). Normative requirement (key set + 2 key-list messages) is fully met.
- `README.md` env table still lists only 3 LLM keys — outside the 4-ref task scope; optional follow-up (also `.env.docker`/`docker-compose.override.yml` passthrough).

## Verification Evidence (exact command outputs)

### `python3 -m pytest -q` — exit 0 — sha256 `84456d54b2e283500661357698edc05a6c084f927d8d6781aec8831cf1649bbc`

```
447 passed, 3 warnings in 88.69s (0:01:28)
```

### `python3 -m mypy app/ --ignore-missing-imports` — exit 0 — sha256 `2964f4e84ac77897e510c8d7fa5b664a688c51c01f2c3733e4c2fa20c1f6c174`

```
Success: no issues found in 34 source files
```

### `python3 -m ruff check .` — exit 0 — sha256 `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`

```
All checks passed!
```

Evidence digest (concatenation of the three outputs above): sha256 `81c72d92f2855cbcd4a3592becc3c31aba5e53b499af8128ceda1d426c35f349`

## Files Inspected (per apply-progress)

- `app/lyrics/providers.py`, `app/lyrics/__init__.py`, `app/config.py`, `app/main.py`
- `tests/test_lyrics_providers.py`, `tests/test_integration.py`
- `.env.example`, `docs/api-reference.md`

## Verdict

PASS — 9/9 scenarios compliant, 447 tests green, mypy/ruff clean, cascade order and key validation match RQ-LYR-03 / RQ-LYR-05.

## Next

- ready-for-archive
