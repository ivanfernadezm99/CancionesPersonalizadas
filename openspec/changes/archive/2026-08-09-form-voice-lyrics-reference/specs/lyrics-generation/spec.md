# Delta for Lyrics Generation

## ADDED Requirements

### RQ-LYR-07: Idea Seed in Lyrics Prompt

The lyrics generation MUST accept an optional `idea` input and MUST include it as a thematic seed in the LLM prompt alongside the accumulated `story` fragments. When `idea` is absent, generation MUST behave exactly as today.

#### Scenario: Idea included in prompt

- GIVEN lyrics generation with `idea="agradecer a mi madre"`
- WHEN the prompt is constructed
- THEN the prompt MUST include the `idea` text as thematic guidance
- AND the output SHOULD reflect the idea's theme

#### Scenario: No idea, current behavior

- GIVEN lyrics generation without `idea`
- WHEN the prompt is constructed
- THEN the prompt MUST NOT include idea guidance
- AND output MUST match existing generation
