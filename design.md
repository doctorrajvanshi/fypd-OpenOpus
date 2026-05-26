# Design Principles

fypd is built with one goal: **Retention**. Every technical decision is geared toward keeping the viewer's eyes on the screen.

## 1. Kinetic Typography
- **Pacing:** Subtitles are capped at 2 words per frame. This creates a "fast" feel even if the speaker is talking slowly.
- **Visuals:** Uses a "Pop" animation (elastic bounce) on every new phrase to grab attention.
- **Readability:** Neon yellow text on matte black shadow ensures visibility across any background.

## 2. Reframing & Composition
- **Rule of Thirds:** Crops are calculated to keep subjects centered or balanced within the narrow 9:16 viewport.
- **Dynamic Zoom:** "Punch-in" zooms are used to emphasize key points or hide awkward transitions.

## 3. Seamless Transitions
- **Audio-Sync:** Cuts never happen mid-word. The engine analyzes the audio waveform to find silences (local RMS minima) to place the cut.
- **Visual Continuity:** Transitions are kept minimal to avoid distracting from the content.

## 4. Performance Design
- **Lazy Fetching:** No need to download 2GB of video to get a 30-second clip. The system only pulls what it needs.
- **Caching:** Local buffer files are cached to prevent redundant downloads during re-runs.
