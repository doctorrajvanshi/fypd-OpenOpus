# fypd - GEMINI.md

## Project Overview
fypd (formerly Viral Clipper) is an automated video curation and reframing pipeline designed to extract highly viral, 9:16 vertical shorts from long-form 16:9 widescreen video files.

### Core Architecture
- **Orchestration:** A premium, Apple-inspired React dashboard (built with Vite + Tailwind + Framer Motion) orchestrates the Gemini API to analyze videos and manage the autonomous production queue.
- **Backend (FastAPI & Tauri):** `app_server.py` manages a sequential background task queue and secure on-demand tunneling. The Tauri desktop window securely injects the `FYPD_DATA_DIR` environment variable to ensure the Python backend seamlessly writes to the user's `%LOCALAPPDATA%` without tripping Windows Administrator permissions.
- **Python Core (`viral_clipper.py`):** A localized kinetic editing engine that processes structural JSON payloads with Computer Vision (CV) and professional rendering templates.
- **Key Technologies:**
  - **Gemini API:** Used for intelligent clip selection, captioning (with emojis), and mood/keyword generation.
  - **MediaPipe:** Powers dynamic face tracking for active speaker following.
  - **PySceneDetect:** Automates visual cut alignment.
  - **Pexels API:** Fetches high-quality portrait B-roll.
  - **yt-dlp:** Handles video fetching and royalty-free background music (BGM) sourcing.
  - **MoviePy & ImageMagick:** Orchestrate complex video compositing, audio mixing (ducking), and multi-style typography.

## System Dependencies & Setup
The project requires several system-level dependencies:
- **Python 3.10+**
- **FFmpeg:** Must be installed and available in the system PATH.
- **ImageMagick:** Required for `TextClip`.
- **Python Packages:**
  ```bash
  pip install -r requirements.txt
  playwright install chromium
  ```

### Social Platform Setup
- **YouTube:** Place a `client_secrets.json` file (Desktop OAuth2 type) in the root directory.
- **Instagram & Facebook:** Requires a Meta Graph API Token and your IG/FB Page IDs. Facebook Reels are published directly to Pages.
- **TikTok:** No API key needed, but you must click "Login to TikTok" in the dashboard once to save your session.

## Development & Usage
The application is now a unified suite.

### Running the Application
1. Start the server:
   ```bash
   python app_server.py
   ```
2. The browser will automatically open to `http://127.0.0.1:8000`.
3. Enter your API Keys (Gemini & Pexels) in the settings.
4. Select a **Visual Style** (Hormozi, Minimalist, Neon).
5. Provide a single YouTube URL or toggle **Batch Mode** to ingest multiple URLs at once.
6. Click "Orchestrate" to begin. Jobs are queued sequentially to manage system resources.

### Global CLI Installation
- The Tauri application utilizes a custom NSIS script (`nsis/addpath.nsh`) to automatically append the installation directory to the user's PATH.
- It is configured with `"installMode": "currentUser"`, meaning it can be installed on any Windows machine securely without requiring an Administrator password, writing directly to the user's AppData directory.

### Key Coding Conventions
- **Task Queue:** `app_server.py` uses `asyncio.Queue` to process video renders one-by-one.
- **Anti-Throttling:** Use `viral_clipper.download_selective_range` to download the full video once to a local cache. This avoids YouTube fragmentation throttling.
- **AI Tracking:** MediaPipe detection uses **Smart-Tracking** (every 5th frame) to maintain cinematic focus while saving 80% CPU.
- **Performance Core:** 
    - **Whisper:** Standardize on the `base` model for high-speed transcription.
    - **MoviePy:** Always pass `threads=os.cpu_count()` to `write_videofile` to maximize master compilation throughput.
- **Progress Reporting:** Use the `MoviePyCallbackLogger` class for non-intrusive progress updates to the dashboard.

## Troubleshooting
- **Missing ImageMagick:** Ensure the path in `viral_clipper.py` matches your local installation.
- **MoviePy Audio Errors:** The script uses a 16kHz downsampling patch to avoid common FPS mismatch crashes.
- **yt-dlp Stability:** The new interactive `tqdm` bars provide real-time feedback during the ingestion phase. If a download appears stuck, check the network layer; however, the new caching system significantly reduces ingestion time for multi-clip batches.
