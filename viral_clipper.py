import os
import json
import sys
import re
import numpy as np
import subprocess
from tqdm import tqdm

# ==============================================================================
# 1. WINDOWS PATH OVERRIDES & SYSTEM INTEGRITY CHECKS
# ==============================================================================
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_data_path(*parts):
    """Resolve a writable path under the fypd AppData directory.
    Reads FYPD_DATA_DIR (set by Tauri) with a local fallback for dev mode."""
    base = os.environ.get("FYPD_DATA_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "fypd"
    )
    path = os.path.join(base, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

# Try to find ImageMagick in the local 'bin' folder (for Tauri standalone mode) or respect environment overrides
local_magick = os.path.join(os.getcwd(), "bin", "magick.exe")
bundled_magick = get_resource_path(os.path.join("bin", "magick.exe"))

if "IMAGEMAGICK_BINARY" in os.environ:
    pass # Respect external environment overrides
elif os.path.exists(local_magick):
    os.environ["IMAGEMAGICK_BINARY"] = local_magick
elif os.path.exists(bundled_magick):
    os.environ["IMAGEMAGICK_BINARY"] = bundled_magick
else:
    # Fallback to a common default or let the user decide
    os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"

# Ensure local 'bin' directory containing ffmpeg, ffprobe, and magick is prepended to the system PATH
local_bin_dir = get_resource_path("bin")
if os.path.exists(local_bin_dir) and local_bin_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = local_bin_dir + os.pathsep + os.environ.get("PATH", "")

try:
    import yt_dlp
    import whisper
    import cv2
    import requests
    import mediapipe as mp
    from scenedetect import detect, ContentDetector
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, afx
except ImportError as e:
    print(f"[-] Missing core dependency library: {e}")
    print("[*] Please run: pip install yt-dlp whisper-openai moviepy==1.0.3 numpy mediapipe scenedetect[opencv] requests")
    sys.exit(1)

class MoviePyProgressLogger:
    def __init__(self, callback, base_progress, weight):
        self.callback = callback
        self.base_progress = base_progress
        self.weight = weight
    def __call__(self, *args, **kwargs): pass
    def callback_wrapper(self, iterable): return iterable
    def log_progress(self, current, total):
        if total > 0:
            percent = (current / total) * self.weight
            self.callback(self.base_progress + percent)
    def __getattr__(self, name): return lambda *args, **kwargs: None

# ==============================================================================
# 2. PREMIUM RETENTION TYPOGRAPHY & CV SETUP
# ==============================================================================
STYLE_TEMPLATES = {
    "hormozi": {
        "FONT": "Impact",
        "FONT_SIZE": 54,
        "TEXT_COLOR": "#FFFF00",
        "SHADOW_COLOR": "#000000",
        "MAX_WORDS_PER_PHRASE": 2,
        "MAX_GAP_SECONDS": 0.6,
        "ANIMATION": "bounce",
        "SHADOW_OFFSET": 4
    },
    "minimalist": {
        "FONT": "Arial",
        "FONT_SIZE": 48,
        "TEXT_COLOR": "#FFFFFF",
        "SHADOW_COLOR": "transparent",
        "MAX_WORDS_PER_PHRASE": 3,
        "MAX_GAP_SECONDS": 0.8,
        "ANIMATION": "fade",
        "SHADOW_OFFSET": 0
    },
    "neon": {
        "FONT": "Impact",
        "FONT_SIZE": 58,
        "TEXT_COLOR": "#00FFFF", # Neon Cyan
        "SHADOW_COLOR": "#FF00FF", # Neon Magenta Glow
        "MAX_WORDS_PER_PHRASE": 2,
        "MAX_GAP_SECONDS": 0.5,
        "ANIMATION": "bounce",
        "SHADOW_OFFSET": 2
    }
}

# Initialize MediaPipe Face Detection (Tasks API)
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import urllib.request

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
MODEL_PATH = get_data_path("models", "blaze_face_short_range.tflite")

if not os.path.exists(MODEL_PATH):
    print("[*] Downloading MediaPipe face tracking model asset...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.5)
face_detector = vision.FaceDetector.create_from_options(options)

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
            # Convert to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            results = face_detector.detect(mp_image)
            
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

def timestamp_to_seconds(ts):
    parts = list(map(int, ts.split(':')))
    if len(parts) == 3:
        return parts[0]*3600 + parts[1]*60 + parts[2]
    elif len(parts) == 2:
        return parts[0]*60 + parts[1]
    return 0

def clean_token(text):
    cleaned = text.strip().upper()
    cleaned = re.sub(r'[^\w\s]', '', cleaned)  # Strip out punctuation artifacts
    if cleaned in ["NONE", "", "[NONE]", "(NONE)", "UM", "UH", "AH", "ERR"]:
        return ""
    return cleaned

# Characters that are illegal in Windows filenames
_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')

def sanitize_filename(name: str) -> str:
    """Strip characters that are illegal in Windows filenames."""
    return _ILLEGAL_FILENAME_CHARS.sub('_', name).strip()

def group_words_into_phrases(words_list, style_config):
    phrases = []
    current_phrase = []
    for word_data in words_list:
        word_text = clean_token(word_data["word"])
        if not word_text:
            continue
        w_start = word_data["start"]
        w_end = word_data["end"]
        
        if not current_phrase:
            current_phrase = [{"text": word_text, "start": w_start, "end": w_end}]
        else:
            time_gap = w_start - current_phrase[-1]["end"]
            if (len(current_phrase) >= style_config["MAX_WORDS_PER_PHRASE"] or 
                time_gap > style_config["MAX_GAP_SECONDS"]):
                phrases.append(current_phrase)
                current_phrase = [{"text": word_text, "start": w_start, "end": w_end}]
            else:
                current_phrase.append({"text": word_text, "start": w_start, "end": w_end})
    if current_phrase:
        phrases.append(current_phrase)
    return phrases

# ==============================================================================
# 3. KINETIC ANIMATION INTERPOLATION INTERNALS
# ==============================================================================
def elastic_bounce_transform(t):
    """Calculates an organic elastic pop scaling effect over the first 150ms"""
    if t < 0.12:
        return 0.85 + (0.4 * (t / 0.12))
    elif t < 0.22:
        return 1.25 - (0.25 * ((t - 0.12) / 0.10))
    return 1.0

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
def download_selective_range(url, output_path, start_sec, end_sec, on_progress=None):
    """Downloads the full video if not present, then extracts the requested range locally."""
    if os.path.exists(output_path):
        return
        
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    video_id = video_id_match.group(1) if video_id_match else "unknown_video"
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
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def fetch_bgm_by_mood(mood):
    """Searches and downloads a royalty-free audio track matching the mood"""
    search_query = f"ytsearch1:royalty free {mood} music for youtube shorts"
    output_path = get_data_path("cache", f"bgm_{mood}.mp3")
    
    if os.path.exists(output_path):
        return output_path
        
    print(f"[*] Sourcing mood-appropriate audio for '{mood}'...")
    
    bin_dir = get_resource_path("bin")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
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
        return output_path
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
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=1&orientation=portrait"
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if data.get("videos"):
            # Get the highest quality mobile/portrait link
            video_files = data["videos"][0]["video_files"]
            best_link = video_files[0]["link"] # Usually the first one is fine
            
            broll_path = get_data_path("cache", f"broll_{query.replace(' ', '_')}.mp4")
            print(f"[*] Downloading stock asset: {broll_path}")
            v_data = requests.get(best_link).content
            with open(broll_path, "wb") as f:
                f.write(v_data)
            return broll_path
    except Exception as e:
        print(f"[-] B-roll fetch failed: {e}")
    return None

class MoviePyCallbackLogger:
    """Stable MoviePy logger that pipes progress to a callback without crashing"""
    def __init__(self, callback, clip_id):
        self.callback = callback
        self.clip_id = clip_id
    def __call__(self, *args, **kwargs):
        m = args[0] if args else kwargs.get('message', '')
        if self.callback and isinstance(m, str) and "t: " in m:
            match = re.search(r'(\d+)%', m)
            if match: self.callback(self.clip_id, int(match.group(1)))
    def iter_bar(self, **kwargs):
        for key in ['iterable', 'sequence']:
            if key in kwargs: return kwargs[key]
        return []
    def callback_wrapper(self, iterable): return iterable
    def log_progress(self, current, total): pass
    def __getattr__(self, name):
        return lambda *args, **kwargs: args[0] if args else None

# ==============================================================================
# 6. UNIVERSAL FORMAT RENDERING MACHINE
# ==============================================================================
def run_production_clipper(json_data, on_clip_completed=None, on_progress=None):
    video_url = json_data["video_url"]
    pexels_key = json_data.get("pexels_key")
    print("[*] Launching neural voice processing arrays (Turbo Base Core)...")
    model = whisper.load_model("base")
    
    total_clips = len(json_data["clips"])
    for i, clip in enumerate(json_data["clips"]):
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
        
        # Segment-by-segment timeline manipulation pass
        for idx, event in enumerate(clip.get("timeline", [])):
            rel_start = event["rel_start"]
            rel_raw_end = event["rel_end"]
            
            # Reposition the video cut mark to map onto standard verbal silence or visual boundaries
            if idx < len(clip["timeline"]) - 1:
                rel_end = find_smart_transition_point(macro_buffer_clip.audio, rel_raw_end, visual_cuts=visual_boundaries)
            else:
                rel_end = rel_raw_end
                
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
        result = model.transcribe(temp_audio, word_timestamps=True, initial_prompt=hinglish_prompt, temperature=0.0)
        print(f"[*] Whisper transcribe finished. Removing {temp_audio}...")
        os.remove(temp_audio)
        print("[*] Removed temp audio.")
        
        all_words = []
        for segment in result.get("segments", []):
            all_words.extend(segment.get("words", []))
            
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
                
                final_audio = CompositeAudioClip([primary_audio, bgm_clip])
            except Exception as e:
                print(f"[-] BGM mastering failed: {e}")

        # Re-encode to standard native video delivery formats
        # Fix #9: Use try/finally so clips are always closed even if write_videofile raises.
        print(f"[*] Compiling composite track layers into master file -> {output_filename}")
        final_short = CompositeVideoClip(main_layers + subtitle_clips).set_audio(final_audio)
        try:
            # Parallelize rendering across all available CPU threads
            # Standard 'bar' logger is restored to fix the 261-byte empty artifact issue
            final_short.write_videofile(output_filename, codec='libx264', audio_codec='aac', fps=30,
                                        ffmpeg_params=["-pix_fmt", "yuv420p"], logger='bar', threads=os.cpu_count())
            
            if on_clip_completed:
                on_clip_completed(clip['id'])
        finally:
            final_short.close()
            macro_buffer_clip.close()

def fallback_full_transcription(video_url, job_id):
    """Fallback transcription using local full video cache and Whisper"""
    print("[*] Initiating Whisper fallback for full video transcription...")
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', video_url)
    video_id = video_id_match.group(1) if video_id_match else "unknown_video"
    
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
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[-] FFmpeg audio extraction failed: {e}")
        return None
    
    print("[*] Launching neural voice processing arrays (Turbo Base Core)...")
    model = whisper.load_model("base")
    
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