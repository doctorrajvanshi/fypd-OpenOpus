import os
import json
import sys
import glob as globlib
import shutil
import numpy as np
import subprocess
from tqdm import tqdm

from fypd_core import (
    STYLE_TEMPLATES,
    WHISPER_MODEL,
    elastic_bounce_transform,
    extract_video_id,
    group_words_into_phrases,
    sanitize_filename,
    timestamp_to_seconds,
)

# ==============================================================================
# 1. SYSTEM PATH RESOLUTION & EXTERNAL BINARY INTEGRITY CHECKS
# ==============================================================================
class DependencyError(RuntimeError):
    """Raised when a required external binary is missing or refuses to run.

    These are surfaced all the way to the dashboard instead of being swallowed
    into the log file, because they are always user-fixable setup problems.
    """

# Keep spawned console windows hidden on Windows so probing never flashes a terminal.
_NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_data_dir():
    """Root of the writable fypd data directory (no side effects)."""
    return os.environ.get("FYPD_DATA_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "fypd"
    )

def get_data_path(*parts):
    """Resolve a writable path under the fypd AppData directory.
    Reads FYPD_DATA_DIR (set by Tauri) with a local fallback for dev mode."""
    path = os.path.join(get_data_dir(), *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

_MAGICK_NAMES = ("magick.exe", "magick") if os.name == "nt" else ("magick", "convert")

def _magick_works(candidate):
    """True only if the candidate path exists AND actually executes.

    Existence alone is not enough: a half-extracted install, a copy missing its
    sibling DLLs, or a stale registry path all pass os.path.exists() and then
    fail at the first TextClip render with an unreadable MoviePy traceback.
    """
    if not candidate or not os.path.isfile(candidate):
        return False
    try:
        result = subprocess.run(
            [candidate, "-version"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=20, **_NO_WINDOW
        )
    except Exception:
        return False
    return result.returncode == 0 and b"ImageMagick" in result.stdout

def _magick_candidates():
    """Yield every plausible ImageMagick location, best guess first."""
    # 1. An explicit override always wins (.env / system environment).
    yield os.environ.get("IMAGEMAGICK_BINARY")

    # 2. The copy Tauri extracts into the user's data directory at first launch.
    # 3. The copy sitting next to the running script (Tauri resource dir / repo).
    # 4. The working directory, for `python viral_clipper.py` from a checkout.
    for base in (get_data_dir(), os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        for name in _MAGICK_NAMES:
            yield os.path.join(base, "bin", name)

    # 5. Anything already on PATH (Linux/macOS package installs, choco, scoop).
    for name in _MAGICK_NAMES:
        yield shutil.which(name)

    # 6. Versioned Windows installs, newest first. The old hardcoded fallback
    #    pinned one exact version string and broke on every other release.
    if os.name == "nt":
        roots = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ]
        for root in roots:
            if not root:
                continue
            for found in sorted(globlib.glob(os.path.join(root, "ImageMagick-*", "magick.exe")), reverse=True):
                yield found

def resolve_imagemagick():
    """Locate a working ImageMagick and export IMAGEMAGICK_BINARY for MoviePy.

    MoviePy reads this variable when moviepy.config is first imported, so this
    must run before the moviepy import below. Returns the resolved path, or
    None when nothing usable was found.
    """
    seen = set()
    for candidate in _magick_candidates():
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if _magick_works(candidate):
            os.environ["IMAGEMAGICK_BINARY"] = candidate
            print(f"[+] ImageMagick resolved: {candidate}")
            return candidate

    # Leave the variable unset rather than pointing MoviePy at a path we know is
    # broken; preflight_dependencies() turns this into a visible error.
    os.environ.pop("IMAGEMAGICK_BINARY", None)
    print("[-] ImageMagick could not be located. Caption rendering will fail.")
    print(f"[-] Searched: {', '.join(sorted(seen))}")
    return None

# Ensure the local 'bin' directories containing ffmpeg, ffprobe, and magick are on PATH.
for _bin_dir in (os.path.join(get_data_dir(), "bin"), get_resource_path("bin")):
    if os.path.isdir(_bin_dir) and _bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _bin_dir + os.pathsep + os.environ.get("PATH", "")

IMAGEMAGICK_PATH = resolve_imagemagick()

try:
    import yt_dlp
    import whisper
    import requests
    import mediapipe as mp
    from proglog import ProgressBarLogger
    from scenedetect import detect, ContentDetector
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, afx
except ImportError as e:
    print(f"[-] Missing core dependency library: {e}")
    print("[*] Please run: pip install -r requirements.txt")
    sys.exit(1)

def preflight_dependencies():
    """Verify the external toolchain before a job starts consuming time.

    Raises DependencyError with an actionable message so the dashboard can show
    the real cause instead of a clip card spinning forever.
    """
    if not shutil.which("ffmpeg"):
        raise DependencyError(
            "FFmpeg was not found. Install FFmpeg and make sure it is on your system PATH, "
            "then restart fypd."
        )

    # MoviePy reads IMAGEMAGICK_BINARY once, when moviepy.config is imported.
    # If it was missing then, re-resolving now cannot repair this process — the
    # user has to restart, which is the case behind "I installed ImageMagick and
    # it still doesn't work".
    resolved_late = IMAGEMAGICK_PATH is None
    magick = IMAGEMAGICK_PATH or resolve_imagemagick()
    if not magick:
        raise DependencyError(
            "ImageMagick was not found, so animated captions cannot be rendered. "
            "Install ImageMagick (https://imagemagick.org/script/download.php) and either add it "
            "to your PATH or set IMAGEMAGICK_BINARY in your .env file to the full path of "
            "magick.exe, then restart fypd."
        )
    if resolved_late:
        raise DependencyError(
            f"ImageMagick was found at '{magick}', but it was not available when fypd started. "
            "Restart fypd to pick it up."
        )

    # A found-and-runnable binary can still fail to render text when the delegate
    # or font configuration is broken, so smoke-test an actual TextClip.
    try:
        probe = TextClip("fypd", fontsize=24, color="white")
        probe.close()
    except Exception as e:
        raise DependencyError(
            f"ImageMagick was found at '{magick}' but could not render text ({e}). "
            "This usually means the installation is incomplete — reinstall ImageMagick and "
            "make sure the 'Install legacy utilities' option is enabled."
        )

# ==============================================================================
# 2. PREMIUM RETENTION TYPOGRAPHY & CV SETUP
# ==============================================================================
# Initialize MediaPipe Face Detection (Tasks API)
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import urllib.request

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
MODEL_NAME = "blaze_face_short_range.tflite"

_face_detector = None

def get_face_detector():
    """Lazily build the MediaPipe detector.

    Kept out of module scope so importing this module never performs network
    I/O — that made the whole backend unimportable offline, and it ran even for
    jobs that use no face tracking at all.
    """
    global _face_detector
    if _face_detector is not None:
        return _face_detector

    # Prefer the model shipped alongside the app before reaching for the network.
    bundled = get_resource_path(MODEL_NAME)
    model_path = get_data_path("models", MODEL_NAME)
    if not os.path.exists(model_path):
        if os.path.exists(bundled):
            shutil.copyfile(bundled, model_path)
        else:
            print("[*] Downloading MediaPipe face tracking model asset...")
            try:
                urllib.request.urlretrieve(MODEL_URL, model_path)
            except Exception as e:
                raise DependencyError(
                    f"Could not download the face tracking model ({e}). Check your internet "
                    "connection, or switch the clip's crop mode away from 'track'."
                )

    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.5)
    _face_detector = vision.FaceDetector.create_from_options(options)
    return _face_detector

class MultiFaceTracker:
    """Handles frame-by-frame face detection with smart frame-skipping and interpolation"""
    def __init__(self, target_w, orig_w):
        self.target_w = target_w
        self.orig_w = orig_w
        self.last_center_x = orig_w // 2
        self.smoothing = 0.15 # Low-pass filter coefficient for cinematic panning
        self.frame_count = 0
        self.skip_frames = 5 # Only detect every 5th frame
        self.target_x = orig_w // 2

    def get_crop_window(self, frame):
        # Only run neural detection every N frames to save CPU
        if self.frame_count % self.skip_frames == 0:
            # MoviePy already hands us RGB frames. The previous BGR2RGB call
            # swapped the red and blue channels, so the detector was scoring
            # colour-inverted faces and missing them far more often than it should.
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame))
            results = get_face_detector().detect(mp_image)
            
            if results.detections:
                detection = results.detections[0]
                bbox = detection.bounding_box
                self.target_x = int(bbox.origin_x + (bbox.width / 2))
        
        self.frame_count += 1
            
        # Apply Exponential Moving Average (EMA) smoothing for fluid movement
        # This naturally interpolates between the skipped frames
        smoothed_center_x = int(self.last_center_x * (1 - self.smoothing) + self.target_x * self.smoothing)
        self.last_center_x = smoothed_center_x
        
        # Calculate x1, x2 while keeping within bounds
        x1 = smoothed_center_x - (self.target_w // 2)
        if x1 < 0: x1 = 0
        if x1 + self.target_w > self.orig_w: x1 = self.orig_w - self.target_w
        
        return x1, x1 + self.target_w

# ==============================================================================
# 3. KINETIC ANIMATION INTERPOLATION INTERNALS
# ==============================================================================
def make_kinetic_slide_up(base_y, offset_y=0):
    """Generates a dynamic slide-up position translation over the first 100ms"""
    return lambda t: ('center', int((base_y + 20 * (1.0 - (t / 0.10))) + offset_y) if t < 0.10 else int(base_y + offset_y))

def create_kinetic_caption(text_string, start_time, duration, max_width, target_y, style_config):
    """Compiles clean, synchronized styled text objects with requested animations"""
    anim_type = style_config.get("ANIMATION", "bounce")
    shadow_offset = style_config.get("SHADOW_OFFSET", 4)
    
    # 1. Base Layer Creation
    def get_base_clip(color, offset_y=0):
        clip = TextClip(text_string, font=style_config["FONT"], fontsize=style_config["FONT_SIZE"], 
                        color=color, method='caption', size=(max_width, None))
        clip = clip.set_start(start_time).set_duration(duration)
        
        # Apply Animations
        if anim_type == "bounce":
            clip = clip.resize(elastic_bounce_transform).set_position(make_kinetic_slide_up(target_y, offset_y=offset_y))
        else: # minimalist / fade
            clip = clip.set_position(('center', target_y + offset_y)).crossfadein(0.2)
            
        return clip

    layers = []
    # Background Shadow Layer (if applicable)
    if style_config["SHADOW_COLOR"] != "transparent":
        layers.append(get_base_clip(style_config["SHADOW_COLOR"], offset_y=shadow_offset))
    
    # Primary Visual Face Layer
    layers.append(get_base_clip(style_config["TEXT_COLOR"]))
    
    return layers

# ==============================================================================
# 4. INTELLIGENT AUDIO-VISUAL TRANSITION ALIGNER
# ==============================================================================
def find_visual_cut_points(video_path):
    """Detects hard visual cuts in the video stream using Content-Aware detection"""
    try:
        print(f"[*] Analyzing visual scene boundaries for {video_path}...")
        scene_list = detect(video_path, ContentDetector())
        return [scene[0].get_seconds() for scene in scene_list] + [scene[1].get_seconds() for scene in scene_list]
    except Exception as e:
        print(f"[-] Visual scene detection failed: {e}")
        return []

def find_smart_transition_point(sub_audio_clip, target_rel_time, visual_cuts=[], search_window=1.2):
    """Parses local audio frame volumes and visual boundaries to shift edits into organic pauses"""
    # 1. Prioritize Visual Cuts (Snap if within window)
    for cut in visual_cuts:
        if abs(cut - target_rel_time) < 0.4: # Tight threshold for visual snapping
            return cut
            
    # 2. Fallback to Audio RMS Analysis
    try:
        fps = 22050  # Lightweight downsampled frequency mapping for instant indexing
        sample_start = int(max(0, target_rel_time - 0.2) * fps)
        sample_end = int(min(sub_audio_clip.duration, target_rel_time + search_window) * fps)
        
        audio_frames = sub_audio_clip.to_soundarray(fps=fps)[sample_start:sample_end]
        if len(audio_frames) == 0:
            return target_rel_time
            
        energy = np.sqrt(np.mean(audio_frames**2, axis=1))
        min_energy_idx = np.argmin(energy)
        return (sample_start + min_energy_idx) / fps
    except Exception:
        return target_rel_time

# ==============================================================================
# 5. AUTOMATED B-ROLL & BGM FETCHING (EXTERNAL APIS)
# ==============================================================================
SOURCE_CACHE_LIMIT_BYTES = 20 * 1024 * 1024 * 1024  # 20 GB of cached source videos

def prune_source_cache(keep_path=None, limit_bytes=SOURCE_CACHE_LIMIT_BYTES):
    """Evict least-recently-used cached source videos above the size budget.

    Full source downloads were previously kept forever, so the temp directory
    grew without bound across jobs.
    """
    try:
        cached = []
        for path in globlib.glob(os.path.join(get_data_dir(), "temp", "full_source_*.mp4")):
            if keep_path and os.path.abspath(path) == os.path.abspath(keep_path):
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            cached.append((stat.st_atime, stat.st_size, path))

        total = sum(size for _, size, _ in cached)
        if keep_path and os.path.exists(keep_path):
            total += os.path.getsize(keep_path)

        for _, size, path in sorted(cached):
            if total <= limit_bytes:
                break
            try:
                os.remove(path)
                total -= size
                print(f"[*] Evicted cached source video: {os.path.basename(path)}")
            except OSError:
                pass
    except Exception as e:
        print(f"[-] Source cache pruning skipped: {e}")

def download_selective_range(url, output_path, start_sec, end_sec, on_progress=None):
    """Downloads the full video if not present, then extracts the requested range locally."""
    if os.path.exists(output_path):
        return

    video_id = extract_video_id(url)
    full_video_path = get_data_path("temp", f"full_source_{video_id}.mp4")

    if not os.path.exists(full_video_path):
        print(f"[*] Downloading full video: {url}")
        bin_dir = get_resource_path("bin")
        
        # tqdm needs to be visible in the terminal
        pbar = tqdm(total=100, desc="Downloading Video", unit="%", leave=True, dynamic_ncols=True)
        def progress_hook(d):
            if d['status'] == 'downloading':
                # Use total_bytes and downloaded_bytes for more accurate progress
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                if total:
                    p = (downloaded / total) * 100
                    p_rounded = round(p, 1)
                    pbar.n = p_rounded
                    pbar.refresh()
                    # Pipe to UI callback (scale 0-100% to represent the Ingesting phase)
                    if on_progress:
                        on_progress(p_rounded)
            elif d['status'] == 'finished':
                pbar.n = 100
                pbar.refresh()
                pbar.close()
                if on_progress:
                    on_progress(100)

        ydl_opts = {
            'format': 'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': full_video_path,
            'noplaylist': True,
            'ffmpeg_location': bin_dir if os.path.exists(bin_dir) else None,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook]
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    prune_source_cache(keep_path=full_video_path)

    if end_sec <= start_sec:
        raise ValueError(
            f"Clip end time ({end_sec}s) must be after its start time ({start_sec}s)."
        )

    # Extract range locally using ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", full_video_path,
        "-t", str(end_sec - start_sec),
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    # Surface ffmpeg's own diagnostics; discarding stderr turned every failure
    # here into a bare "returned non-zero exit status 1".
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **_NO_WINDOW)
    if result.returncode != 0:
        tail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
        raise RuntimeError("FFmpeg range extraction failed:\n" + "\n".join(tail))

def fetch_bgm_by_mood(mood):
    """Searches and downloads a royalty-free audio track matching the mood"""
    safe_mood = sanitize_filename(str(mood))
    search_query = f"ytsearch1:royalty free {safe_mood} music for youtube shorts"
    # yt-dlp appends the container extension to outtmpl, and FFmpegExtractAudio
    # then rewrites it to .mp3. Passing a template that already ends in .mp3
    # produced 'bgm_lofi.mp3.mp3' on disk, so the returned path never existed
    # and every BGM mix silently failed.
    output_stem = get_data_path("cache", f"bgm_{safe_mood}")
    output_path = f"{output_stem}.mp3"

    if os.path.exists(output_path):
        return output_path

    print(f"[*] Sourcing mood-appropriate audio for '{safe_mood}'...")

    bin_dir = get_resource_path("bin")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{output_stem}.%(ext)s",
        'noplaylist': True,
        'ffmpeg_location': bin_dir if os.path.exists(bin_dir) else None,
        'quiet': False,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([search_query])
        if os.path.exists(output_path):
            return output_path
        # The postprocessor may have left a differently-suffixed file behind.
        leftovers = [p for p in globlib.glob(f"{output_stem}.*") if os.path.isfile(p)]
        if leftovers:
            return leftovers[0]
        print("[-] BGM fetch produced no audio file.")
        return None
    except Exception as e:
        print(f"[-] BGM fetch failed: {e}")
        return None

def fetch_broll_from_pexels(query, api_key):
    """Queries Pexels for a vertical stock video matching the semantic keyword"""
    if not api_key:
        return None
    try:
        print(f"[*] Querying Pexels for B-roll: '{query}'...")
        headers = {"Authorization": api_key}
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": 1, "orientation": "portrait"},
            timeout=30,
        )
        data = response.json()

        if data.get("videos"):
            # Get the highest quality mobile/portrait link
            video_files = data["videos"][0]["video_files"]
            best_link = video_files[0]["link"] # Usually the first one is fine

            broll_path = get_data_path("cache", f"broll_{sanitize_filename(query).replace(' ', '_')}.mp4")
            if os.path.exists(broll_path):
                return broll_path
            print(f"[*] Downloading stock asset: {broll_path}")
            v_data = requests.get(best_link, timeout=120).content
            with open(broll_path, "wb") as f:
                f.write(v_data)
            return broll_path
    except Exception as e:
        print(f"[-] B-roll fetch failed: {e}")
    return None

class MoviePyCallbackLogger(ProgressBarLogger):
    """Pipes MoviePy render progress into the dashboard callback.

    Subclasses proglog's own logger rather than duck-typing one. The previous
    hand-rolled version had to be abandoned for logger='bar' because its
    __getattr__ catch-all swallowed calls MoviePy relies on and produced empty
    261-byte output files; bars_callback is the supported extension point and
    leaves MoviePy's write path untouched.
    """
    def __init__(self, callback, clip_id, base=0.0, weight=100.0):
        super().__init__()
        self.callback = callback
        self.clip_id = clip_id
        self.base = base
        self.weight = weight
        self._last_reported = -1

    def bars_callback(self, bar, attr, value, old_value=None):
        # 't' is MoviePy's video frame bar; 'chunk' is the audio pass.
        if not self.callback or attr != "index" or bar != "t":
            return
        total = (self.bars.get(bar) or {}).get("total")
        if not total:
            return
        percent = round(self.base + (value / total) * self.weight, 1)
        # Throttle to whole-percent transitions; this fires once per frame.
        if int(percent) == self._last_reported:
            return
        self._last_reported = int(percent)
        try:
            self.callback(self.clip_id, min(percent, 100.0))
        except Exception:
            pass  # UI reporting must never abort a render

# ==============================================================================
# 6. UNIVERSAL FORMAT RENDERING MACHINE
# ==============================================================================
def run_production_clipper(json_data, on_clip_completed=None, on_progress=None):
    video_url = json_data["video_url"]
    pexels_key = json_data.get("pexels_key")

    # Fail fast and loudly on a broken toolchain rather than crashing mid-render.
    preflight_dependencies()

    print("[*] Launching neural voice processing arrays (Turbo Base Core)...")
    model = whisper.load_model(WHISPER_MODEL)

    for clip in json_data["clips"]:
        if on_progress: on_progress(clip['id'], 0)

        start_sec = timestamp_to_seconds(clip["start_time"])
        end_sec = timestamp_to_seconds(clip["end_time"])
        broll_keywords = clip.get("broll_keywords", [])
        bgm_mood = clip.get("bgm_mood")
        style_name = clip.get("style", "hormozi").lower()
        style_config = STYLE_TEMPLATES.get(style_name, STYLE_TEMPLATES["hormozi"])
        
        safe_title = sanitize_filename(clip['title'])
        raw_buffer_file = get_data_path("temp", f"network_chunk_buffer_{clip['id']}.mp4")
        output_filename = get_data_path("outputs", f"SmartShort_{clip['id']}_{safe_title}.mp4")
        
        # Pull only the required raw video frames down from the web layer
        # Scale download progress (0-100) to represents the first ~15% of the total clip progress
        def dl_progress_wrapper(p):
            if on_progress:
                on_progress(clip['id'], round(p * 0.15, 1))

        download_selective_range(video_url, raw_buffer_file, start_sec, end_sec, on_progress=dl_progress_wrapper)
        
        # B-Roll & BGM Acquisition
        broll_assets = []
        if pexels_key and broll_keywords:
            for kw in broll_keywords[:1]:
                path = fetch_broll_from_pexels(kw, pexels_key)
                if path: broll_assets.append(path)
        
        bgm_path = fetch_bgm_by_mood(bgm_mood) if bgm_mood else None
        
        # Pre-scan for visual scene changes
        visual_boundaries = find_visual_cut_points(raw_buffer_file)
        
        print(f"\n[+] Isolation pass ready. Unlocking buffer window for Clip #{clip['id']}...")
        macro_buffer_clip = VideoFileClip(raw_buffer_file)
        orig_w, orig_h = macro_buffer_clip.size
        
        # Fix #2: For already-portrait video (orig_w < orig_h) keep target_w = orig_w
        # so caption text_safe_width and compositor dimensions are correct.
        if orig_w < orig_h:
            target_w = orig_w
        else:
            target_w = int(orig_h * (9 / 16))
        if target_w % 2 != 0:
            target_w -= 1  # Standard even-integer H.264 video rendering guard
            
        compiled_event_clips = []

        timeline = clip.get("timeline") or [{"rel_start": 0, "rel_end": macro_buffer_clip.duration}]

        # Segment-by-segment timeline manipulation pass
        # carry_start holds the boundary chosen for the *previous* segment's end.
        # Previously only the end was nudged onto a pause while the next segment
        # still began at its original rel_start, so every adjusted cut either
        # repeated or dropped up to a second of footage.
        carry_start = None
        for idx, event in enumerate(timeline):
            rel_start = carry_start if carry_start is not None else event["rel_start"]
            rel_raw_end = event["rel_end"]

            # Reposition the video cut mark to map onto standard verbal silence or visual boundaries
            if idx < len(timeline) - 1:
                rel_end = find_smart_transition_point(macro_buffer_clip.audio, rel_raw_end, visual_cuts=visual_boundaries)
            else:
                rel_end = rel_raw_end

            # Clamp into the buffer and keep the segment non-degenerate; a snapped
            # boundary can otherwise land before the segment it is supposed to end.
            rel_start = max(0.0, min(float(rel_start), macro_buffer_clip.duration))
            rel_end = max(0.0, min(float(rel_end), macro_buffer_clip.duration))
            if rel_end - rel_start < 0.1:
                print(f"[-] Skipping degenerate segment #{idx} ({rel_start:.2f}s -> {rel_end:.2f}s).")
                carry_start = rel_end
                continue
            carry_start = rel_end

            crop_mode = event.get("crop_mode", "center").lower()
            zoom_factor = event.get("zoom", 1.0)
            
            event_clip = macro_buffer_clip.subclip(rel_start, rel_end)
            
            # Universal Orientation Splicer & Dynamic Tracker
            if orig_w < orig_h:
                processed_clip = event_clip  # Clip is already native 9:16 portrait
            elif crop_mode == "track":
                print(f"[*] Initializing neural tracking array for Segment #{idx}...")
                tracker = MultiFaceTracker(target_w, orig_w)
                
                # Fix #4: Capture tracker via default arg to avoid loop closure capture bug.
                # Without this, all segments would share the last iteration's tracker object.
                def track_and_crop(get_frame, t, _tracker=tracker):
                    frame = get_frame(t)
                    x1, x2 = _tracker.get_crop_window(frame)
                    return frame[:, x1:x2]
                
                processed_clip = event_clip.fl(track_and_crop)
            else:
                if crop_mode == "left": x1, x2 = 0, target_w
                elif crop_mode == "right": x1, x2 = orig_w - target_w, orig_w
                else: x1, x2 = (orig_w - target_w) // 2, ((orig_w - target_w) // 2) + target_w
                processed_clip = event_clip.crop(x1=x1, y1=0, x2=x2, y2=orig_h)
            
            # Digital Scale Punch-In Zoom Module
            if zoom_factor > 1.0:
                scaled = processed_clip.resize(zoom_factor)
                sw, sh = scaled.size
                processed_clip = scaled.crop(x1=(sw-target_w)//2, y1=(sh-orig_h)//2, 
                                             x2=((sw-target_w)//2)+target_w, y2=((sh-orig_h)//2)+orig_h)
            
            compiled_event_clips.append(processed_clip)

        if not compiled_event_clips:
            raise ValueError(
                f"Clip #{clip['id']} produced no usable segments. Check that its timeline "
                "start/end times fall inside the clip's duration."
            )

        # Stitch tracking adjustments
        joined_track = concatenate_videoclips(compiled_event_clips, method="compose")

        # B-Roll Overlay Compositor
        main_layers = [joined_track]
        if broll_assets:
            try:
                print("[*] Applying semantic B-roll overlays...")
                broll_clip = VideoFileClip(broll_assets[0]).set_duration(4).set_start(1).crossfadein(0.5).crossfadeout(0.5)
                # Resize and center crop B-roll to match target_w
                bw, bh = broll_clip.size
                b_target_w = target_w
                b_target_h = orig_h
                b_scaled = broll_clip.resize(height=b_target_h)
                b_sw, b_sh = b_scaled.size
                broll_clip = b_scaled.crop(x1=(b_sw-b_target_w)//2, y1=0, x2=((b_sw-b_target_w)//2)+b_target_w, y2=b_target_h)
                main_layers.append(broll_clip)
            except Exception as e:
                print(f"[-] B-roll overlay failed: {e}")

        # Audio Extraction Pipeline Patch
        # A source with no audio stream leaves joined_track.audio as None; that
        # used to surface as a bare AttributeError halfway through the render.
        all_words = []
        if joined_track.audio is None:
            print("[-] Source segment has no audio track. Skipping captions for this clip.")
        else:
            print("[*] Performing sound track mapping extraction pass...")
            temp_audio = get_data_path("temp", f"temp_audio_{clip['id']}.wav")
            joined_track.audio.write_audiofile(temp_audio, fps=16000, logger=None)

            # STYLISTIC HINGLISH EXAMPLES PREVENT ENCODING HALLUCINATIONS
            hinglish_prompt = (
                "Okay guys, so today we are talking about software engineering, code reviews, "
                "AI SaaS architecture, and bootstrapped startups. Product built ho gaya hai, "
                "ab marketing aur distribution pe focus karna hai. Kya chal raha hai? All good, "
                "everything is fully transparent."
            )

            print(f"[*] Starting whisper transcribe on {temp_audio}...")
            try:
                result = model.transcribe(temp_audio, word_timestamps=True, initial_prompt=hinglish_prompt, temperature=0.0)
                for segment in result.get("segments", []):
                    all_words.extend(segment.get("words", []))
            finally:
                if os.path.exists(temp_audio):
                    os.remove(temp_audio)
                    print("[*] Removed temp audio.")

        grouped_phrases = group_words_into_phrases(all_words, style_config)
        subtitle_clips = []

        text_safe_width = target_w - 80
        caption_baseline_y = int(orig_h * 0.58) # Safely clears mobile device interaction icons
        
        for phrase in grouped_phrases:
            phrase_text = " ".join([w["text"] for w in phrase])
            p_start = phrase[0]["start"]
            p_end = phrase[-1]["end"]
            
            kinetic_layers = create_kinetic_caption(phrase_text, p_start, (p_end - p_start), text_safe_width, caption_baseline_y, style_config)
            subtitle_clips.extend(kinetic_layers)
            
        # Final Audio Compositing with BGM & Ducking
        print("[*] Mastering final audio mix (Ducking BGM to 12%)...")
        primary_audio = joined_track.audio
        final_audio = primary_audio
        
        if bgm_path:
            try:
                bgm_clip = AudioFileClip(bgm_path).volumex(0.12)
                # Loop BGM if shorter than clip
                if bgm_clip.duration < joined_track.duration:
                    bgm_clip = afx.audio_loop(bgm_clip, duration=joined_track.duration)
                else:
                    bgm_clip = bgm_clip.subclip(0, joined_track.duration)

                layers = [primary_audio, bgm_clip] if primary_audio is not None else [bgm_clip]
                final_audio = CompositeAudioClip(layers)
            except Exception as e:
                print(f"[-] BGM mastering failed: {e}")

        # Re-encode to standard native video delivery formats
        # Fix #9: Use try/finally so clips are always closed even if write_videofile raises.
        print(f"[*] Compiling composite track layers into master file -> {output_filename}")
        final_short = CompositeVideoClip(main_layers + subtitle_clips).set_audio(final_audio)
        try:
            # Parallelize rendering across all available CPU threads.
            # Render occupies the remaining 85% of this clip's progress bar; the
            # callback logger reports it live instead of jumping 15% -> 100%.
            render_logger = MoviePyCallbackLogger(on_progress, clip['id'], base=15.0, weight=85.0)
            final_short.write_videofile(output_filename, codec='libx264', audio_codec='aac', fps=30,
                                        ffmpeg_params=["-pix_fmt", "yuv420p"], logger=render_logger,
                                        threads=os.cpu_count())

            if on_clip_completed:
                on_clip_completed(clip['id'], os.path.basename(output_filename))
        finally:
            final_short.close()
            macro_buffer_clip.close()
            if os.path.exists(raw_buffer_file):
                try:
                    os.remove(raw_buffer_file)
                except OSError:
                    pass

def fallback_full_transcription(video_url, job_id):
    """Fallback transcription using local full video cache and Whisper"""
    print("[*] Initiating Whisper fallback for full video transcription...")
    video_id = extract_video_id(video_url)

    full_video_path = get_data_path("temp", f"full_source_{video_id}.mp4")

    if not os.path.exists(full_video_path):
        print("[*] Full video not found in cache. Downloading via yt-dlp...")
        # Trigger download by requesting a 1-second segment (which downloads full video to cache)
        dummy_out = get_data_path("temp", f"dummy_{video_id}.mp4")
        download_selective_range(video_url, dummy_out, 0, 1)
        if os.path.exists(dummy_out):
            os.remove(dummy_out)
            
    if not os.path.exists(full_video_path):
        print("[-] Failed to cache full video for fallback transcription.")
        return None
        
    temp_audio = get_data_path("temp", f"temp_audio_full_{job_id}.wav")
    print(f"[*] Extracting full audio track to {temp_audio}...")
    
    # Extract 16kHz mono audio for optimized Whisper processing
    cmd = [
        "ffmpeg", "-y",
        "-i", full_video_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        temp_audio
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **_NO_WINDOW)
        if result.returncode != 0:
            tail = result.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
            raise RuntimeError("\n".join(tail))
    except Exception as e:
        print(f"[-] FFmpeg audio extraction failed: {e}")
        return None

    print("[*] Launching neural voice processing arrays (Turbo Base Core)...")
    model = whisper.load_model(WHISPER_MODEL)

    hinglish_prompt = (
        "Okay guys, so today we are talking about software engineering, code reviews, "
        "AI SaaS architecture, and bootstrapped startups. Product built ho gaya hai, "
        "ab marketing aur distribution pe focus karna hai. Kya chal raha hai? All good, "
        "everything is fully transparent."
    )
    
    print("[*] Starting Whisper transcription on full audio...")
    try:
        result = model.transcribe(temp_audio, initial_prompt=hinglish_prompt, temperature=0.0)
        transcript = result.get("text", "").strip()
    except Exception as e:
        print(f"[-] Whisper transcription failed: {e}")
        transcript = None
    finally:
        if os.path.exists(temp_audio):
            print(f"[*] Cleaning up temporary audio: {temp_audio}")
            os.remove(temp_audio)
    
    return transcript

# ==============================================================================
# 7. MAIN ENTRY LAYER
# ==============================================================================
if __name__ == "__main__":
    CONFIG_FILE = "clips.json"
    
    if not os.path.exists(CONFIG_FILE):
        print(f"[-] Structural Error: Ingestion payload target file missing: '{CONFIG_FILE}'")
        sys.exit(1)
        
    print(f"[+] Operational data maps online. Running workflow arrays from {CONFIG_FILE}...")
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        json_payload = json.load(file)
        
    run_production_clipper(json_payload)
    print("\n[+] SUCCESS: Automation process complete! All assets saved seamlessly to directory paths.")