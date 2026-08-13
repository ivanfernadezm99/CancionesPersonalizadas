## Exploration: zen-lyrics-provider

### Current State

The lyrics generation pipeline is a **cascade of per-provider instances** — each provider implements `BaseProvider.generate(prompt) -> LyricsResult | None` and `cascade_providers()` tries them in order until one returns a valid result, raising `LyricsGenerationError` only if all fail.

Three providers exist today in `app/lyrics/providers.py`:

| Provider | Transport | Response parsing |
|----------|-----------|------------------|
| `OpenAIProvider` | openai SDK (`gpt-4o`) | `response.choices[0].message.content` |
| `GeminiProvider` | httpx REST `generateContent` | `candidates[0].content.parts[0].text` |
| `OpenRouterProvider` | httpx POST `/chat/completions` (OpenAI-compatible) | `choices[0].message.content` |

`OpenRouterProvider` is the template for Zen: same OpenAI-compatible `chat.completions` shape (`{model, messages, temperature, max_tokens}`), same response read (`choices[0]["message"]["content"]`), same `_parse_lyrics_json()` post-processing that strips markdown fences and tolerates malformed JSON by returning `None` (which triggers cascade fallback). All three providers send the Spanish "Devuelve SOLO un objeto JSON válido" system prompt with `temperature=0.8, max_tokens=1500`.

Provider construction lives in `app/lyrics/__init__.py::_build_providers()`, gated on API keys in strict order: **OpenAI → Gemini → OpenRouter**. Both `app/main.py` (lifespan, line ~69) and `_build_providers()` raise/mention the same three-key list, and `Settings.has_any_llm_key()` gates startup. E2E reality: OpenAI returns `429 credit_balance_exhausted`, Gemini `503` — only OpenRouter actually works today, and the user wants free Zen models FIRST.

Settings (`app/config.py`) is pydantic-settings with `extra="ignore"` (new env vars won't crash). The three LLM keys live under a "# LLM API Keys" block. `.env.example` and `docs/api-reference.md` document the keys and cascade order — both will need updates. Note: `docs/api-reference.md` lists `MISTRAL_API_KEY` and `GOOGLE_API_KEY` which are NOT implemented in `config.py` (stale doc rows).

### Affected Areas

- `app/lyrics/providers.py` — add Zen provider (and, recommended, extract the shared OpenAI-compatible generate flow currently inside `OpenRouterProvider`)
- `app/lyrics/__init__.py` — `_build_providers()` ordering (Zen primary/secondary FIRST) + the "No LLM providers configured" error message
- `app/config.py` — add `ZEN_API_KEY`, `ZEN_PRIMARY_MODEL`, `ZEN_SECONDARY_MODEL`; update `has_any_llm_key()`
- `app/main.py` — lifespan RuntimeError message (line ~69) lists the three keys; must mention Zen
- `tests/test_lyrics_providers.py` — new Zen test class following the OpenRouter `patch.object(client, "post")` pattern; cascade ordering coverage
- `tests/test_integration.py` — `has_any_llm_key()` tests (~lines 845–914) will need a Zen-key case
- `.env.example` — document Zen vars + updated cascade order
- `docs/api-reference.md` — env var table (add Zen; optionally clean stale `MISTRAL_API_KEY`/`GOOGLE_API_KEY` rows)
- `openspec/specs/lyrics-generation/spec.md` — delta touching RQ-LYR-03 (provider table) and RQ-LYR-05 (key validation wording)

### Approaches

**A1 — New standalone `ZenProvider` (duplicate OpenRouter logic)**

Copy the ~40-line OpenAI-compatible generate flow into a new `ZenProvider` with Zen's base URL (`https://opencode.ai/zen/v1`), Bearer auth, and configurable model.

- Pros: zero risk to existing providers; most explicit; matches "one provider per class" precedent
- Cons: exact duplicate of OpenRouter's request/parse logic; third provider will triple it; drift risk
- Effort: Low

**A2 — Extract `OpenAICompatProvider` base; `ZenProvider` + `OpenRouterProvider` subclass it** ⭐

A base class parametrized by `(name, api_key, model, base_url, headers)` owns the shared `generate()` flow (post `/chat/completions` → read `choices[0]["message"]["content"]` → `_parse_lyrics_json`). `OpenRouterProvider(api_key)` keeps its public signature (existing tests and `_build_providers` unaffected), and `ZenProvider(api_key, model)` passes Zen's URL and header.

- Pros: DRY; both providers are literally the same protocol; future OpenAI-compatible providers become 5-line subclasses; existing OpenRouter tests stay green if the constructor signature is preserved
- Cons: touches working code (small refactor of `OpenRouterProvider` body); needs careful test preservation
- Effort: Low–Medium

**A3 — One `ZenProvider` that internally tries multiple models before returning None**

Single cascade entry; `generate()` loops over `["big-pickle", "nemotron-3-ultra-free"]`.

- Pros: single config knob; fewer cascade entries
- Cons: duplicates the cascade concept inside the provider; obscures which model produced the result (`result.provider` loses granularity); breaks the "one entry = one model" symmetry of the cascade
- Effort: Low

**Model selection decision (separate from provider class):** Big Pickle must be cascade-primary and Nemotron an additional fallback, sharing the same base URL/key. Recommend **two cascade entries with distinct names** (`zen-big-pickle` first, `zen-nemotron` second) — the cascade already implements exactly this fallback semantics, keeps `result.provider` transparent, and matches how OpenAI/Gemini/OpenRouter are modeled. (A3's single entry is the alternative, rejected for opacity.)

**Config decision:** `ZEN_API_KEY` (required gate), plus `ZEN_PRIMARY_MODEL="big-pickle"` and `ZEN_SECONDARY_MODEL="nemotron-3-ultra-free"` with defaults. Model names configurable, base URL hardcoded in the provider (consistent with OpenRouter/Gemini precedent). Adding a third Nemotron variant (`nemotron-3.5-lightning-free`) later is a one-line settings field + cascade entry — keep it out of scope now.

**Reasoning-model handling:** Big Pickle returns `content` + `reasoning_content`; Nemotron returns `content` + `reasoning_details`. Verified: the JSON lives in `content` for both. No special handling needed — keep reading `message["content"]` exactly as OpenRouter does. Optional defensive touch: if `content` is empty, log and return `None` (current behavior) so the cascade falls through; do NOT try to parse `reasoning_content` as the answer (it is thinking text, not the JSON).

### Recommendation

**A2** (extract `OpenAICompatProvider`, subclass for both OpenRouter and Zen) with **two Zen cascade entries** (`zen-big-pickle` → `zen-nemotron`) and configurable models. This is the cleanest fit for the codebase: it eliminates the exact duplication A1 would introduce, keeps the existing `OpenRouterProvider` API stable, and lets the proven cascade ordering do the fallback work. Cascade order becomes: **zen-big-pickle → zen-nemotron → openai → gemini → openrouter**.

Config surface (all with sensible defaults except the key):
- `ZEN_API_KEY` — Bearer key (the opencode-go key); must be added to `has_any_llm_key()`
- `ZEN_PRIMARY_MODEL="big-pickle"`
- `ZEN_SECONDARY_MODEL="nemotron-3-ultra-free"`

### Risks

- **Personal-key exposure**: the Zen key is a personal opencode-go key. Putting it in Railway env vars ships a personal credential; if it rotates or the account changes, Zen silently drops out of the cascade (fallback still works — this is a resilience feature, not a failure mode).
- **Free-tier reliability**: free models carry no SLA and may rate-limit; cascade mitigates but the failure path (all providers down → 503) still exists.
- **Refactor regression**: extracting the base class touches `OpenRouterProvider`'s body; mitigate by preserving the `(api_key)` constructor signature so the existing test class stays green, and running the full suite (strict TDD repo).
- **Doc drift**: four places reference the key list / cascade order (`main.py`, `__init__.py`, `.env.example`, `docs/api-reference.md`) plus `has_any_llm_key()`; missing any one leaves confusing 503/error messages. `.env.example` also documents the old order — must be updated.
- **Stale docs found (out of scope)**: `docs/api-reference.md` lists `MISTRAL_API_KEY`/`GOOGLE_API_KEY` which don't exist in `config.py`; optionally clean while editing the same table.

### Ready for Proposal

Yes — the approach is settled (A2, two cascade entries, configurable models). The orchestrator should tell the user: proposal will add `ZEN_API_KEY` (+ two model env vars) to config and Railway, extract `OpenAICompatProvider`, add `ZenProvider` with Big Pickle primary and Nemotron secondary before the existing providers, and update specs/docs/tests. One open question for the user: whether `docs/api-reference.md` stale rows (`MISTRAL_API_KEY`, `GOOGLE_API_KEY`) should be cleaned in the same change.
