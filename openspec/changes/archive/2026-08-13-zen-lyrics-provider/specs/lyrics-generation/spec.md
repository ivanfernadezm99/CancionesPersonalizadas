# Delta for Lyrics Generation

## MODIFIED Requirements

### Requirement: RQ-LYR-03: Multi-Provider Selection

The system SHALL cascade through LLM providers in fixed order until one returns valid lyrics, starting with Zen (free, OpenAI-compatible) before the existing providers:

| Order | Provider | Model | Notes |
|-------|----------|-------|-------|
| 1 | Zen (Big Pickle) | `big-pickle` | Entry `zen-big-pickle`; requires `ZEN_API_KEY` |
| 2 | Zen (Nemotron) | `nemotron-3-ultra-free` | Entry `zen-nemotron`; requires `ZEN_API_KEY` |
| 3 | OpenAI | GPT-4o | Requires `OPENAI_API_KEY` |
| 4 | Google | Gemini | Requires `GEMINI_API_KEY` |
| 5 | OpenRouter | GPT-4o / Gemini | Fallback; requires `OPENROUTER_API_KEY` |

Zen providers SHALL call the OpenAI-compatible endpoint `https://opencode.ai/zen/v1/chat/completions` with Bearer auth, parametrized by `ZEN_API_KEY`, `ZEN_PRIMARY_MODEL` (default `big-pickle`), and `ZEN_SECONDARY_MODEL` (default `nemotron-3-ultra-free`). If `ZEN_API_KEY` is unset, both Zen entries MUST be skipped and the cascade MUST fall through to OpenAI/Gemini/OpenRouter. Zen reasoning models return the JSON answer in `message.content`; the system MUST read `content` and MUST ignore `reasoning_content`/`reasoning_details`. Empty `content` MUST yield `None` so the cascade continues.
(Previously: cascade order was OpenAI → Gemini → OpenRouter with no Zen entries.)

#### Scenario: First provider succeeds

- GIVEN Zen Big Pickle returns valid lyrics in < 10s
- WHEN the multi-provider pipeline runs
- THEN the result from `zen-big-pickle` is used
- AND no fallback providers are called

#### Scenario: Zen primary fails, Zen secondary succeeds

- GIVEN Zen Big Pickle returns an error (timeout or 5xx)
- WHEN the multi-provider pipeline runs
- THEN it MUST fall back to `zen-nemotron`
- AND the final result MUST come from Zen Nemotron

#### Scenario: Reasoning model JSON in content

- GIVEN a Zen reasoning model returns JSON in `content` plus non-empty `reasoning_content`/`reasoning_details`
- WHEN the provider parses the response
- THEN the JSON MUST be read from `content`
- AND `reasoning_content`/`reasoning_details` MUST be ignored

#### Scenario: Empty content falls through

- GIVEN a Zen provider returns empty `content`
- WHEN the cascade runs
- THEN that provider MUST return `None`
- AND the cascade MUST continue with the next provider

#### Scenario: Zen key not configured

- GIVEN `ZEN_API_KEY` is not set
- WHEN `_build_providers()` runs
- THEN no Zen entries are added to the cascade
- AND the cascade MUST start with OpenAI

#### Scenario: All providers fail

- GIVEN all providers (Zen, OpenAI, Gemini, OpenRouter) return errors
- WHEN the multi-provider pipeline runs
- THEN the system MUST return a 503 error
- AND the error message MUST indicate "all LLM providers unavailable"

### Requirement: RQ-LYR-05: Provider Key Validation

The system MUST validate at startup, via `has_any_llm_key()`, that at least one LLM provider API key is configured. The key set MUST include `ZEN_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `OPENROUTER_API_KEY`. If none are configured, the /api/generate endpoint MUST return 503 with a clear setup error. All user-facing key-list messages — the startup log and the "No LLM providers configured" error — MUST list Zen.
(Previously: key set and messages covered only OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY.)

#### Scenario: No API keys configured

- GIVEN no LLM provider keys are set (ZEN_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY all empty)
- WHEN the application starts
- THEN the system MUST log a fatal error
- AND the /api/generate endpoint MUST return 503

#### Scenario: Partial key configuration

- GIVEN only OPENAI_API_KEY is set, others are empty
- WHEN the system starts
- THEN it MUST log a warning about missing Zen, Gemini, and OpenRouter keys
- BUT it MUST still accept /api/generate requests
- AND only attempt OpenAI for lyrics generation

#### Scenario: Zen-only configuration

- GIVEN only ZEN_API_KEY is set, others are empty
- WHEN the system starts
- THEN `has_any_llm_key()` MUST return true
- AND the system MUST start without fatal errors
- AND only attempt Zen providers for lyrics generation
