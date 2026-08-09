"""Dependency-free helpers shared by the server and the rendering engine.

Everything here is pure Python with no third-party imports, so it can be
imported (and unit tested) without pulling in MoviePy, Whisper or MediaPipe.
`sanitize_filename` in particular used to be defined twice — once in
app_server.py and once in viral_clipper.py — with the filenames they produced
required to stay byte-identical.
"""

import hashlib
import re

# Characters that are illegal in Windows filenames
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')

# Whisper checkpoint used for clip captions and full-video fallback
# transcription. The Tauri installer warms up this exact name.
WHISPER_MODEL = "base"

STYLE_TEMPLATES = {
    "hormozi": {
        "FONT": "Impact",
        "FONT_SIZE": 54,
        "TEXT_COLOR": "#FFFF00",
        "SHADOW_COLOR": "#000000",
        "MAX_WORDS_PER_PHRASE": 2,
        "MAX_GAP_SECONDS": 0.6,
        "ANIMATION": "bounce",
        "SHADOW_OFFSET": 4
    },
    "minimalist": {
        "FONT": "Arial",
        "FONT_SIZE": 48,
        "TEXT_COLOR": "#FFFFFF",
        "SHADOW_COLOR": "transparent",
        "MAX_WORDS_PER_PHRASE": 3,
        "MAX_GAP_SECONDS": 0.8,
        "ANIMATION": "fade",
        "SHADOW_OFFSET": 0
    },
    "neon": {
        "FONT": "Impact",
        "FONT_SIZE": 58,
        "TEXT_COLOR": "#00FFFF",  # Neon Cyan
        "SHADOW_COLOR": "#FF00FF",  # Neon Magenta Glow
        "MAX_WORDS_PER_PHRASE": 2,
        "MAX_GAP_SECONDS": 0.5,
        "ANIMATION": "bounce",
        "SHADOW_OFFSET": 2
    }
}


def sanitize_filename(name: str) -> str:
    """Strip characters that are illegal in Windows filenames."""
    return _ILLEGAL_FILENAME_CHARS.sub('_', str(name)).strip()


def timestamp_to_seconds(ts):
    """Parse HH:MM:SS, MM:SS or a bare seconds value into float seconds.

    Models routinely emit fractional seconds ("00:01:23.5") and occasionally a
    plain number; int() on those raised and killed the entire job.
    """
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        parts = [float(p) for p in str(ts).strip().split(':')]
    except ValueError:
        raise ValueError(f"Unparseable timestamp: {ts!r}. Expected HH:MM:SS.")
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    raise ValueError(f"Unparseable timestamp: {ts!r}. Expected HH:MM:SS.")


def extract_video_id(url: str) -> str:
    """Derive a stable cache key for a video URL.

    Falls back to a hash of the URL rather than a shared "unknown_video"
    constant, which used to make two different non-YouTube sources collide on
    one cache file and silently clip the wrong footage.
    """
    match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})(?:[?&/]|$)', url)
    if match:
        return match.group(1)
    return "url_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def clean_token(text: str) -> str:
    cleaned = text.strip().upper()
    cleaned = re.sub(r'[^\w\s]', '', cleaned)  # Strip out punctuation artifacts
    if cleaned in ["NONE", "", "[NONE]", "(NONE)", "UM", "UH", "AH", "ERR"]:
        return ""
    return cleaned


def group_words_into_phrases(words_list, style_config):
    """Chunk word-level timestamps into caption-sized phrases."""
    phrases = []
    current_phrase = []
    for word_data in words_list:
        word_text = clean_token(word_data["word"])
        if not word_text:
            continue
        w_start = word_data["start"]
        w_end = word_data["end"]

        if not current_phrase:
            current_phrase = [{"text": word_text, "start": w_start, "end": w_end}]
        else:
            time_gap = w_start - current_phrase[-1]["end"]
            if (len(current_phrase) >= style_config["MAX_WORDS_PER_PHRASE"] or
                    time_gap > style_config["MAX_GAP_SECONDS"]):
                phrases.append(current_phrase)
                current_phrase = [{"text": word_text, "start": w_start, "end": w_end}]
            else:
                current_phrase.append({"text": word_text, "start": w_start, "end": w_end})
    if current_phrase:
        phrases.append(current_phrase)
    return phrases


def elastic_bounce_transform(t):
    """Calculates an organic elastic pop scaling effect over the first 150ms"""
    if t < 0.12:
        return 0.85 + (0.4 * (t / 0.12))
    elif t < 0.22:
        return 1.25 - (0.25 * ((t - 0.12) / 0.10))
    return 1.0
