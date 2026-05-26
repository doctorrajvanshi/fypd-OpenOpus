# fypd - GEMINI.md

## Project Overview
fypd (formerly Viral Clipper) is an automated video curation and reframing pipeline designed to extract highly viral, 9:16 vertical shorts from long-form 16:9 widescreen video files.

### Core Architecture
- **Orchestration:** A premium, Apple-inspired React dashboard (built with Vite + Tailwind + Framer Motion) orchestrates the Gemini API to analyze videos and manage the autonomous production queue.
- **Backend (FastAPI):** `app_server.py` manages a sequential background task queue, secure on-demand tunneling, and serves the React UI.
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

### Key Coding Conventions
- **Task Queue:** `app_server.py` uses `asyncio.Queue` to process video renders one-by-one.
- **Style Templates:** Visual themes are stored in `STYLE_TEMPLATES` and define fonts, animations, and shadows.
- **Audio Ducking:** Background music is automatically ducked to ~12% volume when combined with dialogue.
- **Kinetic Typography:** Captions use elastic bounce or fade animations depending on the selected style.

## Troubleshooting
- **Missing ImageMagick:** Ensure the path in `viral_clipper.py` matches your local installation.
- **MoviePy Audio Errors:** The script uses a 16kHz downsampling patch to avoid common FPS mismatch crashes.
- **yt-dlp Failures:** 
  - Keep `yt-dlp` updated to handle changes in YouTube's streaming protocols.
  - **Perceived Freezes during Download:** Because `yt-dlp` uses `ffmpeg` to seek and download precise time ranges over heavily throttled YouTube connections, downloads may appear "frozen" at 0 bytes for several minutes. Do not abort the process—the console will output progress. The JavaScript runtime warning (`deno`/`node`) can be safely ignored as the system falls back to alternative APIs.
