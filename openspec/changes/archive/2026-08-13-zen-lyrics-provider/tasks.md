# Tasks: Zen Lyrics Provider

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 (incl. tests) |
| 400-line budget risk | Low (project budget: 800) |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Provider refactor + Zen cascade + config + docs | PR 1 (only) | `python3 -m pytest tests/test_lyrics_providers.py tests/test_integration.py` | N/A — unit/integration only; mocked httpx, no live LLM call | Revert single commit: `_build_providers()` drops Zen entries, config fields removed, `has_any_llm_key()` restored |

## Phase 1: RED Tests (strict TDD — write first)

- [x] 1.1 `tests/test_lyrics_providers.py`: add `TestZenProvider` — `patch.object(provider.client, "post", new_callable=AsyncMock)` pattern: valid response → `LyricsResult` with `provider == "zen-big-pickle"`; JSON read from `content` while `reasoning_content` present (RQ-LYR-03)
- [x] 1.2 `tests/test_lyrics_providers.py`: `TestZenProvider` — empty `content` → `None`; HTTP error → `None`; `ZenProvider(api_key="")` raises `ValueError` (RQ-LYR-03, RQ-LYR-05)
- [x] 1.3 `tests/test_lyrics_providers.py`: cascade order `zen-big-pickle` → `zen-nemotron` → `openai` → `gemini` → `openrouter`; with `ZEN_API_KEY` unset, cascade starts at `openai` (RQ-LYR-03)
- [x] 1.4 `tests/test_integration.py` `TestStartupValidation` (~L832-914): `has_any_llm_key()` true with only `ZEN_API_KEY` set; false when `ZEN_API_KEY` also empty (RQ-LYR-05)

## Phase 2: GREEN Implementation

- [x] 2.1 `app/lyrics/providers.py`: extract `OpenAICompatProvider(BaseProvider)` — init `(name, api_key, model, base_url, headers)`; move shared `generate()` (POST `/chat/completions`, `choices[0]["message"]["content"]`, `_parse_lyrics_json`) from `OpenRouterProvider`
- [x] 2.2 `app/lyrics/providers.py`: refactor `OpenRouterProvider(api_key)` to subclass `OpenAICompatProvider` (preserve public signature); add `ZenProvider(api_key, model)` — base_url `https://opencode.ai/zen/v1`, Bearer auth
- [x] 2.3 `app/config.py`: add `ZEN_API_KEY`, `ZEN_PRIMARY_MODEL="big-pickle"`, `ZEN_SECONDARY_MODEL="nemotron-3-ultra-free"` under LLM block (L19-22); include `ZEN_API_KEY` in `has_any_llm_key()` (L82-84)
- [x] 2.4 `app/lyrics/__init__.py`: `_build_providers()` — two Zen entries (`zen-big-pickle` first) then OpenAI/Gemini/OpenRouter; update "No LLM providers configured" message (L88-90) to list Zen
- [x] 2.5 `app/main.py`: lifespan key-list RuntimeError (L69-72) includes `ZEN_API_KEY`

## Phase 3: Verification

- [x] 3.1 `python3 -m pytest` — full suite green, incl. preserved OpenRouter tests
- [x] 3.2 `python3 -m mypy app/ --ignore-missing-imports`
- [x] 3.3 `python3 -m ruff check .`

## Phase 4: Documentation

- [x] 4.1 `.env.example`: Zen vars + cascade order `zen-big-pickle → zen-nemotron → openai → gemini → openrouter`
- [x] 4.2 `docs/api-reference.md`: env var table — add Zen rows (leave stale `MISTRAL_API_KEY`/`GOOGLE_API_KEY` per out-of-scope)
- [x] 4.3 Grep all 4 key-list refs (`main.py`, `__init__.py`, `.env.example`, `docs/api-reference.md`) + `has_any_llm_key()` — all list Zen
