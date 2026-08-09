import os
import sys
import json
import logging

# --- Load .env before anything reads configuration ---
# README and .env.example both document these settings, but nothing ever loaded
# the file, so IMAGEMAGICK_BINARY / HOST / PORT were silently ignored.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; process environment still applies

# --- Resolve writable data directory ---
# When launched by Tauri, FYPD_DATA_DIR is injected as an env var.
# In dev mode (python app_server.py directly), fall back to a user AppData path.
_FYPD_DATA = os.environ.get("FYPD_DATA_DIR") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "fypd"
)
LOG_DIR    = os.path.join(_FYPD_DATA, "logs")
OUTPUT_DIR = os.path.join(_FYPD_DATA, "outputs")
TEMP_DIR   = os.path.join(_FYPD_DATA, "temp")
CRASH_LOG  = os.path.join(_FYPD_DATA, "crash_log.txt")

for _d in (LOG_DIR, OUTPUT_DIR, TEMP_DIR):
    os.makedirs(_d, exist_ok=True)

log_file = os.path.join(LOG_DIR, "fypd.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

class StreamToLogger:
    def __init__(self, logger, log_level):
        self.logger = logger
        self.log_level = log_level
        
    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())
            
    def flush(self):
        pass

    def isatty(self):
        return False

# Redirect stdout and stderr to the log file
sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO)
sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR)
import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import viral_clipper
import social_publisher
import subprocess
import glob
import webbrowser
import time
import re
from threading import Timer
from fastapi.responses import FileResponse
import litellm

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# Cap the in-memory job store; it previously grew for the lifetime of the process
# and was returned in full on every dashboard poll.
MAX_JOBS_RETAINED = 50


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = asyncio.create_task(background_worker())
    try:
        yield
    finally:
        worker.cancel()


app = FastAPI(title="fypd Backend", lifespan=lifespan)

# Global Paths
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Keep for runtime output folder
FRONTEND_DIR = get_resource_path("dist_frontend")

# In-memory job store and queue
jobs = {}
job_queue = asyncio.Queue()

# This server is unauthenticated and holds the user's API keys, so a wildcard
# origin let any website they happened to be browsing drive the whole pipeline.
# Only the dashboard's own origins are allowed.
ALLOWED_ORIGINS = [
    f"http://{HOST}:{PORT}",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",   # vite dev server
    "http://localhost:5173",
    "tauri://localhost",       # packaged desktop webview (macOS/Linux)
    "http://tauri.localhost",  # packaged desktop webview (Windows)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class ClipTimeline(BaseModel):
    rel_start: float
    rel_end: float
    crop_mode: str = "center"
    zoom: float = 1.0

class Clip(BaseModel):
    id: int
    title: str
    start_time: str
    end_time: str
    caption: Optional[str] = None
    timeline: List[ClipTimeline] = []
    # These three drive the visual style, B-roll lookup and background music.
    # They were absent from the model, so Pydantic dropped them before the
    # payload ever reached the clipper: every clip rendered as "hormozi" with
    # no B-roll and no BGM regardless of what the UI or the model selected.
    style: Optional[str] = None
    bgm_mood: Optional[str] = None
    broll_keywords: List[str] = []

class ProcessRequest(BaseModel):
    video_url: str
    clips: List[Clip]
    pexels_key: Optional[str] = None
    publish_targets: List[str] = [] # ["youtube", "instagram", "tiktok", "facebook"]
    ig_access_token: Optional[str] = None
    ig_user_id: Optional[str] = None
    fb_access_token: Optional[str] = None
    fb_page_id: Optional[str] = None
    ngrok_token: Optional[str] = None
    
    # Dual-model Content Repurposing configurations
    auto_repurpose: Optional[bool] = False
    twitter_provider: Optional[str] = None
    twitter_model: Optional[str] = None
    twitter_key: Optional[str] = None
    twitter_base_url: Optional[str] = None
    medium_provider: Optional[str] = None
    medium_model: Optional[str] = None
    medium_key: Optional[str] = None
    medium_base_url: Optional[str] = None

class FullRepurposeRequest(BaseModel):
    job_id: str
    video_url: str
    
    # Twitter Model Config
    twitter_provider: str
    twitter_model: str
    twitter_key: str
    twitter_base_url: Optional[str] = None
    
    # Medium Model Config
    medium_provider: str
    medium_model: str
    medium_key: str
    medium_base_url: Optional[str] = None
    
    directive: Optional[str] = None

def fetch_youtube_transcript(video_url: str, job_id: str) -> str:
    """Downloads auto-generated YouTube subtitles in VTT/SRT format and strips timestamps to return a clean plain-text transcript."""
    # Staged in TEMP_DIR, not OUTPUT_DIR: everything under OUTPUT_DIR is served
    # over HTTP at /videos, and leftover subtitle files were being published there.
    output_template = os.path.join(TEMP_DIR, f"Job_{job_id}_subtitles")

    # Run yt-dlp to write auto-generated subs, skip video download, in VTT or SRT format
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--write-auto-subs",
        "--write-subs",
        "--skip-download",
        "--sub-format", "vtt/srt/best",
        "--output", output_template,
        video_url
    ]
    
    sub_files = []
    try:
        print(f"[*] Extracting YouTube subtitles for {video_url}...")
        # Since it skips video download, it should finish in less than 1.5s.
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)

        # Search for downloaded subtitle file in the staging directory
        sub_files = glob.glob(f"{output_template}.*")
        if not sub_files:
            raise Exception("No subtitle files downloaded.")

        sub_file = sub_files[0]
        print(f"[+] Subtitles downloaded to {sub_file}")

        with open(sub_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Clean VTT/SRT timestamps and metadata
        clean_lines = []
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line == "WEBVTT" or line.startswith("Kind:") or line.startswith("Language:") or line.isdigit():
                continue
            if "-->" in line:
                continue
            line = re.sub(r"<[^>]+>", "", line)
            if line:
                clean_lines.append(line)
        
        # Deduplicate consecutive identical lines
        dedup_lines = []
        for line in clean_lines:
            if not dedup_lines or dedup_lines[-1] != line:
                dedup_lines.append(line)
                
        return " ".join(dedup_lines)

    except Exception as e:
        print(f"[-] Failed to fetch subtitles via yt-dlp: {e}")
        return ""
    finally:
        # Remove every downloaded language variant, not just the one we parsed.
        for stale in sub_files or glob.glob(f"{output_template}.*"):
            try:
                os.remove(stale)
            except OSError:
                pass

# Re-exported from the shared core so the server and the renderer can never
# drift on the filenames they produce (Fix #3: characters illegal on Windows).
from fypd_core import sanitize_filename  # noqa: E402

# ==============================================================================
# CONTENT REPURPOSING (shared by the autonomous pass and the on-demand endpoint)
# ==============================================================================
# response_format={"type": "json_object"} is only valid for OpenAI and Gemini.
# Anthropic handles JSON mode via its own mechanism (managed by litellm
# internally); passing this kwarg to the Anthropic endpoint raises a 400 error.
JSON_MODE_PROVIDERS = {"openai", "gemini"}

def build_model_string(provider: str, model: str) -> str:
    """LiteLLM model identifier, standardising OpenAI-compatible local proxies."""
    if provider in ("ollama", "lm_studio"):
        return f"openai/{model}"
    return f"{provider}/{model}"

def _directive_block(directive: Optional[str]) -> str:
    if not directive:
        return ""
    return f"\nCUSTOM USER DIRECTIVE: {directive}\nYou MUST satisfy this custom instruction."

def build_twitter_prompt(transcript: str, directive: Optional[str] = None) -> str:
    return f"""You are an expert ghostwriter and viral growth hacker.
Based on the following video transcript:
"{transcript}"

Generate an opinionated, highly engaging, and viral Twitter/X thread (3 to 5 tweets).{_directive_block(directive)}

Guidelines:
1. The first tweet must be a high-converting hook that grabs attention, states a bold or controversial opinion, and makes the reader want to read the thread.
2. Use clean formatting, spacing, and short sentences.
3. Include relevant emojis sparingly.
4. Ensure each tweet is under 280 characters.
5. The last tweet should encourage discussion or summarize the main takeaway.

Output a JSON object with this exact schema:
{{
    "tweets": [
        "Tweet 1 text here...",
        "Tweet 2 text here...",
        ...
    ]
}}"""

def build_medium_prompt(transcript: str, directive: Optional[str] = None) -> str:
    return f"""You are a professional tech blogger and content editor.
Based on the following video transcript:
"{transcript}"

Write a high-quality, engaging, and detailed Medium article (300 to 600 words) discussing the core topics of the transcript.{_directive_block(directive)}

Guidelines:
1. Create an eye-catching, SEO-optimized title at the top.
2. Use a structured hierarchy with descriptive H2/H3 subtitles.
3. Write in an opinionated, authoritative, yet approachable tone.
4. Break the content into readable paragraphs with bullet points or blockquotes for key takeaways.
5. Add a compelling conclusion.

Format the output as a beautiful Markdown document."""

def generate_twitter_thread(job_id, transcript, provider, model, key, base_url, directive=None) -> dict:
    """Draft a Twitter thread and persist it next to the job's other artifacts."""
    model_string = build_model_string(provider, model)
    extra_kwargs = {"response_format": {"type": "json_object"}} if provider in JSON_MODE_PROVIDERS else {}

    print(f"[*] Generating Twitter thread using {model_string}...")
    response = litellm.completion(
        model=model_string,
        messages=[{"role": "user", "content": build_twitter_prompt(transcript, directive)}],
        api_key=key or "local",
        base_url=base_url,
        max_tokens=2000,
        **extra_kwargs
    )
    content = response.choices[0].message.content

    # Robust regex extraction (handles markdown fences and conversational filler)
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("No valid JSON found in Twitter thread response")

    payload = json.loads(match.group())
    tweets_filename = os.path.join(OUTPUT_DIR, f"Job_{job_id}_full_tweets.json")
    with open(tweets_filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
    print(f"[+] Saved generated tweets to {tweets_filename}")
    return payload

def generate_medium_article(job_id, transcript, provider, model, key, base_url, directive=None) -> str:
    """Draft a Medium article and persist it next to the job's other artifacts."""
    model_string = build_model_string(provider, model)

    print(f"[*] Generating Medium article using {model_string}...")
    response = litellm.completion(
        model=model_string,
        messages=[{"role": "user", "content": build_medium_prompt(transcript, directive)}],
        api_key=key or "local",
        base_url=base_url,
        max_tokens=4000
    )
    content = response.choices[0].message.content

    medium_filename = os.path.join(OUTPUT_DIR, f"Job_{job_id}_full_medium.md")
    with open(medium_filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Saved generated Medium article to {medium_filename}")
    return content

def resolve_transcript(video_url: str, job_id: str) -> str:
    """Return a transcript from cache, YouTube subtitles, or local Whisper."""
    transcript_filename = os.path.join(OUTPUT_DIR, f"Job_{job_id}_full_transcript.txt")
    if os.path.exists(transcript_filename):
        print(f"[*] Found cached full transcript for Job {job_id}...")
        with open(transcript_filename, "r", encoding="utf-8") as f:
            return f.read()

    transcript = fetch_youtube_transcript(video_url, job_id)
    if not transcript:
        print("[*] YouTube subtitles unavailable. Activating Whisper local fallback...")
        transcript = viral_clipper.fallback_full_transcription(video_url, job_id)

    if transcript:
        with open(transcript_filename, "w", encoding="utf-8") as f:
            f.write(transcript)
    return transcript or ""

def run_clipper_sync(job_id: str, data: dict):
    """Core synchronous processing logic executed in a separate thread"""
    def set_clip(clip_id, **fields):
        for c in jobs[job_id]["clips"]:
            if c["id"] == clip_id:
                c.update(fields)
                break

    try:
        def on_clip_done(clip_id, filename=None):
            # Record the real filename the renderer produced so the dashboard
            # never has to re-derive it from the (unsanitized) clip title.
            fields = {"status": "completed", "progress": 100}
            if filename:
                fields["filename"] = filename
            set_clip(clip_id, **fields)

        def on_clip_progress(clip_id, progress):
            set_clip(clip_id, status="processing", progress=progress)

        # Run the clipper with real-time feedback
        viral_clipper.run_production_clipper(data, on_clip_completed=on_clip_done, on_progress=on_clip_progress)

        # Post-Processing: Direct Social Upload
        targets = data.get("publish_targets", [])
        if targets:
            print(f"[*] Initiating automated publishing to: {targets}")
            for clip in data["clips"]:
                # Fix #3: Sanitize title to remove characters illegal on Windows.
                safe_title = sanitize_filename(clip['title'])
                video_path = os.path.join(OUTPUT_DIR, f"SmartShort_{clip['id']}_{safe_title}.mp4")
                caption = clip.get("caption") or "New Short from fypd"

                if "youtube" in targets:
                    social_publisher.YouTubePublisher().publish(video_path, caption)

                if "instagram" in targets:
                    social_publisher.InstagramPublisher(
                        data.get("ig_access_token"),
                        data.get("ig_user_id"),
                        data.get("ngrok_token")
                    ).publish(video_path, caption)

                if "tiktok" in targets:
                    social_publisher.TikTokPublisher().publish(video_path, caption)

                if "facebook" in targets:
                    social_publisher.FacebookPublisher(
                        data.get("fb_access_token"),
                        data.get("fb_page_id"),
                        data.get("ngrok_token")
                    ).publish(video_path, caption)

        # Autonomous Full-Video Repurposing Post-Render Pass
        if data.get("auto_repurpose"):
            print(f"[*] Autonomous full-video repurposing active for Job {job_id}...")
            transcript = resolve_transcript(data.get("video_url"), job_id)

            if not transcript:
                print("[-] No transcript available; skipping autonomous repurposing.")
            else:
                print("[+] Transcript retrieved successfully.")
                try:
                    generate_twitter_thread(
                        job_id, transcript,
                        data.get("twitter_provider"), data.get("twitter_model"),
                        data.get("twitter_key"), data.get("twitter_base_url"),
                    )
                except Exception as e:
                    print(f"[-] Twitter thread auto-generation failed: {e}")

                try:
                    generate_medium_article(
                        job_id, transcript,
                        data.get("medium_provider"), data.get("medium_model"),
                        data.get("medium_key"), data.get("medium_base_url"),
                    )
                except Exception as e:
                    print(f"[-] Medium article auto-generation failed: {e}")

        # Update job status
        jobs[job_id]["status"] = "completed"
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        # Mark unfinished clips failed too. The dashboard renders per-clip status
        # in preference to job status, so leaving them on "processing" left the
        # cards spinning forever and hid the real error (a missing ImageMagick,
        # most often) in the log file.
        for c in jobs[job_id]["clips"]:
            if c.get("status") != "completed":
                c["status"] = "failed"
                c["error"] = str(e)

async def background_worker():
    """Sequentially processes jobs from the queue"""
    print("[*] Background worker started. Ready for processing.")
    while True:
        job_id, job_data = await job_queue.get()
        jobs[job_id]["status"] = "processing"
        print(f"[*] Processing Job: {job_id}")
        
        try:
            # Execute blocking CPU-heavy task in a thread pool
            await asyncio.to_thread(run_clipper_sync, job_id, job_data)
        except Exception as e:
            # run_clipper_sync handles its own errors, but a failure to even
            # dispatch must not silently kill the worker for the whole session.
            print(f"[-] Worker error on job {job_id}: {e}")
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
        finally:
            job_queue.task_done()
            print(f"[+] Finished Job: {job_id}")

@app.get("/health")
async def health():
    """Reports external toolchain readiness so the UI can show setup problems."""
    try:
        await asyncio.to_thread(viral_clipper.preflight_dependencies)
        return {"ok": True, "imagemagick": viral_clipper.IMAGEMAGICK_PATH}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/")
async def serve_ui():
    if os.path.exists(os.path.join(FRONTEND_DIR, "index.html")):
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/favicon.svg")
async def serve_favicon():
    if os.path.exists(os.path.join(FRONTEND_DIR, "favicon.svg")):
        return FileResponse(os.path.join(FRONTEND_DIR, "favicon.svg"))
    return FileResponse(os.path.join(BASE_DIR, "frontend/public/favicon.svg"))

def dump_model(model: BaseModel) -> dict:
    """Serialize a Pydantic model across v1 and v2."""
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()

def evict_old_jobs():
    """Drop the oldest finished jobs once the store exceeds its cap."""
    if len(jobs) <= MAX_JOBS_RETAINED:
        return
    finished = [jid for jid, j in jobs.items() if j.get("status") in ("completed", "failed")]
    for jid in finished[: len(jobs) - MAX_JOBS_RETAINED]:
        jobs.pop(jid, None)

@app.post("/process")
async def process_video(request: ProcessRequest):
    if not request.clips:
        raise HTTPException(status_code=400, detail="No clips supplied for processing.")

    job_id = str(uuid.uuid4())
    job_data = dump_model(request)

    # Initialize per-clip status tracking for real-time frontend updates
    for clip in job_data["clips"]:
        clip["status"] = "pending"
        clip["progress"] = 0
        clip["filename"] = f"SmartShort_{clip['id']}_{sanitize_filename(clip['title'])}.mp4"

    evict_old_jobs()
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "video_url": request.video_url,
        "clips": job_data["clips"]
    }

    await job_queue.put((job_id, job_data))

    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs")
async def get_jobs():
    return jobs

class OrchestrateRequest(BaseModel):
    provider: str
    model: str
    api_key: str
    prompt: str
    base_url: Optional[str] = None

@app.post("/orchestrate")
async def orchestrate_ai(request: OrchestrateRequest):
    """Universal LLM orchestrator using LiteLLM with Regex JSON extraction"""
    try:
        model_string = build_model_string(request.provider, request.model)

        print(f"[*] Orchestrating with {model_string}...")

        extra_kwargs = {}
        if request.provider in JSON_MODE_PROVIDERS:
            extra_kwargs["response_format"] = {"type": "json_object"}

        response = await asyncio.to_thread(
            litellm.completion,
            model=model_string,
            messages=[{"role": "user", "content": request.prompt}],
            api_key=request.api_key,
            base_url=request.base_url,
            max_tokens=8000,
            **extra_kwargs
        )
        
        content = response.choices[0].message.content
        
        # Robust Regex JSON Extraction (Handles Markdown and conversational filler)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            raise Exception("No valid JSON found in LLM response")

    except Exception as e:
        print(f"[-] Orchestration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class FetchModelsRequest(BaseModel):
    provider: str
    api_key: str
    base_url: Optional[str] = None

@app.post("/models/fetch")
async def fetch_provider_models(request: FetchModelsRequest):
    """Pings provider endpoints to retrieve available models"""
    import requests

    def _get(url, **kwargs):
        kwargs.setdefault("timeout", 30)
        res = requests.get(url, **kwargs)
        res.raise_for_status()
        return res.json()

    try:
        # For Local providers, we assume OpenAI compatibility
        url = request.base_url
        if request.provider == "ollama" and not url: url = "http://localhost:11434/v1"
        if request.provider == "lm_studio" and not url: url = "http://localhost:1234/v1"

        if request.provider in ["ollama", "lm_studio"]:
            return [m["id"] for m in _get(f"{url}/models").get("data", [])]

        # For cloud providers, use LiteLLM's mapping or standard endpoints
        # Note: LiteLLM model_list can be heavy, so we'll provide standard fallbacks
        if request.provider == "openai":
            data = _get("https://api.openai.com/v1/models",
                        headers={"Authorization": f"Bearer {request.api_key}"})
            return [m["id"] for m in data.get("data", []) if "gpt" in m["id"]]

        if request.provider == "gemini":
            # Key passed as a header, not a query string: URLs land in proxy logs
            # and exception traces, and this one carried the user's API key.
            data = _get("https://generativelanguage.googleapis.com/v1beta/models",
                        headers={"x-goog-api-key": request.api_key})
            return [m["name"].replace("models/", "") for m in data.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])]

        if request.provider == "anthropic":
            # Previously unhandled: the UI offered Claude, then fell through to
            # the "default" stub below and every subsequent completion failed.
            data = _get("https://api.anthropic.com/v1/models",
                        headers={"x-api-key": request.api_key,
                                 "anthropic-version": "2023-06-01"})
            return [m["id"] for m in data.get("data", [])]

        if request.provider == "openrouter":
            return [m["id"] for m in _get("https://openrouter.ai/api/v1/models").get("data", [])]

        return ["default"] # Fallback

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tiktok/login")
async def tiktok_login():
    """Launches a visible browser for the user to log in to TikTok manually"""
    from playwright.sync_api import sync_playwright
    import threading
    
    def launch_browser():
        with sync_playwright() as p:
            # Persistent context to save cookies (same absolute profile the
            # publisher reads, rather than a cwd-relative folder).
            browser = p.chromium.launch_persistent_context(
                social_publisher.tiktok_session_dir(),
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            page.goto("https://www.tiktok.com/login", wait_until="networkidle")
            print("[*] TikTok Login window open. Please log in manually and close the browser.")
            # Wait for user to close browser
            while True:
                try:
                    if not browser.pages: break
                    time.sleep(1)
                except: break
            print("[+] TikTok Session Saved.")
    
    threading.Thread(target=launch_browser).start()
    return {"status": "Login window launched. Please check your desktop."}

@app.post("/repurpose/full")
async def repurpose_full_video(request: FullRepurposeRequest):
    """Generates an opinionated Twitter thread and Medium article draft for the complete video."""
    try:
        transcript = await asyncio.to_thread(resolve_transcript, request.video_url, request.job_id)
        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="Could not retrieve subtitles from the video or local fallback. "
                       "Please ensure the video has audio and is accessible."
            )

        # Draft both pieces concurrently; they hit different providers.
        tweets, article = await asyncio.gather(
            asyncio.to_thread(
                generate_twitter_thread, request.job_id, transcript,
                request.twitter_provider, request.twitter_model,
                request.twitter_key, request.twitter_base_url, request.directive,
            ),
            asyncio.to_thread(
                generate_medium_article, request.job_id, transcript,
                request.medium_provider, request.medium_model,
                request.medium_key, request.medium_base_url, request.directive,
            )
        )

        return {
            "tweets": tweets.get("tweets", []),
            "article": article
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[-] Full video repurposing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount the outputs folder so the browser can stream rendered videos
app.mount("/videos", StaticFiles(directory=OUTPUT_DIR), name="videos")

# Mount React static files if built
if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

if __name__ == "__main__":
    import uvicorn
    try:
        # Surface a broken toolchain at startup instead of at first render.
        try:
            viral_clipper.preflight_dependencies()
        except Exception as e:
            print(f"[-] Dependency check failed: {e}")

        # Open the browser to the local server address
        Timer(1.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
        uvicorn.run(app, host=HOST, port=PORT)
    except Exception as e:
        with open(CRASH_LOG, "w") as f:
            f.write(f"CRASH REPORT:\n{str(e)}")
            import traceback
            f.write(traceback.format_exc())
