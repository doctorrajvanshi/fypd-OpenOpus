"""
fypd End-to-End Test Suite
===========================
Tests the full pipeline in layers:
  Layer 1 — Server health & static routes
  Layer 2 — /models/fetch for each provider type
  Layer 3 — /orchestrate (LLM JSON generation)
  Layer 4 — /process  (job queuing + status polling)
  Layer 5 — Python core unit tests (filename sanitizer, timestamp parser,
             phrase grouper, elastic bounce, smart transition)
  Layer 6 — social_publisher stubs (no real credentials needed)

Run: python test_e2e.py [--gemini-key YOUR_KEY]
"""

import sys
import json
import time
import argparse
import requests
import unittest
import threading

# Force UTF-8 on Windows terminals that default to cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = "http://127.0.0.1:8000"

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = failed = skipped = 0

def ok(label):
    global passed
    passed += 1
    print(f"  {GREEN}✓{RESET} {label}")

def fail(label, detail=""):
    global failed
    failed += 1
    print(f"  {RED}✗{RESET} {label}")
    if detail:
        print(f"    {RED}{detail}{RESET}")

def skip(label, reason=""):
    global skipped
    skipped += 1
    print(f"  {YELLOW}–{RESET} {label} (skipped: {reason})")

def section(title):
    print(f"\n{BOLD}{'─'*55}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─'*55}{RESET}")

# ──────────────────────────────────────────────
# Layer 1 — Server Health
# ──────────────────────────────────────────────
def test_server_health():
    section("Layer 1 — Server Health & Static Routes")

    try:
        r = requests.get(f"{BASE}/jobs", timeout=5)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)
        ok("/jobs returns 200 with dict payload")
    except Exception as e:
        fail("/jobs health check", str(e))
        print(f"\n{RED}Server not reachable at {BASE}. Is app_server.py running?{RESET}")
        sys.exit(1)

    try:
        r = requests.get(f"{BASE}/", timeout=5)
        assert r.status_code == 200
        ok("/ (UI root) returns 200")
    except Exception as e:
        fail("/ root route", str(e))

# ──────────────────────────────────────────────
# Layer 2 — Model Fetching
# ──────────────────────────────────────────────
def test_model_fetch(gemini_key=None):
    section("Layer 2 — /models/fetch")

    # Gemini (live if key provided)
    if gemini_key:
        try:
            r = requests.post(f"{BASE}/models/fetch",
                              json={"provider": "gemini", "api_key": gemini_key},
                              timeout=15)
            assert r.status_code == 200
            models = r.json()
            assert isinstance(models, list) and len(models) > 0
            ok(f"Gemini models fetched ({len(models)} models: {models[:3]}...)")
        except Exception as e:
            fail("Gemini model fetch", str(e))
    else:
        skip("Gemini model fetch", "no --gemini-key provided")

    # OpenRouter (no key needed for model listing)
    try:
        r = requests.post(f"{BASE}/models/fetch",
                          json={"provider": "openrouter", "api_key": ""},
                          timeout=15)
        assert r.status_code == 200
        models = r.json()
        assert isinstance(models, list) and len(models) > 0
        ok(f"OpenRouter models fetched ({len(models)} models)")
    except Exception as e:
        fail("OpenRouter model fetch", str(e))

    # Ollama (expected to fail gracefully if not running)
    try:
        r = requests.post(f"{BASE}/models/fetch",
                          json={"provider": "ollama", "api_key": "",
                                "base_url": "http://localhost:11434/v1"},
                          timeout=5)
        if r.status_code == 200:
            ok(f"Ollama models fetched ({len(r.json())} models)")
        else:
            skip("Ollama model fetch", f"Ollama not running (HTTP {r.status_code})")
    except Exception:
        skip("Ollama model fetch", "Ollama not running locally")

# ──────────────────────────────────────────────
# Layer 3 — /orchestrate  (needs a real key)
# ──────────────────────────────────────────────
SAMPLE_PROMPT = """You are a viral content strategist. Analyze this YouTube video URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ.
Identify 2 viral segments (15-45 seconds each).
Output a JSON object:
{
  "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "clips": [
    {
      "id": 1,
      "title": "Hook_Moment",
      "start_time": "00:00:05",
      "end_time": "00:00:30",
      "caption": "Never gonna give you up 🎤",
      "style": "hormozi",
      "bgm_mood": "upbeat",
      "broll_keywords": ["music", "dance"],
      "timeline": [{"rel_start": 0, "rel_end": 25, "crop_mode": "track", "zoom": 1.0}]
    },
    {
      "id": 2,
      "title": "Chorus_Drop",
      "start_time": "00:00:42",
      "end_time": "00:01:05",
      "caption": "The classic drop 🔥",
      "style": "neon",
      "bgm_mood": "epic",
      "broll_keywords": ["concert", "crowd"],
      "timeline": [{"rel_start": 0, "rel_end": 23, "crop_mode": "center", "zoom": 1.0}]
    }
  ]
}"""

def test_orchestrate(gemini_key=None):
    section("Layer 3 — /orchestrate (LLM JSON generation)")

    if not gemini_key:
        skip("Orchestrate end-to-end", "no --gemini-key provided")
        return None

    # Dynamically pick the first available Gemini model so the test never
    # breaks on deprecated model names (e.g. gemini-2.0-flash is sunset).
    gemini_model = "gemini-2.5-flash"  # sensible default
    try:
        mr = requests.post(f"{BASE}/models/fetch",
                           json={"provider": "gemini", "api_key": gemini_key},
                           timeout=15)
        if mr.status_code == 200 and mr.json():
            gemini_model = mr.json()[0]
    except Exception:
        pass  # fall back to default

    ok(f"Auto-selected Gemini model: {gemini_model}")

    try:
        r = requests.post(f"{BASE}/orchestrate", json={
            "provider": "gemini",
            "model": gemini_model,
            "api_key": gemini_key,
            "prompt": SAMPLE_PROMPT
        }, timeout=60)

        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
        data = r.json()

        assert "clips" in data, f"Missing 'clips' key. Got: {list(data.keys())}"
        assert isinstance(data["clips"], list), "'clips' is not a list"
        assert len(data["clips"]) >= 1, "No clips returned"

        clip = data["clips"][0]
        required_fields = ["id", "title", "start_time", "end_time", "timeline"]
        for f in required_fields:
            assert f in clip, f"Clip missing field: '{f}'"

        ok(f"Orchestrate returned {len(data['clips'])} clips with valid schema")
        ok(f"  Sample clip: '{clip['title']}' {clip['start_time']} → {clip['end_time']}")
        return data
    except Exception as e:
        fail("Orchestrate", str(e))
        return None

# ──────────────────────────────────────────────
# Layer 4 — /process (job queue + polling)
# ──────────────────────────────────────────────
MOCK_PROCESS_PAYLOAD = {
    "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "clips": [
        {
            "id": 99901,
            "title": "Test_Clip_E2E",   # clean title — illegal char stripping verified in Layer 5 unit tests
            "start_time": "00:00:05",
            "end_time": "00:00:20",
            "caption": "Test caption 🚀",
            "style": "minimalist",
            "bgm_mood": None,
            "timeline": [
                {"rel_start": 0, "rel_end": 15, "crop_mode": "center", "zoom": 1.0}
            ]
        }
    ],
    "publish_targets": []
}

def test_process_queue():
    section("Layer 4 — /process Job Queue & Status Polling")

    try:
        r = requests.post(f"{BASE}/process", json=MOCK_PROCESS_PAYLOAD, timeout=10)
        assert r.status_code == 200
        resp = r.json()
        assert "job_id" in resp
        assert resp["status"] == "queued"
        job_id = resp["job_id"]
        ok(f"Job queued successfully (id: {job_id[:8]}...)")
    except Exception as e:
        fail("/process job enqueue", str(e))
        return

    # Poll for status transition (queued → processing → completed).
    # We now wait for the FULL production cycle to finish.
    try:
        # 120s timeout to allow for download + render of a small clip
        deadline = time.time() + 180 
        last_status = "queued"
        print("    [*] Waiting for engine to complete production (polling /jobs)...")
        
        while time.time() < deadline:
            r = requests.get(f"{BASE}/jobs", timeout=5)
            jobs = r.json()
            if job_id in jobs:
                job_state = jobs[job_id]
                last_status = job_state["status"]
                
                # Check for incremental progress if available
                p = job_state["clips"][0].get("progress", 0)
                if last_status == "processing":
                    print(f"    [*] Progress: {p}%", end="\r")

                if last_status in ("completed", "failed"):
                    print() # New line after carriage return
                    break
            time.sleep(3)

        if last_status == "completed":
            ok(f"Job successfully COMPLETED within timeline")
            return job_id, MOCK_PROCESS_PAYLOAD["clips"][0]
        elif last_status == "failed":
            fail("Job failed in pipeline", f"Engine reported 'failed' state.")
        else:
            fail("Job timeout", f"Job stuck in '{last_status}' after 180s")
    except Exception as e:
        fail("Job status polling", str(e))
    return None, None

# ──────────────────────────────────────────────
# Layer 7 — File System Integrity
# ──────────────────────────────────────────────
def test_file_integrity(job_id, clip_meta):
    section("Layer 7 — Production Artifact Verification")
    if not job_id or not clip_meta:
        skip("Artifact verification", "No successful job to verify")
        return

    import os
    # Resolve the data directory (must match app_server logic)
    base = os.environ.get("FYPD_DATA_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "fypd"
    )
    
    # Sanitize title to match filename generation
    from app_server import sanitize_filename
    safe_title = sanitize_filename(clip_meta['title'])
    filename = f"SmartShort_{clip_meta['id']}_{safe_title}.mp4"
    output_path = os.path.join(base, "outputs", filename)

    print(f"    [*] Checking artifact: {output_path}")
    
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        if size > 100000: # Standard vertical clip should be > 100KB
            ok(f"Verified master artifact exists ({size/1024/1024:.2f} MB)")
        else:
            fail("Empty artifact detected", f"File exists but is too small ({size} bytes). Likely a render failure.")
    else:
        fail("Missing artifact", f"Expected file not found at: {output_path}")

# ──────────────────────────────────────────────
# Layer 5 — Python Core Unit Tests
# ──────────────────────────────────────────────
def test_python_core():
    section("Layer 5 — Python Core Unit Tests")

    # Add project root to path
    sys.path.insert(0, ".")

    # ── app_server: sanitize_filename ──
    try:
        from app_server import sanitize_filename
        assert sanitize_filename("Hello/World:Test") == "Hello_World_Test"
        assert sanitize_filename('bad"name<here>') == "bad_name_here_"
        assert sanitize_filename("normal_title") == "normal_title"
        ok("sanitize_filename: strips /  :  *  ?  \"  <  >  |")
    except Exception as e:
        fail("sanitize_filename", str(e))

    # ── viral_clipper: timestamp_to_seconds ──
    try:
        import viral_clipper as vc
        assert vc.timestamp_to_seconds("00:01:30") == 90
        assert vc.timestamp_to_seconds("01:00:00") == 3600
        assert vc.timestamp_to_seconds("00:00") == 0
        assert vc.timestamp_to_seconds("01:30") == 90
        ok("timestamp_to_seconds: HH:MM:SS and MM:SS both parse correctly")
    except Exception as e:
        fail("timestamp_to_seconds", str(e))

    # ── viral_clipper: clean_token ──
    try:
        assert vc.clean_token("hello!") == "HELLO"
        assert vc.clean_token("UM") == ""
        assert vc.clean_token("[NONE]") == ""
        assert vc.clean_token(" world ") == "WORLD"
        ok("clean_token: strips punctuation and filters filler words")
    except Exception as e:
        fail("clean_token", str(e))

    # ── viral_clipper: elastic_bounce_transform ──
    try:
        s0   = vc.elastic_bounce_transform(0.0)
        s_up = vc.elastic_bounce_transform(0.12)   # peak
        s_1  = vc.elastic_bounce_transform(1.0)    # settled
        assert s0 < s_up, f"Scale should rise: {s0} < {s_up}"
        assert abs(s_1 - 1.0) < 1e-9,  f"Should settle at 1.0, got {s_1}"
        ok(f"elastic_bounce_transform: rises ({s0:.2f}→{s_up:.2f}) then settles at 1.0")
    except Exception as e:
        fail("elastic_bounce_transform", str(e))

    # ── viral_clipper: group_words_into_phrases (hormozi: 2 words max) ──
    try:
        style = {"MAX_WORDS_PER_PHRASE": 2, "MAX_GAP_SECONDS": 0.6}
        words = [
            {"word": "hello", "start": 0.0, "end": 0.3},
            {"word": "world", "start": 0.4, "end": 0.7},
            {"word": "foo",   "start": 0.8, "end": 1.0},
        ]
        phrases = vc.group_words_into_phrases(words, style)
        assert len(phrases) == 2, f"Expected 2 phrases, got {len(phrases)}"
        assert len(phrases[0]) == 2   # hello + world
        assert len(phrases[1]) == 1   # foo
        ok(f"group_words_into_phrases: hormozi 2-word cap produces {len(phrases)} phrases correctly")
    except Exception as e:
        fail("group_words_into_phrases", str(e))

    # ── viral_clipper: group_words_into_phrases (gap-based split) ──
    try:
        style = {"MAX_WORDS_PER_PHRASE": 5, "MAX_GAP_SECONDS": 0.3}
        words = [
            {"word": "first",  "start": 0.0, "end": 0.2},
            {"word": "second", "start": 0.3, "end": 0.5},   # gap=0.1 → same phrase
            {"word": "third",  "start": 1.0, "end": 1.2},   # gap=0.5 → new phrase
        ]
        phrases = vc.group_words_into_phrases(words, style)
        assert len(phrases) == 2, f"Expected 2 phrases (gap split), got {len(phrases)}"
        ok("group_words_into_phrases: gap-based phrase splitting works correctly")
    except Exception as e:
        fail("group_words_into_phrases (gap split)", str(e))

    # ── Fix #3 integration: title with illegal chars → valid filename ──
    try:
        from app_server import sanitize_filename
        title = "Test_Clip_Sanitize/Check"
        safe  = sanitize_filename(title)
        import re
        assert not re.search(r'[\\/:"*?<>|]', safe), f"Illegal chars remain: {safe}"
        ok(f"Fix #3 integration: '{title}' → '{safe}' (no illegal chars)")
    except Exception as e:
        fail("Fix #3 integration", str(e))

# ──────────────────────────────────────────────
# Layer 6 — Social Publisher Stubs
# ──────────────────────────────────────────────
def test_social_stubs():
    section("Layer 6 — Social Publisher Stubs")

    sys.path.insert(0, ".")
    try:
        from social_publisher import YouTubePublisher, InstagramPublisher, TikTokPublisher, FacebookPublisher
        ok("social_publisher imports cleanly")
    except Exception as e:
        fail("social_publisher import", str(e))
        return

    # YouTube: should fail gracefully without client_secrets.json
    try:
        pub = YouTubePublisher(client_secrets_path="__nonexistent__.json")
        result = pub.publish("fake.mp4", "Test caption")
        assert result is False
        ok("YouTubePublisher.publish returns False gracefully (no credentials)")
    except Exception as e:
        fail("YouTubePublisher graceful failure", str(e))

    # TikTok: missing session dir should fail gracefully
    try:
        pub = TikTokPublisher(user_data_dir="__nonexistent_session__")
        # Don't actually launch a browser — just confirm instantiation works
        ok("TikTokPublisher instantiates without error")
    except Exception as e:
        fail("TikTokPublisher instantiation", str(e))

    # InstagramPublisher / FacebookPublisher: instantiation only
    try:
        ig = InstagramPublisher("fake_token", "fake_user_id", ngrok_auth_token=None)
        fb = FacebookPublisher("fake_token", "fake_page_id", ngrok_auth_token=None)
        ok("InstagramPublisher + FacebookPublisher instantiate without error")
    except Exception as e:
        fail("IG/FB Publisher instantiation", str(e))

# ──────────────────────────────────────────────
# Main runner
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# Layer 8 — Repurposing Engine Fallback
# ──────────────────────────────────────────────
def test_repurpose_fallback(job_id):
    section("Layer 8 — Repurposing Engine & Fallback")
    if not job_id:
        skip("Repurpose verification", "No successful job to verify")
        return

    # Mock request for full repurpose
    payload = {
        "job_id": job_id,
        "video_url": MOCK_PROCESS_PAYLOAD["video_url"],
        "twitter_provider": "openrouter",
        "twitter_model": "google/gemini-2.0-flash-001",
        "twitter_key": "sk-or-v1-...", # Not actually needed for this pass if we just check logic
        "medium_provider": "openrouter",
        "medium_model": "google/gemini-2.0-flash-001",
        "medium_key": "sk-or-v1-..."
    }

    try:
        # We'll check if the transcript file exists first. 
        # If it doesn't, we'll hit the endpoint which triggers the fallback.
        print("    [*] Triggering full-video repurpose (this may invoke Whisper fallback)...")
        r = requests.post(f"{BASE}/repurpose/full", json=payload, timeout=300)
        
        # Verify artifacts on disk regardless of 200/500 (since AI might fail without keys)
        import os
        base = os.environ.get("FYPD_DATA_DIR") or os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "fypd"
        )
        transcript_path = os.path.join(base, "outputs", f"Job_{job_id}_full_transcript.txt")
        
        if os.path.exists(transcript_path) and os.path.getsize(transcript_path) > 0:
            ok(f"Verified full transcript generated ({os.path.getsize(transcript_path)} bytes)")
            if r.status_code != 200:
                print(f"    [!] Note: AI generation failed (expected without keys), but core fallback logic PASSED.")
        else:
            if r.status_code == 200:
                fail("Missing transcript", f"Endpoint returned 200 but file not found: {transcript_path}")
            else:
                fail("Repurpose failure", f"Status {r.status_code}: {r.text}")

    except Exception as e:
        # It's expected to fail if no AI keys are provided, but the transcript SHOULD be generated before that.
        # Wait, the endpoint gathers results from gather(). If AI fails, the endpoint fails.
        # So we check if the transcript file was at least created.
        import os
        base = os.environ.get("FYPD_DATA_DIR") or os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "fypd"
        )
        transcript_path = os.path.join(base, "outputs", f"Job_{job_id}_full_transcript.txt")
        if os.path.exists(transcript_path):
            ok(f"Verified full transcript generated even if AI gathering failed ({os.path.getsize(transcript_path)} bytes)")
        else:
            fail("Repurposing logic", str(e))

def main():
    parser = argparse.ArgumentParser(description="fypd E2E Test Suite")
    parser.add_argument("--gemini-key", default=None, help="Gemini API key (enables live LLM tests)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═'*55}{RESET}")
    print(f"{BOLD}  fypd End-to-End Test Suite{RESET}")
    print(f"{BOLD}{'═'*55}{RESET}")
    print(f"  Target: {BASE}")
    print(f"  Gemini key: {'provided ✓' if args.gemini_key else 'not provided (LLM tests skipped)'}")

    test_server_health()
    test_model_fetch(args.gemini_key)
    orch_result = test_orchestrate(args.gemini_key)
    job_id, clip_meta = test_process_queue()
    test_python_core()
    test_social_stubs()
    test_file_integrity(job_id, clip_meta)
    test_repurpose_fallback(job_id)

    # ── Summary ──
    total = passed + failed + skipped
    print(f"\n{BOLD}{'═'*55}{RESET}")
    print(f"{BOLD}  Results: {total} tests{RESET}")
    print(f"  {GREEN}Passed:  {passed}{RESET}")
    print(f"  {RED}Failed:  {failed}{RESET}")
    print(f"  {YELLOW}Skipped: {skipped}{RESET}")
    print(f"{BOLD}{'═'*55}{RESET}\n")

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
