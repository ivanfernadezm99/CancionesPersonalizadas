# Proposal: Form Voice Variety, Lyrics Auto-Generation, Reference Song

## Intent

Make the personalized-song form offer real voice variety, let users seed lyrics from an "idea" with one-click auto-generation, and ensure the existing reference-song feature actually reaches the deployed staging.

## User Goals

- Select from varied Spanish voices: español hombre latino, español hombre españa, mujer española, mujer latina, etc.
- Type "la idea de lo que queres hacer" and auto-generate editable lyrics for the recipient.
- See and use the reference-song field on staging (name + MP3 upload).

## Non-Goals

- NOT rewriting the whole form or its UX flow.
- NOT touching auth/roles/payments (POSBackend rewrite in flight stays out).
- NOT adding voice cloning (v1+ future).
- NOT changing preview/final generation pipeline semantics.

## Current State Gap

1. **Voice**: backend registry has only `male`/`female`; frontend hard-codes `male|female|duo|children`. `duo`/`children` pass free-text validation but crash at job time (`build_prompt` ValueError). No `/voices` endpoint → two drifting lists.
2. **Lyrics**: no idea/comment field, no auto-generate; fragments are the only input.
3. **Reference song**: implemented locally end-to-end (backend + frontend) but UNCOMMITTED / not deployed — user can't see it on staging.

## Approach

- **Voice** (recommended A1): extend `VOICE_REGISTRY` to ~7 entries — `male`, `female`, `es-latino-male`, `es-espana-male`, `es-espana-female`, `es-latina-female`, `es-espana-child` (drop `duo`/`children`). Add `GET /api/voices` → `[{id,label}]`. Frontend fetches and renders data-driven. Backend validates `voice` against registry at API boundary, fail fast with 422 (not job crash). Alternatives: keep hard-coded sync — rejected (drift already proven).
- **Lyrics** (recommended B1): add optional `idea` field to project create/update/patch + persist in `projects`. Add `POST /api/projects/{id}/lyrics-draft` reusing `lyrics_generate` → returns editable verses/chorus; frontend textarea + "Autogenerar letra" button fills fragments editor (via existing `PUT /fragments`). Alternative: auto-gen only at preview (no editable draft) — rejected.
- **Reference song**: NO new backend code. Verify end-to-end, commit/push both repos, confirm on staging. If gap is real, deliver the field only.

## Capabilities

### New Capabilities
- `lyrics-autodraft`: idea-driven one-click editable lyric draft endpoint + frontend wiring.

### Modified Capabilities
- `voice-configuration`: add varied voice entries + `GET /api/voices` + registry validation (fail-fast 422).
- `song-projects`: persist `idea` field through create/update/patch; reference-song delivery verified/deployed.
- `lyrics-generation`: `idea` seed feeds lyrics prompt; draft output structure reuses existing schema.

## Slices & Delivery (review_budget=800)

| Slice | Scope | Est. Δ lines |
|-------|-------|-------------|
| 1 | Voice variety + `/voices` endpoint + reference-song commit/verify/deploy | ~180 (back ~90, front ~90) |
| 2 | Lyrics `idea` field + auto-generate draft endpoint + UI | ~260 (back ~120, front ~140) |

Recommend: **chained PRs** (slice 1 → slice 2) in each repo; each slice well under 800-line budget; frontend repo carries extra in-flight reference-song lines.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Uncommitted work both repos (auth, reference-song) | High | Plan deltas vs working tree; commit slice 1 as baseline |
| Voice drift backend vs frontend | Med | Single `/voices` source; remove hard-coded list |
| Lyrics LLM cost/latency on draft | Med | Reuse provider cascade + 503 handling; button shows loading |

## Rollback Plan

Revert the slice 1 PR (voice+voices); registry edit alone restores old IDs — old projects stay valid since `male`/`female` retained. Revert slice 2 PR; `idea` is nullable, `lyrics-draft` endpoint is additive — no data migration required.

## Dependencies

- Commit/push current in-flight work in **both** repos before applying slice 1.
- LLM provider keys (existing) for lyrics draft.

## Success Criteria

- [ ] `GET /api/voices` returns ~7 options; frontend renders them data-driven.
- [ ] Selecting any valid voice no longer crashes jobs; invalid voice returns 422.
- [ ] Reference-song field visible & working on staging.
- [ ] User can type an idea, click auto-generate, and see editable lyrics filling the fragments editor.
