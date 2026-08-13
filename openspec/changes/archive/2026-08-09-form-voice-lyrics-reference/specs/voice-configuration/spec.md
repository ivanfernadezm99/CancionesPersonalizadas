# Delta for Voice Configuration

## ADDED Requirements

### RQ-VOICE-01: Available Voices Endpoint

The system MUST expose `GET /api/voices` returning the full voice registry as an array of `{id, label, gender}` objects. This endpoint MUST be the single source of truth for the frontend voice selector; the frontend MUST NOT hard-code its own voice options.

#### Scenario: Return available voices

- GIVEN a healthy voice registry
- WHEN GET /api/voices is called
- THEN response MUST be 200 with an array of ~7 entries
- AND each entry MUST include `id`, `label`, and `gender`

#### Scenario: Reflects registry exactly

- GIVEN the registry defines `es-latino-male`
- WHEN GET /api/voices is called
- THEN the response MUST include `es-latino-male`
- AND the list MUST exactly match the registry (no drift)

### RQ-VOICE-02: Fail-Fast Voice Validation

The system MUST validate the `voice` field against the voice registry at the API boundary (request validation) and MUST return a 422 error for unknown IDs. Voice validation MUST NOT be deferred to job execution, and MUST NOT let an unknown voice crash a job.

#### Scenario: Unknown voice rejected at request time

- GIVEN a request with `voice: "celebrity_x"`
- WHEN the project create/update or generate request is validated
- THEN response MUST be 422
- AND no job MUST be created

#### Scenario: Legacy duo/children rejected

- GIVEN a request with `voice: "duo"` or `voice: "children"`
- WHEN the request is validated
- THEN response MUST be 422
- AND the error MUST list valid voice IDs

#### Scenario: New valid voice accepted

- GIVEN a request with `voice: "es-latino-male"`
- WHEN the request is validated
- THEN response MUST be accepted
- AND the job MUST run without voice-related failure

## MODIFIED Requirements

### RQ-VOI-01: Voice Selection Input

The system MUST accept a `voice` parameter in the generation request with the following valid options:

| Value | Label | Gender |
|-------|-------|--------|
| `male` | Voz masculina | male |
| `female` | Voz femenina | female |
| `es-latino-male` | Español hombre latino | male |
| `es-espana-male` | Español hombre España | male |
| `es-espana-female` | Mujer española | female |
| `es-latina-female` | Mujer latina | female |
| `es-espana-child` | Voz infantil española | child |

If `voice` is omitted, the system SHOULD default to `female`.
(Previously: only `male` and `female` were valid; `duo`/`children` were not in the registry.)

#### Scenario: Explicit male voice

- GIVEN a generate request with `voice: "male"`
- WHEN the request is validated
- THEN the system MUST accept the value
- AND pass it to the voice abstraction layer

#### Scenario: Explicit new regional voice

- GIVEN a generate request with `voice: "es-espana-female"`
- WHEN the request is validated
- THEN the system MUST accept the value
- AND pass it to the voice abstraction layer

#### Scenario: Default voice when omitted

- GIVEN a generate request without a `voice` field
- WHEN the request is validated
- THEN the system MUST use `female` as the default

#### Scenario: Unsupported voice value

- GIVEN a generate request with `voice: "duo"`, `children`, or any value not in the registry
- WHEN the request is validated
- THEN the system MUST return a 422 validation error
- AND the error MUST list the supported voice IDs

### RQ-VOI-02: Lyria 3 Prompt Mapping

The system MUST map each abstract voice selection to a distinct Spanish voice descriptor string (`prompt_es`) injected into the music generation `prompt` field. When `reference_song` is present, it MUST be appended as a style modifier.
(Previously: only male/female descriptors existed; new regional voices have distinct descriptors.)

#### Scenario: Male voice prompt construction

- GIVEN a voice selection of `male` and genre="bachata"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Spanish male voice descriptor (e.g. "voz masculina española")
- AND the prompt SHOULD include "cantante masculino"

#### Scenario: Latino male prompt construction

- GIVEN a voice selection of `es-latino-male` and genre="reggaetón"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Latino male descriptor (e.g. "voz masculina latina")
- AND the prompt SHOULD include "hombre latinoamericano"

#### Scenario: Female voice prompt construction

- GIVEN a voice selection of `female` and genre="balada"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a Spanish female voice descriptor (e.g. "voz femenina española")
- AND the prompt SHOULD include "cantante femenina"

#### Scenario: Child voice prompt construction

- GIVEN a voice selection of `es-espana-child`
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include a child voice descriptor (e.g. "voz infantil")
