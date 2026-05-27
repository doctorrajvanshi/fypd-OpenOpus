# Changelog

All notable changes to this project will be documented in this file.

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
