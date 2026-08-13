# Proposal: Zen Lyrics Provider

## Intent

The lyrics cascade is degraded: OpenAI returns 429 (credits exhausted), Gemini 503 (down) — only OpenRouter actually works. Add OpenCode Zen as a FREE OpenAI-compatible provider, placed FIRST in the cascade: Big Pickle (`big-pickle`) primary, NVIDIA Nemotron (`nemotron-3-ultra-free`) secondary. Eliminates the current single-point-of-failure cost exposure and restores multi-provider resilience at zero marginal cost.

## Scope

### In Scope
- Extract `OpenAICompatProvider` base (parametrized: name, api_key, model, base_url, headers) from `OpenRouterProvider`'s generate flow; `OpenRouterProvider(api_key)` keeps public signature
- Add `ZenProvider(api_key, model)` hitting `https://opencode.ai/zen/v1/chat/completions`
- Two Zen cascade entries: `zen-big-pickle` → `zen-nemotron` → openai → gemini → openrouter
- Config: `ZEN_API_KEY` (gate) + `ZEN_PRIMARY_MODEL="big-pickle"` + `ZEN_SECONDARY_MODEL="nemotron-3-ultra-free"`; `has_any_llm_key()` includes Zen
- Tests: Zen class (OpenRouter `patch.object(client, "post")` pattern), cascade ordering, `has_any_llm_key` Zen case
- Docs/spec delta: `.env.example`, `docs/api-reference.md`, `app/main.py` + `__init__.py` error messages, lyrics-generation spec (RQ-LYR-03 table, RQ-LYR-05 wording)

### Out of Scope
- Third Nemotron variant (`nemotron-3.5-lightning-free`) — one-line settings + cascade entry later
- Stale doc rows (`MISTRAL_API_KEY`, `GOOGLE_API_KEY`) — optional cleanup, pending user decision
- Retrying/probing Zen health (cascade handles failure already)

## Capabilities

### New Capabilities
None — Zen is a provider inside the existing `lyrics-generation` capability.

### Modified Capabilities
- `lyrics-generation`: RQ-LYR-03 provider table gains Zen rows (zen-big-pickle, zen-nemotron); RQ-LYR-05 key-validation wording adds `ZEN_API_KEY` (cascade order: zen-big-pickle → zen-nemotron → openai → gemini → openrouter)

## Approach

A2 (from exploration): extract `OpenAICompatProvider` owning post `/chat/completions` → `choices[0]["message"]["content"]` → `_parse_lyrics_json`; `OpenRouterProvider` and `ZenProvider` subclass it. Reasoning models (Big Pickle, Nemotron) return JSON in `content` (verified) — keep reading `message["content"]`, ignore `reasoning_content`/`reasoning_details`; empty content → `None` → cascade falls through.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `app/lyrics/providers.py` | Modified | Extract `OpenAICompatProvider`; add `ZenProvider` |
| `app/lyrics/__init__.py` | Modified | `_build_providers()` order (Zen first) + error msg |
| `app/config.py` | Modified | 3 new Zen vars; `has_any_llm_key()` |
| `app/main.py` | Modified | Lifespan key-list message (~L69-72) |
| `tests/test_lyrics_providers.py` | Modified | Zen tests + cascade ordering |
| `tests/test_integration.py` | Modified | `has_any_llm_key()` Zen case (~L845-914) |
| `.env.example` | Modified | Zen vars + new order |
| `docs/api-reference.md` | Modified | Env var table |
| `openspec/specs/lyrics-generation/spec.md` | Modified | Delta: RQ-LYR-03, RQ-LYR-05 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Personal-key exposure (opencoe-go key in Railway) | Med | Cascade fallback absorbs rotation; document in AGENTS.md |
| Free-tier rate limits / no SLA | Med | Cascade continues; 503 only if ALL providers down |
| Refactor regression (OpenRouter body) | Low | Preserve `(api_key)` signature; full pytest suite |
| Doc drift (4 refs + `has_any_llm_key`) | Med | Update all in same change; spec delta tracks |

## Rollback Plan

Revert change (git): `_build_providers()` drops Zen entries, config fields removed, `has_any_llm_key()` restored — prior cascade order returns immediately. No schema/migration impact.

## Dependencies

- `ZEN_API_KEY` (user's opencode-go key) added to Railway `cancionespersonalizadas` env

## Success Criteria

- [ ] Full pytest suite green (strict TDD repo)
- [ ] Cascade order verified: zen-big-pickle → zen-nemotron → openai → gemini → openrouter
- [ ] `has_any_llm_key()` true with only `ZEN_API_KEY` set; startup no longer fails
- [ ] `result.provider` distinguishes `zen-big-pickle` vs `zen-nemotron`
- [ ] `.env.example` + `docs/api-reference.md` + error messages all list Zen
