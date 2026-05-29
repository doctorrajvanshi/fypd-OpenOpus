import os
import sys
import json
import logging

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

app = FastAPI(title="fypd Backend")

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
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
    timeline: List[ClipTimeline]

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
    output_template = os.path.join(OUTPUT_DIR, f"Job_{job_id}_subtitles")
    
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
    
    try:
        print(f"[*] Extracting YouTube subtitles for {video_url}...")
        # Since it skips video download, it should finish in less than 1.5s.
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Search for downloaded subtitle file in output directory
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
                
        transcript = " ".join(dedup_lines)
        
        # Clean up the downloaded subtitle file so it doesn't clutter outputs
        try:
            os.remove(sub_file)
        except Exception:
            pass
            
        return transcript
        
    except Exception as e:
        print(f"[-] Failed to fetch subtitles via yt-dlp: {e}")
        return ""

# Fix #3: Characters illegal in Windows filenames.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')

def sanitize_filename(name: str) -> str:
    """Strip characters that are illegal in Windows filenames."""
    return _ILLEGAL_FILENAME_CHARS.sub('_', name).strip()

def run_clipper_sync(job_id: str, data: dict):
    """Core synchronous processing logic executed in a separate thread"""
    try:
        def on_clip_done(clip_id):
            for c in jobs[job_id]["clips"]:
                if c["id"] == clip_id:
                    c["status"] = "completed"
                    c["progress"] = 100
                    break
                    
        def on_clip_progress(clip_id, progress):
            for c in jobs[job_id]["clips"]:
                if c["id"] == clip_id:
                    c["status"] = "processing"
                    c["progress"] = progress
                    break

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
                caption = clip.get("caption", "New Short from fypd")
                
                if "youtube" in targets:
                    publisher = social_publisher.YouTubePublisher()
                    publisher.publish(video_path, caption)
                
                if "instagram" in targets:
                    publisher = social_publisher.InstagramPublisher(
                        data.get("ig_access_token"), 
                        data.get("ig_user_id"),
                        data.get("ngrok_token")
                    )
                    publisher.publish(video_path, caption)

                if "tiktok" in targets:
                    publisher = social_publisher.TikTokPublisher()
                    publisher.publish(video_path, caption)

                if "facebook" in targets:
                    publisher = social_publisher.FacebookPublisher(
                        data.get("fb_access_token"), 
                        data.get("fb_page_id"),
                        data.get("ngrok_token")
                    )
                    publisher.publish(video_path, caption)

        # Autonomous Full-Video Repurposing Post-Render Pass
        if data.get("auto_repurpose"):
            print(f"[*] Autonomous full-video repurposing active for Job {job_id}...")
            video_url = data.get("video_url")

            # 1. Fetch transcript (Try YouTube subtitles first, fallback to local Whisper)
            transcript = fetch_youtube_transcript(video_url, job_id)
            if not transcript:
                print("[*] YouTube subtitles unavailable. Activating Whisper local fallback...")
                transcript = viral_clipper.fallback_full_transcription(video_url, job_id)

            if transcript:
                print("[+] Transcript retrieved successfully. Writing transcript file...")
                transcript_filename = os.path.join(OUTPUT_DIR, f"Job_{job_id}_full_transcript.txt")
                with open(transcript_filename, "w", encoding="utf-8") as f:
                    f.write(transcript)
                # 2. Generate Twitter Thread
                try:
                    t_provider = data.get("twitter_provider")
                    t_model = data.get("twitter_model")
                    t_key = data.get("twitter_key") or "local"
                    t_base_url = data.get("twitter_base_url")
                    
                    t_model_string = f"{t_provider}/{t_model}"
                    if t_provider in ["ollama", "lm_studio"]:
                        t_model_string = f"openai/{t_model}"
                    
                    extra_kwargs = {}
                    if t_provider in ["openai", "gemini"]:
                        extra_kwargs["response_format"] = {"type": "json_object"}
                    
                    print(f"[*] Auto-generating Twitter thread using {t_model_string}...")
                    t_prompt = f"""You are an expert ghostwriter and viral growth hacker. 
Based on the following video transcript:
"{transcript}"

Generate an opinionated, highly engaging, and viral Twitter/X thread (3 to 5 tweets).

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
                    
                    t_response = litellm.completion(
                        model=t_model_string,
                        messages=[{"role": "user", "content": t_prompt}],
                        api_key=t_key,
                        base_url=t_base_url,
                        max_tokens=2000,
                        **extra_kwargs
                    )
                    t_content = t_response.choices[0].message.content
                    
                    # Regex extraction
                    t_match = re.search(r"\{.*\}", t_content, re.DOTALL)
                    if t_match:
                        t_json = json.loads(t_match.group())
                        tweets_filename = os.path.join(OUTPUT_DIR, f"Job_{job_id}_full_tweets.json")
                        with open(tweets_filename, "w", encoding="utf-8") as f:
                            json.dump(t_json, f, indent=4)
                        print(f"[+] Saved auto-generated tweets to {tweets_filename}")
                except Exception as e:
                    print(f"[-] Twitter thread auto-generation failed: {e}")
                
                # 3. Generate Medium Article
                try:
                    m_provider = data.get("medium_provider")
                    m_model = data.get("medium_model")
                    m_key = data.get("medium_key") or "local"
                    m_base_url = data.get("medium_base_url")
                    
                    m_model_string = f"{m_provider}/{m_model}"
                    if m_provider in ["ollama", "lm_studio"]:
                        m_model_string = f"openai/{m_model}"
                    
                    print(f"[*] Auto-generating Medium article using {m_model_string}...")
                    m_prompt = f"""You are a professional tech blogger and content editor. 
Based on the following video transcript:
"{transcript}"

Write a high-quality, engaging, and detailed Medium article (300 to 600 words) discussing the core topics of the transcript.

Guidelines:
1. Create an eye-catching, SEO-optimized title at the top.
2. Use a structured hierarchy with descriptive H2/H3 subtitles.
3. Write in an opinionated, authoritative, yet approachable tone.
4. Break the content into readable paragraphs with bullet points or blockquotes for key takeaways.
5. Add a compelling conclusion.

Format the output as a beautiful Markdown document."""
                    
                    m_response = litellm.completion(
                        model=m_model_string,
                        messages=[{"role": "user", "content": m_prompt}],
                        api_key=m_key,
                        base_url=m_base_url,
                        max_tokens=4000
                    )
                    m_content = m_response.choices[0].message.content
                    
                    medium_filename = os.path.join(OUTPUT_DIR, f"Job_{job_id}_full_medium.md")
                    with open(medium_filename, "w", encoding="utf-8") as f:
                        f.write(m_content)
                    print(f"[+] Saved auto-generated Medium article to {medium_filename}")
                except Exception as e:
                    print(f"[-] Medium article auto-generation failed: {e}")

        # Update job status
        jobs[job_id]["status"] = "completed"
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

async def background_worker():
    """Sequentially processes jobs from the queue"""
    print("[*] Background worker started. Ready for processing.")
    while True:
        job_id, job_data = await job_queue.get()
        jobs[job_id]["status"] = "processing"
        print(f"[*] Processing Job: {job_id}")
        
        # Execute blocking CPU-heavy task in a thread pool
        await asyncio.to_thread(run_clipper_sync, job_id, job_data)
        
        job_queue.task_done()
        print(f"[+] Finished Job: {job_id}")

@app.on_event("startup")
async def startup_event():
    # Start the worker task
    asyncio.create_task(background_worker())

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

@app.post("/process")
async def process_video(request: ProcessRequest):
    job_id = str(uuid.uuid4())
    job_data = request.dict()
    
    # Initialize per-clip status tracking for real-time frontend updates
    for clip in job_data["clips"]:
        clip["status"] = "pending"
        clip["progress"] = 0

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
        model_string = f"{request.provider}/{request.model}"
        if request.provider in ["ollama", "lm_studio"]:
            model_string = f"openai/{request.model}" # Standardize local proxies
            
        print(f"[*] Orchestrating with {model_string}...")
        
        # Fix #6: response_format={"type": "json_object"} is only valid for OpenAI and Gemini.
        # Anthropic handles JSON mode via a system prompt / its own beta header (managed by litellm
        # internally); passing this kwarg to the Anthropic endpoint raises a 400 error.
        json_providers = {"openai", "gemini"}
        extra_kwargs = {}
        if request.provider in json_providers:
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
    try:
        # For Local providers, we assume OpenAI compatibility
        url = request.base_url
        if request.provider == "ollama" and not url: url = "http://localhost:11434/v1"
        if request.provider == "lm_studio" and not url: url = "http://localhost:1234/v1"
        
        # Use LiteLLM's model_list or direct request
        # For simplicity and reliability with local providers, we'll use a direct request for those
        if request.provider in ["ollama", "lm_studio"]:
            import requests
            res = requests.get(f"{url}/models")
            data = res.json()
            return [m["id"] for m in data.get("data", [])]
        
        # For cloud providers, use LiteLLM's mapping or standard endpoints
        # Note: LiteLLM model_list can be heavy, so we'll provide standard fallbacks
        if request.provider == "openai":
            import requests
            res = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {request.api_key}"})
            return [m["id"] for m in res.json().get("data", []) if "gpt" in m["id"]]
        
        if request.provider == "gemini":
            import requests
            res = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={request.api_key}")
            return [m["name"].replace("models/", "") for m in res.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]

        if request.provider == "openrouter":
            import requests
            res = requests.get("https://openrouter.ai/api/v1/models")
            return [m["id"] for m in res.json().get("data", [])]

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
            # Persistent context to save cookies
            browser = p.chromium.launch_persistent_context(
                "tiktok_session",
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
        # Check if the transcript already exists on disk
        transcript_filename = os.path.join(OUTPUT_DIR, f"Job_{request.job_id}_full_transcript.txt")
        
        if os.path.exists(transcript_filename):
            print(f"[*] Found cached full transcript for Job {request.job_id}...")
            with open(transcript_filename, "r", encoding="utf-8") as f:
                transcript = f.read()
        else:
            # Otherwise, harvest subtitles instantly via yt-dlp
            transcript = fetch_youtube_transcript(request.video_url, request.job_id)
            if not transcript:
                import viral_clipper
                print("[*] YouTube subtitles unavailable. Activating Whisper local fallback...")
                transcript = viral_clipper.fallback_full_transcription(request.video_url, request.job_id)
                
            if not transcript:
                raise Exception("Could not retrieve subtitles from the video or local fallback. Please ensure the video has audio and is accessible.")
            
            # Save the harvested transcript
            with open(transcript_filename, "w", encoding="utf-8") as f:
                f.write(transcript)
        
        # We will run both the Twitter thread and Medium article generations in a thread pool concurrently.
        def generate_twitter():
            t_provider = request.twitter_provider
            t_model = request.twitter_model
            t_key = request.twitter_key or "local"
            t_base_url = request.twitter_base_url
            
            t_model_string = f"{t_provider}/{t_model}"
            if t_provider in ["ollama", "lm_studio"]:
                t_model_string = f"openai/{t_model}"
            
            extra_kwargs = {}
            if t_provider in ["openai", "gemini"]:
                extra_kwargs["response_format"] = {"type": "json_object"}
            
            directive_prompt = ""
            if request.directive:
                directive_prompt = f"\nCUSTOM USER DIRECTIVE: {request.directive}\nYou MUST satisfy this custom instruction."
            
            t_prompt = f"""You are an expert ghostwriter and viral growth hacker. 
Based on the following video transcript:
"{transcript}"

Generate an opinionated, highly engaging, and viral Twitter/X thread (3 to 5 tweets).{directive_prompt}

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
            response = litellm.completion(
                model=t_model_string,
                messages=[{"role": "user", "content": t_prompt}],
                api_key=t_key,
                base_url=t_base_url,
                max_tokens=2000,
                **extra_kwargs
            )
            content = response.choices[0].message.content
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                t_json = json.loads(match.group())
                tweets_filename = os.path.join(OUTPUT_DIR, f"Job_{request.job_id}_full_tweets.json")
                with open(tweets_filename, "w", encoding="utf-8") as f:
                    json.dump(t_json, f, indent=4)
                return t_json
            raise Exception("No valid JSON found in Twitter thread response")

        def generate_medium():
            m_provider = request.medium_provider
            m_model = request.medium_model
            m_key = request.medium_key or "local"
            m_base_url = request.medium_base_url
            
            m_model_string = f"{m_provider}/{m_model}"
            if m_provider in ["ollama", "lm_studio"]:
                m_model_string = f"openai/{m_model}"
            
            directive_prompt = ""
            if request.directive:
                directive_prompt = f"\nCUSTOM USER DIRECTIVE: {request.directive}\nYou MUST satisfy this custom instruction."
            
            m_prompt = f"""You are a professional tech blogger and content editor. 
Based on the following video transcript:
"{transcript}"

Write a high-quality, engaging, and detailed Medium article (300 to 600 words) discussing the core topics of the transcript.{directive_prompt}

Guidelines:
1. Create an eye-catching, SEO-optimized title at the top.
2. Use a structured hierarchy with descriptive H2/H3 subtitles.
3. Write in an opinionated, authoritative, yet approachable tone.
4. Break the content into readable paragraphs with bullet points or blockquotes for key takeaways.
5. Add a compelling conclusion.

Format the output as a beautiful Markdown document."""
            
            response = litellm.completion(
                model=m_model_string,
                messages=[{"role": "user", "content": m_prompt}],
                api_key=m_key,
                base_url=m_base_url,
                max_tokens=4000
            )
            content = response.choices[0].message.content
            medium_filename = os.path.join(OUTPUT_DIR, f"Job_{request.job_id}_full_medium.md")
            with open(medium_filename, "w", encoding="utf-8") as f:
                f.write(content)
            return content

        # Run both tasks concurrently in separate threads using to_thread
        tweets, article = await asyncio.gather(
            asyncio.to_thread(generate_twitter),
            asyncio.to_thread(generate_medium)
        )
        
        return {
            "tweets": tweets.get("tweets", []),
            "article": article
        }

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
        # Open the browser to the local server address
        Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
        uvicorn.run(app, host="127.0.0.1", port=8000)
    except Exception as e:
        with open(CRASH_LOG, "w") as f:
            f.write(f"CRASH REPORT:\n{str(e)}")
            import traceback
            f.write(traceback.format_exc())
