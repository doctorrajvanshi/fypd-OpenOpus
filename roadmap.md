# Project Roadmap

The vision for fypd is to provide the world's most advanced autonomous "factory" for high-retention vertical content.

## Phase 1: Core Engine (Completed)
- [x] Basic 9:16 reframing (Left, Center, Right).
- [x] Kinetic typography with dual-layered drop shadows.
- [x] Selective byte-range downloading (macro-buffer protocol).
- [x] Audio-aware cut alignment.

## Phase 2: Enhanced Intelligence (Completed)
- [x] **Multi-Face Tracking:** Automatically shift the crop window to follow the active speaker via MediaPipe.
- [x] **Scene Change Detection:** Automatic cutting based on visual shifts via PySceneDetect.
- [x] **B-Roll Integration:** Automatically fetch and overlay relevant stock footage via Pexels API.

## Phase 3: Visual Polish (Completed)
- [x] **Custom Style Templates:** Support for "Hormozi", "Minimalist", and "Neon" visual themes.
- [x] **Background Music:** Automatic fetching and syncing of royalty-free background music via `yt-dlp`.
- [x] **Auto-Emojis:** Semantic insertion of emojis into captions based on segment context.

## Phase 4: Platform & Scaling (Completed)
- [x] **Premium React Dashboard:** A high-end, Apple-inspired interface built with Vite + Tailwind + Framer Motion.
- [x] **Batch Processing:** Sequential task queue and multi-URL ingestion UI for overnight content creation.
- [x] **Direct Social Upload:** Integrated automated publishing for YouTube Shorts, Instagram Reels, Facebook Reels (via On-Demand Tunneling), and TikTok (via Browser Automation).

## Phase 8: Universal LLM Integration (Completed)
- [x] **Universal Orchestrator:** Backend routing via `litellm` to support OpenAI, Anthropic, OpenRouter, Ollama, and LM Studio.
- **Dynamic Model Fetching:** UI dynamically queries provider endpoints to populate available model lists.
- **Robust Extraction:** Regex-based JSON parsing to handle erratic markdown outputs from local LLaMA/Mistral models.

