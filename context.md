# Developer Context

This document provides technical context for developers working on the fypd codebase.

## Key Files
- `viral_clipper.py`: The main entry point. Contains the rendering pipeline and typography logic.
- `PRD.md`: The original requirements document. Reference this for feature intent.
- `clips.json`: The runtime configuration. This file is consumed by the Python engine.

## Implementation Details

### Typography Offset
The text is offset by `+4px` on both axes to create a "Premium" drop shadow. This is implemented in `create_kinetic_caption` by layering two `TextClip` objects.

### Audio Normalization
The engine downsamples audio to `16kHz` for Whisper. This is a critical "guardrail" to prevent `MoviePy` from crashing during FPS conversion on certain hardware configurations.

### ImageMagick Path
**Warning:** The path to `magick.exe` is currently hardcoded in `viral_clipper.py`. In a production environment, this should be moved to an environment variable or a configuration file.

### Coordinate Mapping
Reframing uses a simple coordinate shift based on `target_w` (calculated as `9/16 * height`).
- `Center`: `(orig_w - target_w) // 2`
- `Left`: `0`
- `Right`: `orig_w - target_w`
