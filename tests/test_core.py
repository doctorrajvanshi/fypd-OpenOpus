"""Unit tests for the dependency-free core helpers.

These import only fypd_core, so they run in CI in seconds without MoviePy,
Whisper, MediaPipe or a live server.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fypd_core import (  # noqa: E402
    STYLE_TEMPLATES,
    clean_token,
    elastic_bounce_transform,
    extract_video_id,
    group_words_into_phrases,
    sanitize_filename,
    timestamp_to_seconds,
)


class TestSanitizeFilename:
    def test_strips_windows_illegal_characters(self):
        assert sanitize_filename("Hello/World:Test") == "Hello_World_Test"
        assert sanitize_filename('bad"name<here>') == "bad_name_here_"

    def test_leaves_ordinary_titles_alone(self):
        assert sanitize_filename("normal_title") == "normal_title"

    def test_handles_every_illegal_character(self):
        assert sanitize_filename(r'a\b/c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


class TestTimestampToSeconds:
    @pytest.mark.parametrize("value,expected", [
        ("00:01:30", 90),
        ("01:00:00", 3600),
        ("00:00", 0),
        ("01:30", 90),
    ])
    def test_standard_formats(self, value, expected):
        assert timestamp_to_seconds(value) == expected

    def test_fractional_seconds(self):
        """Models routinely emit these; int() used to raise and kill the job."""
        assert timestamp_to_seconds("00:01:23.5") == pytest.approx(83.5)

    def test_bare_seconds(self):
        assert timestamp_to_seconds("42") == 42
        assert timestamp_to_seconds(42) == 42
        assert timestamp_to_seconds(42.5) == pytest.approx(42.5)

    def test_unparseable_raises_rather_than_returning_zero(self):
        with pytest.raises(ValueError):
            timestamp_to_seconds("not a timestamp")


class TestExtractVideoId:
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
    ])
    def test_extracts_the_eleven_character_id(self, url):
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_distinct_unmatched_urls_do_not_collide(self):
        """They previously all mapped to 'unknown_video' and shared one cache file."""
        a = extract_video_id("https://example.com/a.mp4")
        b = extract_video_id("https://example.com/b.mp4")
        assert a != b

    def test_unmatched_url_is_stable(self):
        url = "https://example.com/a.mp4"
        assert extract_video_id(url) == extract_video_id(url)


class TestCleanToken:
    def test_uppercases_and_strips_punctuation(self):
        assert clean_token("hello!") == "HELLO"
        assert clean_token(" world ") == "WORLD"

    @pytest.mark.parametrize("filler", ["UM", "[NONE]", "uh", ""])
    def test_filters_filler_words(self, filler):
        assert clean_token(filler) == ""


class TestGroupWordsIntoPhrases:
    def _words(self, spec):
        return [{"word": w, "start": s, "end": e} for w, s, e in spec]

    def test_splits_on_max_words_per_phrase(self):
        style = STYLE_TEMPLATES["hormozi"]  # MAX_WORDS_PER_PHRASE = 2
        words = self._words([
            ("one", 0.0, 0.2), ("two", 0.2, 0.4),
            ("three", 0.4, 0.6), ("four", 0.6, 0.8),
        ])
        phrases = group_words_into_phrases(words, style)
        assert [len(p) for p in phrases] == [2, 2]

    def test_splits_on_long_silence(self):
        style = STYLE_TEMPLATES["hormozi"]  # MAX_GAP_SECONDS = 0.6
        words = self._words([("one", 0.0, 0.2), ("two", 5.0, 5.2)])
        phrases = group_words_into_phrases(words, style)
        assert len(phrases) == 2

    def test_drops_filler_tokens(self):
        style = STYLE_TEMPLATES["minimalist"]
        words = self._words([("um", 0.0, 0.1), ("real", 0.1, 0.3)])
        phrases = group_words_into_phrases(words, style)
        assert [w["text"] for p in phrases for w in p] == ["REAL"]

    def test_empty_input_yields_no_phrases(self):
        assert group_words_into_phrases([], STYLE_TEMPLATES["neon"]) == []


class TestElasticBounceTransform:
    def test_rises_then_settles_at_one(self):
        assert elastic_bounce_transform(0.0) < elastic_bounce_transform(0.12)
        assert elastic_bounce_transform(1.0) == pytest.approx(1.0)

    def test_never_collapses_to_zero(self):
        for t in (0.0, 0.05, 0.12, 0.2, 0.22, 0.5, 2.0):
            assert elastic_bounce_transform(t) > 0.5


class TestStyleTemplates:
    @pytest.mark.parametrize("name", ["hormozi", "minimalist", "neon"])
    def test_every_style_exposes_the_keys_the_renderer_reads(self, name):
        required = {
            "FONT", "FONT_SIZE", "TEXT_COLOR", "SHADOW_COLOR",
            "MAX_WORDS_PER_PHRASE", "MAX_GAP_SECONDS", "ANIMATION", "SHADOW_OFFSET",
        }
        assert required <= set(STYLE_TEMPLATES[name])
