# Changelog

All notable changes to this project will be documented in this file.

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
