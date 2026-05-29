# fypd

**The Autonomous Content Factory & Repurposing Hub.**

fypd is an automated, high-retention video curation and repurposing suite. It transforms standard 16:9 widescreen long-form videos into highly viral 9:16 vertical shorts, while concurrently drafting opinionated, social-ready Twitter/X threads and Medium articles based on the complete video narrative.

By decoupling the heavyweight localized video processing tasks (Whisper, MediaPipe, MoviePy) from the AI orchestration layer, the system provides a robust, zero-database architecture operated entirely from an elegant, Apple-inspired glassmorphic React dashboard.

---

## 🚀 Key Features

*   **Autonomous Clip Selection:** Leverages Gemini, OpenAI, Claude, or local LLMs to analyze videos and curate high-retention vertical segments.
*   **Smart Neural Tracking:** Integrated **MediaPipe** face tracking with **Frame-Skipping (80% faster)** and EMA cinematic smoothing.
*   **Turbo Production Engine:**
    *   **Anti-Throttling Ingestion:** Downloads the full widescreen video once and performs local range extraction via `ffmpeg`.
    *   **Turbo-Transcription:** Integrated Whisper **`base` model** for high-speed, word-level audio timestamps.
    *   **Parallel Master Render:** Multi-threaded export pass utilizing all available CPU cores.
*   **Full-Video Repurposing Hub:**
    *   **Sub-Reliability Fallback:** Automatically triggers local Whisper transcription if YouTube subtitles are unavailable.
    *   **Twitter Threads & Medium Articles:** Drafts publication-ready content using Deep Reasoning AI models.
*   **Real-Time Glassmorphic Dashboard:**
    *   **Incremental Clip Delivery:** Finished clips are interactive immediately while the rest of the queue renders.
    *   **Dual Progress Tracking:** Real-time percentage bars for both ingestion and rendering phases.
*   **Auto-Distribution Pipeline:** Direct programmatic uploads to **YouTube Shorts, Instagram Reels, Facebook Reels, and TikTok**.
*   **Global CLI Access:** The Tauri desktop installer automatically registers the `fypd` command to your system PATH and installs locally, bypassing the need for administrator privileges.
*   **Over-The-Air (OTA) Updates:** The built-in Tauri updater securely pulls patches from GitHub Releases, utilizing Ed25519 cryptographic signatures to guarantee zero-tamper background updates.

---

## 📚 Documentation
- **[GEMINI.md](GEMINI.md):** Core architecture notes, technology stack, and essential developer conventions.
- **[PRD.md](PRD.md):** Product Requirements Document detailing scope, roadmap, and core user flows.
- **[architecture.md](architecture.md), [design.md](design.md) & [UI_design.md](UI_design.md):** Detailed system architecture and visual/UI design specifications.
- **[roadmap.md](roadmap.md) & [changelog.md](changelog.md):** Upcoming features and historical updates.

---

## 🛠️ Installation & Setup

### 1. Prerequisites
Before running the suite, make sure you have installed:
*   **Python 3.10+**
*   **FFmpeg** (must be available in your system `PATH`)
*   **ImageMagick** (required for MoviePy text rendering)

### 2. Standalone Build Setup
Clone the repository and install the dependencies:
```bash
# Clone the repository
git clone https://github.com/doctorrajvanshi/fypd-OpenOpus.git
cd fypd-OpenOpus

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright dependencies (for TikTok automatic session setups)
playwright install chromium
```

*Note: To build the standalone Desktop App, we use a fully automated GitHub Actions pipeline with Tauri. Just push a `v*` tag to trigger the cloud release.*

### 3. Configuration & Environment Variables
Copy the `.env.example` file to `.env` and set the path to your ImageMagick executable:
```bash
cp .env.example .env
```
Open `.env` and configure:
```env
IMAGEMAGICK_BINARY=C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe
```

---

## 💻 Usage

Start the unified server using the main runner:
```bash
python app_server.py
```
1.  The browser will automatically launch to `http://127.0.0.1:8000`.
2.  Open **System Configuration** to set your API Keys (Gemini, OpenAI, Pexels) and select your **Twitter** and **Medium** writing models (supports local Ollama/LM Studio proxies!).
3.  Paste a YouTube URL and click **Orchestrate**. 
4.  Jobs are queued sequentially in the background worker queue. Sit back and watch your Content Factory render widescreen streams into short clips, tweets, and articles!

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
