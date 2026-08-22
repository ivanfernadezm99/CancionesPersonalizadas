"""Tests for reusing user-provided lyrics from story fragments.

The project worker must use the exact lyrics the user approved (autodraft
writes "Estrofa/Estribillo/Puente" sections as fragments) instead of letting
the LLM re-compose different lyrics. Free-form stories without a complete
lyric structure keep the LLM generation path.
"""

from __future__ import annotations

from app.projects import _classify_section_line, _story_to_lyrics_if_complete


class TestClassifySectionLine:
    def test_estrofa_with_number(self) -> None:
        assert _classify_section_line("Estrofa 1") == "[Verse 1]"

    def test_estrofa_numbered_short(self) -> None:
        assert _classify_section_line("Estrofa 2:") == "[Verse 2]"

    def test_estribillo(self) -> None:
        assert _classify_section_line("Estribillo") == "[Chorus]"

    def test_puente(self) -> None:
        assert _classify_section_line("Puente") == "[Bridge]"

    def test_english_bracketed_verse(self) -> None:
        assert _classify_section_line("[Verse 3]") == "[Verse 3]"

    def test_english_chorus_bracketed(self) -> None:
        assert _classify_section_line("[Chorus]") == "[Chorus]"

    def test_regular_line_returns_none(self) -> None:
        assert _classify_section_line("tus ojos brillan como el sol") is None

    def test_empty_line_returns_none(self) -> None:
        assert _classify_section_line("") is None


class TestStoryToLyricsIfComplete:
    def test_autodraft_fragments_convert_to_music_lyrics(self) -> None:
        story = (
            "Estrofa 1\nTus ojos brillan\njunto al mar\n"
            "Estribillo\nmi amor te va a esperar\n"
            "Puente\nsiempre vas a estar"
        )
        result = _story_to_lyrics_if_complete(story)
        assert result is not None
        assert "[Verse 1]" in result
        assert "Tus ojos brillan" in result
        assert "[Chorus]" in result
        assert "mi amor te va a esperar" in result
        assert "[Bridge]" in result
        assert "Puente" not in result

    def test_already_formatted_sections_pass_through(self) -> None:
        story = "[Verse 1]\nline\n[Chorus]\nchorus line"
        result = _story_to_lyrics_if_complete(story)
        assert result is not None
        assert result.startswith("[Verse 1]\nline\n[Chorus]\nchorus line")

    def test_free_form_story_returns_none(self) -> None:
        story = "Mi abuela amaba el tango y me lo contaba cada domingo"
        assert _story_to_lyrics_if_complete(story) is None

    def test_only_verses_without_chorus_returns_none(self) -> None:
        story = "Estrofa 1\nline one\nEstrofa 2\nline two"
        assert _story_to_lyrics_if_complete(story) is None

    def test_empty_story_returns_none(self) -> None:
        assert _story_to_lyrics_if_complete("") is None
        assert _story_to_lyrics_if_complete(None) is None

    def test_header_without_lines_is_skipped(self) -> None:
        story = "Estrofa 1\nEstribillo\ncoro\nPuente\npuente"
        result = _story_to_lyrics_if_complete(story)
        assert result is not None
        assert "[Verse 1]" not in result  # empty verse dropped
        assert result.startswith("[Chorus]")