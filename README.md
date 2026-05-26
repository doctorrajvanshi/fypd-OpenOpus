# fypd

**The Autonomous Content Factory & Repurposing Hub.**

fypd is an automated, high-retention video curation and repurposing suite. It transforms standard 16:9 widescreen long-form videos into highly viral 9:16 vertical shorts, while concurrently drafting opinionated, social-ready Twitter/X threads and Medium articles based on the complete video narrative.

By decoupling the heavyweight localized video processing tasks (Whisper, MediaPipe, MoviePy) from the AI orchestration layer, the system provides a robust, zero-database architecture operated entirely from an elegant, Apple-inspired glassmorphic React dashboard.

---

## 🚀 Key Features

*   **Autonomous Clip Selection:** Leverages Gemini, OpenAI, Claude, or local LLMs to analyze videos and curate high-retention vertical segments.
*   **Neural Face Tracking:** Integrated **Google MediaPipe** speaker following for smooth, active coordinate panning.
*   **Audio-Aware Splicing:** Snaps transitions and camera pans to natural dialogue silence limits using audio Root-Mean-Square (RMS) volume envelopes and Content-Aware cut boundaries (**PySceneDetect**).
*   **Premium Retention Typography:** Burns stylized, drop-shadowed kinetic subtitles using layered MoviePy text composition (supports Hormozi, Neon, and Minimalist themes).
*   **Automatic Stock Foot Overlays:** Semi-automatically fetches and overlays relevant portrait B-roll using the **Pexels API** based on semantic keywords.
*   **Full-Video Repurposing Hub:**
    *   **Twitter Threads:** Formulates cohesive, viral X threads under 280 characters using specialized snappy copywriting models.
    *   **Medium Articles:** Drafts publication-ready editorial articles with clean Markdown headings, bullet points, and deep reasoning summaries.
    *   **Interactive AI Scribes:** Input natural language directives (e.g. *"make it more sarcastic"*) to dynamically regenerate text in real time.
*   **Job-Level Dashboard Grouping:** Collates multiple vertical curations cleanly under widescreen parent **Job Panels** on a single grid.
*   **Auto-Distribution Pipeline:** Direct programmatic uploads to **YouTube Shorts, Instagram Reels, Facebook Reels, and TikTok**.

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
git clone https://github.com/your-username/fypd.git
cd fypd

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright dependencies (for TikTok automatic session setups)
playwright install chromium
```

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
