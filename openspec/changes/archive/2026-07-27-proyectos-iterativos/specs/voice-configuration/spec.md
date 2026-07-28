# Delta for Voice Configuration

## ADDED Requirements

### RQ-VOI-05: Reference Song in Prompt Building

The `build_prompt` function MUST accept an optional `reference_song: str | None` parameter. When provided, the reference song style description MUST be appended to the generated prompt.

#### Scenario: Reference song appended

- GIVEN voice="male", genre="bachata", and reference_song="Bachata Rosa - Juan Luis Guerra"
- WHEN `build_prompt` constructs the Lyria 3 prompt
- THEN the prompt MUST include "voz masculina española"
- AND the prompt MUST end with "al estilo de Bachata Rosa - Juan Luis Guerra"

#### Scenario: No reference song

- GIVEN voice="female", genre="balada", and reference_song=None
- WHEN `build_prompt` is called
- THEN the prompt MUST NOT contain style references
- AND output MUST match existing prompt behavior

## MODIFIED Requirements

### RQ-VOI-02: Lyria 3 Prompt Mapping

The system MUST map the abstract voice selection to concrete OpenClaw prompt parameters. The mapping layer MUST produce a voice prompt string. When reference_song is present, it MUST be appended as a style modifier.
(Previously: no reference_song parameter existed in the mapping layer)

#### Scenario: Male voice with reference song (new)

- GIVEN voice="male", genre="bachata", reference_song="Bachata Rosa"
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include "voz masculina española"
- AND the prompt MUST include reference song style guidance

#### Scenario: Female voice without reference (unchanged)

- GIVEN voice="female", genre="balada", no reference_song
- WHEN the abstraction layer builds the prompt
- THEN the prompt MUST include "voz femenina española"
- AND the prompt MUST NOT include any style reference
