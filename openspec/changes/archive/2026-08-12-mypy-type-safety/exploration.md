# Exploration — mypy-type-safety

**Project**: cancionespersonalizadas · **Change**: `mypy-type-safety`
**Environment verified**: mypy **2.1.0**, pydantic **2.13.1**, Python 3.10
**Baseline**: `python3 -m mypy app/ --ignore-missing-imports` → **15 errors** in 3 files (confirmed; 34 files checked).

---

## Mypy Configuration (current)

From `pyproject.toml` → `[tool.mypy]`:

```toml
python_version = "3.10"
strict = true
ignore_missing_imports = true
disallow_untyped_defs = false
disallow_any_unimported = false
warn_unused_ignores = true
```

Key observations:

- **No `plugins` key** → the pydantic mypy plugin is NOT loaded. Pydantic models are typed by mypy's **built-in `dataclass_transform` support** (see root cause A below).
- `strict = true` is what enables `disallow_any_generics` (→ `type-arg` errors) and `disallow_untyped_calls` (→ `no-untyped-call` error). Note the project explicitly relaxes `disallow_untyped_defs`, so new untyped defs are allowed, but *calling* untyped defs from typed contexts is not.
- `warn_unused_ignores = true` → any `# type: ignore` added must carry the exact error code or it will itself error.
- `mypy --show-config` is **not available** in mypy 2.x (option was removed) — cannot be used to introspect effective config.

---

## The 15 errors — grouped by root cause

### Group A (10 errors) — Pydantic field defaults not recognized by mypy (`call-arg`)

**Affected errors**:
| File:line | Error |
|---|---|
| `app/projects/__init__.py:85` | Missing named arg `reference_song` / `reference_description` for `GenerateRequest` |
| `app/projects/__init__.py:153` | Missing named arg `reference_song` / `reference_description` for `GenerateRequest` |
| `app/projects/router.py:366` | Missing named arg `genre`, `mood`, `voice`, `reference_song`, `idea`, `chaining_enabled` for `SongProjectUpdate` |

**Root cause** (verified against installed sources):

1. pydantic 2.13.1 decorates `ModelMetaclass` with
   `@dataclass_transform(kw_only_default=True, field_specifiers=(PydanticModelField, ...))`
   (`pydantic/_internal/_model_construction.py:82`). Mypy 2.1 processes every `BaseModel` subclass through its built-in dataclass_transform machinery and **synthesizes a typed `__init__`** with required/optional fields — no pydantic plugin involved.
2. Field-default detection (`mypy/plugins/dataclasses.py` `analyze()` / `_collect_field_args()`): for an RHS that is a `Field(...)` call, a field is treated as having a default **only if a keyword argument named `default`, `default_factory`, or `factory` is present** (`has_default = "default" in field_args or ...`). `_collect_field_args` drops positional arguments entirely — its own comment: *"field() only takes keyword arguments."*
3. Therefore `genre: str | None = Field(None, min_length=1, max_length=50)` → mypy sees **no default** → the field is **required** in the synthesized `__init__`. The same applies to `Field(None, ...)` (positional) and `Field("balada", ...)` (positional default) — both look default-less. `Field(default=None, ...)` is recognized. A plain assignment (`fragment: StoryFragmentAdd | None = None`) is recognized.
4. The call sites (`app/projects/__init__.py:85,153` build `GenerateRequest` without `reference_song`/`reference_description`; `app/projects/router.py:366` builds `SongProjectUpdate(reference_description=...)` only) then trip the false-required fields.

**Why this is a false positive (no real requirement)**: all these fields are declared `X | None = Field(None, ...)` — optional at runtime by design. For `SongProjectUpdate`, `store.update_project` (`app/projects/store.py:220-257`) implements **partial-update semantics**: it applies only fields whose value is `not None`. There is no legitimate scenario where `genre`/`mood`/`voice`/etc. are required for a PATCH. Same for `GenerateRequest` — `reference_song`/`reference_description` are optional style hints (validated by `_validate_reference_song`, which passes `None`/empty through).

**Fix (type-only, zero runtime change)** — in `app/models.py`, convert the positional default to the keyword form (Pydantic's `Field(default=...)` is byte-for-byte the same semantic as passing the default as first positional; runtime is identical):

- `GenerateRequest`: `story` (line 60), `reference_song` (64-68), `reference_description` (69-73), `idea` (74-78) → `Field(default=None, ...)`
- `SongProjectUpdate`: `genre`, `mood`, `voice`, `reference_song`, `reference_description`, `idea`, `chaining_enabled` (lines 208-218) → `Field(default=None, ...)`

**Latent instances of the same root cause** (not currently erroring because no call sites omit them, but would break any future caller that relies on the default): `app/models.py:107` `LyricsResult.bridge`, `:139` `JobStatusResponse.error`, `:298` `PaymentConfirmRequest.metadata`, plus `GenerateRequest.story`/`idea` (currently always passed at the two call sites). Recommendation: convert all of them in the same pass for consistency.

**Empirical validation**: a minimal reproduction with the exact field patterns reproduced the identical errors (including `Field("balada", ...)` → required, `Field(default=...)` → optional, plain `= None` → optional). Applying `Field(default=None, ...)` to the repro: **0 errors**.

### Group B (3 errors) — Missing generic type arguments (`type-arg`)

**Affected errors**:
| File:line | Error |
|---|---|
| `app/projects/router.py:39` | `project: dict` |
| `app/projects/router.py:83` | `-> dict` |
| `app/music/clipchain.py:321` | `segments: list = []` |

**Root cause**: `strict = true` enables `disallow_any_generics` → bare `dict`/`list` without type arguments are errors.

**Fix (pure annotation changes, no runtime impact)**:
- `router.py:39` → `project: dict[str, Any]`; `router.py:83` → `-> dict[str, Any]`. Requires adding `from typing import Any` to `router.py` (currently no `typing` import).
- `clipchain.py:321` → `segments: list[Any] = []` (pydub `AudioSegment` is imported lazily by design — graceful fallback when pydub is missing — so `AudioSegment` cannot be named at module level; `Any` is correct here). Add `Any` to the existing `from typing import NamedTuple`.

### Group C (1 error) — Call to untyped function (`no-untyped-call`)

**Affected error**: `app/music/clipchain.py:312` — `_get_audio_segment()`.

**Root cause**: `strict = true` enables `disallow_untyped_calls`. `_get_audio_segment` (`clipchain.py:78-85`) has **no return annotation** (lazy pydub import returning `AudioSegment` or `None`), so calling it in the typed `stitch_clips` body errors. The sibling helper in `app/music/durext.py:23` is already annotated `-> Any` — the established project pattern.

**Fix (annotation-only)**: add `-> Any` to `clipchain.py:78` (`def _get_audio_segment() -> Any:`), importing `Any` alongside `NamedTuple`. pydub is untyped (`ignore_missing_imports`), so `Any` is the pragmatic and consistent type.

### Group D (1 error) — Union attribute access (`union-attr`)

**Affected error**: `app/projects/router.py:360` — `Item "AudioAnalysisResult" of "AudioAnalysisResult | AudioAnalysisError" has no attribute "detail"`.

**Root cause**: `analyze_audio` returns the union `AudioAnalysisResult | AudioAnalysisError` (`app/audio_analysis.py:41`). The guard `if hasattr(result, "error"):` (router.py:357) does **not narrow** the union for mypy — `hasattr` is not a type-narrowing construct — so `result.detail` at line 360 is accessed on the full union and `AudioAnalysisResult` has no `detail` attribute. (`AudioAnalysisError` has `error` + `detail`; `AudioAnalysisResult` has `language`, `transcript`, `duration_seconds`, `energy`, `estimated_tempo`, `style_description`.)

**Fix (behavior-identical, small runtime-code change)**: replace `hasattr(result, "error")` with `isinstance(result, AudioAnalysisError)`. Semantics are provably identical for these two dataclasses: `AudioAnalysisResult` never has an `error` attribute; `AudioAnalysisError` always does. After the guard, mypy narrows `result` to `AudioAnalysisResult`, which also cleans up `result.style_description` (line 366), `result.language/transcript/duration_seconds/energy/estimated_tempo` (lines 377-384).

Alternative (not recommended): `detail={"error": "analysis_failed", "detail": result.detail},  # type: ignore[union-attr]` — annotation-only, but `warn_unused_ignores = true` demands the exact code and it masks the real intent; `isinstance` is strictly better.

**Side note**: `analyze_audio` currently never *returns* `AudioAnalysisError` in practice (all exceptions are swallowed and a default-filled `AudioAnalysisResult` is returned, `app/audio_analysis.py:56-80`) — the union is aspirational. The type contract still says union, so the handler must branch on it; `isinstance` makes that branch explicit and type-safe.

---

## Affected Areas

- `app/models.py` — `GenerateRequest`, `SongProjectUpdate` (10 of 15 errors; `Field(None, ...)` → `Field(default=None, ...)`)
- `app/projects/__init__.py:85,153` — call sites of `GenerateRequest` (errors disappear once the model is fixed; **no change needed here**)
- `app/projects/router.py:39,83,360,366` — `dict[str, Any]` annotations, `typing.Any` import, `isinstance` narrowing
- `app/music/clipchain.py:78,312,321` — `-> Any` on `_get_audio_segment`, `list[Any]` for segments
- `app/audio_analysis.py` — read-only; types are fine, no change needed
- No changes to: `app/projects/store.py`, `app/jobs/*`, tests (behavior untouched)

## Approaches

1. **Fix annotations in place (recommended)** — convert `Field(None, …)` → `Field(default=None, …)` in models; add type args; annotate `_get_audio_segment`; use `isinstance` in router.
   - Pros: minimal diff, zero runtime behavior change, addresses the 15 errors plus latent instances, no new config
   - Cons: touches 3 files; the `hasattr`→`isinstance` swap is technically runtime code (provably behavior-identical)
   - Effort: Low

2. **Enable the pydantic mypy plugin** (`plugins = ["pydantic.mypy"]` in pyproject) — the "canonical" pydantic answer.
   - Pros: would (in theory) model fields correctly
   - Cons: **NOT viable here** — pydantic 2.13.1's plugin is incompatible with mypy 2.1.0 (`ImportError: module 'mypy.expandtype' has no attribute 'ExpandTypeVisitor'` observed); enabling it breaks every mypy run. Would also be a config change with environment coupling.
   - Effort: N/A (blocked)

3. **Bulk `# type: ignore[...]`** at the 15 error sites.
   - Pros: smallest diff, purely additive
   - Cons: masks the systemic root cause; `warn_unused_ignores` forces precise codes; leaves latent traps in `LyricsResult`, `JobStatusResponse`, `PaymentConfirmRequest`; doesn't fix the false "required" contract that already breaks correct callers (e.g. `SongProjectUpdate(reference_description=...)` is a *correct* call that today fails type-checking)
   - Effort: Low

## Recommendation

**Approach 1** — annotation-level fixes in `app/models.py`, `app/projects/router.py`, `app/music/clipchain.py`. All fixes are type-only or provably behavior-identical; no runtime behavior changes. Optionally extend the `Field(default=None, ...)` conversion to the latent instances (`bridge`, `error`, `metadata`, `story`, `idea`) so the fix is complete and future callers aren't surprised. Do NOT enable the pydantic plugin (incompatible with mypy 2.1.0).

## Risks

- **None for behavior**: `Field(None, …)` and `Field(default=None, …)` are semantically identical in Pydantic v2; `dict[str, Any]` / `list[Any]` / `-> Any` are pure annotations; `isinstance(AudioAnalysisError)` is equivalent to `hasattr(result, "error")` for these two dataclasses.
- **Not a real required-field change**: `SongProjectUpdate` fields are genuinely optional (partial PATCH, verified in `store.update_project`); `GenerateRequest.reference_song/reference_description` are optional style hints. Mypy's current "required" view is a false positive that already rejects valid calls.
- **`warn_unused_ignores = true`**: any `type: ignore` added must carry the exact error code; prefer real fixes.
- **Plugin temptation**: adding `plugins = ["pydantic.mypy"]` breaks mypy with this mypy/pydantic pair — avoid.
- **Verification gate**: after apply, `python3 -m mypy app/ --ignore-missing-imports` must return 0 errors, and the full pytest suite must stay green (behavior untouched).

## Ready for Proposal

**Yes** — root causes are fully diagnosed and empirically validated (reproduction + fix repro → 0 errors). The orchestrator should tell the user: all 15 errors are type-checking false positives/annotation gaps with zero-behavior fixes; no architectural decisions required; scope is 3 files, ~10 annotation edits plus one `hasattr`→`isinstance` swap.
