# Delta for Lyrics Generation

## ADDED Requirements

### RQ-LYR-06: Reference Song Influence

The system MUST accept an optional `reference_song` parameter in the lyrics generation context (from project settings). When provided, the LLM prompt MUST include style/melody guidance referencing that song.

#### Scenario: Reference song in lyrics prompt

- GIVEN a project with reference_song="Bachata Rosa - Juan Luis Guerra"
- WHEN the lyrics prompt is constructed
- THEN the prompt MUST include "al estilo de Bachata Rosa - Juan Luis Guerra"
- AND the output SHOULD reflect bachata romantic structure

#### Scenario: No reference song

- GIVEN lyrics generation without reference_song
- WHEN the prompt is constructed
- THEN the prompt MUST NOT include style references
- AND behavior MUST match existing lyrics generation

## MODIFIED Requirements

### RQ-LYR-04: Spanish Romantic Quality

The system SHOULD apply prompt engineering optimized for Spanish romantic poetry. When `reference_song` is provided, the system SHOULD instruct the model to match that song's style, rhythm, and thematic elements.
(Previously: no reference song parameter existed)

#### Scenario: Genre-appropriate vocabulary (unchanged)

- GIVEN genre="reggaetón"
- WHEN lyrics are generated
- THEN the output SHOULD use informal, rhythmic Spanish with shorter lines

#### Scenario: Reference song overrides genre defaults (new)

- GIVEN reference_song="El Amor - José José" and genre="balada romántica"
- WHEN the prompt includes the reference
- THEN lyrics SHOULD match the romantic ballad style of the reference
- AND the reference song name MUST appear in the prompt
