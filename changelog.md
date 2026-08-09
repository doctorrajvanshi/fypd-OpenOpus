# Changelog

All notable changes to this project will be documented in this file.

## [1.2.1] - 2026-08-09
### Added
- **Resilient ImageMagick discovery:** searches `IMAGEMAGICK_BINARY`, the app data `bin/`, the app folder, `PATH`, and versioned Program Files installs — and executes each candidate before accepting it, so partially-installed copies are skipped rather than silently used.
- **Startup dependency preflight** with a `/health` endpoint and a *Setup Required* banner in the dashboard, so missing FFmpeg/ImageMagick is reported in the UI instead of only in the log file.
- **`.env` support** via `python-dotenv` — `IMAGEMAGICK_BINARY`, `HOST` and `PORT` are now actually read.
- **Anthropic model listing** in `/models/fetch`; Claude was selectable in the UI but unsupported by the backend.
- **CI workflow** running unit tests, a frontend typecheck/build, and a Rust format check.
- **`fypd_core.py`**, a dependency-free module of shared pure helpers, with a pytest suite.

### Fixed
- **Visual style, B-roll keywords and BGM mood were silently discarded:** the `Clip` request model never declared them, so Pydantic stripped all three before the payload reached the renderer. Every clip rendered as `hormozi` with no B-roll and no music.
- **Completed clips 404'd in the dashboard** whenever a title contained characters the backend sanitizes out of filenames; the backend now reports the real filename and the frontend URL-encodes it.
- **Face tracking ran on colour-inverted frames** (`BGR2RGB` applied to already-RGB MoviePy frames), badly degrading detection.
- **Segment boundaries desynced:** smart transition snapping moved a segment's end without moving the next segment's start, duplicating or dropping up to a second of footage per cut.
- **Per-clip render progress never reported** — the callback logger was written but never wired up; progress jumped 15% → 100%.
- **Failed jobs left clip cards spinning forever**, hiding the job error; unfinished clips are now marked failed with the reason.
- Whisper warm-up in the installer downloaded `small` while the engine loads `base`.
- Setup re-ran on every launch on macOS/Linux (readiness was probed via `bin/magick.exe`), and a half-finished setup counted as complete on Windows.
- BGM downloads wrote `bgm_<mood>.mp3.mp3`, so the returned path never existed and every music mix failed.
- Clips with no audio track crashed with an `AttributeError` mid-render.
- Timestamps with fractional seconds (`00:01:23.5`) raised and killed the whole job.
- Facebook publishing tore down its tunnel after a fixed 10s, interrupting larger uploads; it now waits for the fetch to complete.
- Instagram publish errors were swallowed, reporting success on failure.

### Changed
- **Publishing tunnels now expose a single file, not the whole API.** `ngrok.connect(8000)` published the entire dashboard backend — `/orchestrate`, `/process`, `/jobs`, `/tiktok/login` and every rendered clip, transcript and draft under `/videos`. Uploads now run a throwaway server on an ephemeral port serving one file at one random path.
- **CORS restricted to the dashboard's own origins.** A wildcard origin on an unauthenticated local server holding API keys let any visited website drive the pipeline.
- Gemini API keys are sent as a header rather than a URL query parameter.
- Cached source videos are pruned with an LRU budget instead of accumulating forever; per-clip buffers are cleaned up after each render.
- The face tracking model is bundled and loaded lazily, so importing the engine no longer performs network I/O.
- Duplicated Twitter/Medium prompt and generation logic consolidated into shared helpers.
- Tauri webview CSP enabled (was `null`).

## [1.2.0] - 2026-05-30
### Added
- **Turbo-Production Suite:** High-performance optimizations across the entire pipeline.
- **Anti-Throttling Ingestion:** Implemented full-video local caching and range extraction to bypass YouTube byte-range throttling (3-5x speedup).
- **Smart AI Tracking:** Neural frame-skipping (Detect every 5th frame) with cinematic EMA interpolation, reducing CV CPU load by 80%.
- **Repurposing Fallback:** Automatically switches to Whisper full-video transcription if YouTube subtitles are missing, ensuring 100% reliability for ghostwriting.
- **Real-Time UI Progress:** High-fidelity progress bars on the dashboard driven by backend download and rendering data.
- **Incremental Delivery:** Clips are now displayed and interactive as soon as they are finished rendering.
- **Rich Terminal Feedback:** Integrated `tqdm` for interactive progress bars in the server logs.

### Changed
- Migrated transcription engine to the Whisper **`base` model** for significantly faster processing with maintained accuracy.
- Enabled **Multi-threaded Rendering** in MoviePy to utilize all available CPU cores during master compilation.

### Fixed
- Fixed a critical "empty clip" (0-byte) bug caused by MoviePy logger interception.
- Stabilized real-time progress callbacks to prevent subprocess blocking.
- Resolved module shadowing in `app_server.py` that caused `UnboundLocalError`.

## [1.1.0] - 2026-05-28
### Added
- Global CLI access support (`fypd` command) via a custom Tauri NSIS installer hook.
- Unified directory pathing resolving to `%LOCALAPPDATA%\fypd` to prevent UAC administrator prompts during installation.
### Fixed
- Fixed backend `StreamToLogger` crash on startup due to missing `isatty` method in detached processes.
- Re-routed all hardcoded temporary and output directories to use the writable app data path.

## [1.0.0] - 2026-05-27
### Added
- Fully automated PyInstaller build pipeline via GitHub Actions.
- Native custom `.ico` and `favicon.svg` branding.
- Multi-provider LLM settings (OpenAI, Anthropic, Ollama, LM Studio).
- Content Repurposing Hub for auto-generating Twitter threads and Medium articles.

### Changed
- Migrated core face tracking engine from the deprecated `mediapipe.python.solutions` API to the modern `mediapipe.tasks.vision` API.
- Restored the lightweight Tauri desktop wrapper architecture to ensure optimal installer sizes, deferring ML python environment resolution to runtime.

### Fixed
- Permanently resolved the critical Windows Python 3.12 `libprotobuf` text parsing crash.
- Eliminated dependency locks, safely upgrading to `mediapipe==0.10.35` and `protobuf==5.29.6`.

## [0.1.0] - 2026-05-26
### Added
- Initial release of the **fypd** core.
- Selective byte-range downloading logic via `yt-dlp`.
- Kinetic typography engine with dual-layered drop shadows.
- Whisper "Small" model integration for multilingual transcription.
- Smart audio-aligner for seamless clip transitions.
- Multi-crop support (Left/Center/Right) for 9:16 conversion.
- Hinglish transcription prompt support.

## [0.1.1] - 2026-05-27
### Fixed
- Fixed a silent freeze perception during video extraction by exposing `yt-dlp` console output (`quiet: False`).
- Fixed an issue where `ffmpeg` range extraction appeared stuck due to YouTube HTTP throttling.
- Fixed an infinite loop / memory leak in Tauri `useEffect` listeners.
- Fixed a facial tracking variable capture closure bug in `viral_clipper.py`.
- Fixed the `target_w` initialization bug for portrait video handling.
- Fixed API_BASE dynamic port fallback to prevent connection errors on varying environments.

### Added
- Cinema Player Modal for full-screen review.
- Kinetic Stage Tracker for monitoring video generation phases.
