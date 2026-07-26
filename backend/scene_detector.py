"""
Scene-based frame sampling.
Returns representative timestamps — one per scene cut.
Falls back to uniform FPS sampling if PySceneDetect isn't installed or fails.
"""
import os
import json
import subprocess
from typing import List

try:
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector
    SCENEDETECT_AVAILABLE = True
except ImportError:
    SCENEDETECT_AVAILABLE = False

from config import SCENE_THRESHOLD, MIN_SCENE_LEN, FALLBACK_FPS


def get_video_duration(video_path: str) -> float:
    cmd = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams', video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return 0.0
    data = json.loads(result.stdout)
    for stream in data.get('streams', []):
        if stream.get('codec_type') == 'video':
            dur = stream.get('duration')
            if dur:
                return float(dur)
    fmt_dur = data.get('format', {}).get('duration')
    
    if fmt_dur:
        return float(fmt_dur)
    return 0.0


def get_representative_timestamps(video_path: str) -> List[float]:
    """
    Returns a list of timestamps (seconds) — one per detected scene.
    These are the frames we'll embed. Not every second, just the meaningful ones.
    """
    if SCENEDETECT_AVAILABLE:
        try:
            return _scene_detect(video_path)
        except Exception as e:
            print(f"    Scene detection failed ({e}), falling back to {FALLBACK_FPS}FPS sampling")

    return _uniform_sample(video_path)


def _scene_detect(video_path: str) -> List[float]:
    video   = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(ContentDetector(
        threshold=SCENE_THRESHOLD,
        min_scene_len=MIN_SCENE_LEN
    ))
    manager.detect_scenes(video, show_progress=False)
    scenes = manager.get_scene_list()

    if not scenes:
        # No cuts detected — single-shot video. Sample at 25%, 50%, 75%.
        duration = get_video_duration(video_path)
        if duration <= 0:
            return [0.0]
        return [round(duration * p, 3) for p in (0.25, 0.50, 0.75)]

    # Take the midpoint of each scene as its representative frame.
    timestamps = [
        round((start.get_seconds() + end.get_seconds()) / 2, 3)
        for start, end in scenes
    ]
    print(f"    {len(timestamps)} scenes detected")
    return timestamps


def _uniform_sample(video_path: str) -> List[float]:
    duration = get_video_duration(video_path)
    print(f"    Duration detected: {duration:.1f}s", flush=True)

    if duration <= 0:
        print("    WARNING: could not detect duration — using [1.0, 3.0, 5.0] as fallback", flush=True)
        return [1.0, 3.0, 5.0]   # avoid 0.0s which is often a black frame

    step = 1.0 / FALLBACK_FPS
    # Start at 1 second to skip potential black frames at the very start
    timestamps = [round(t * step, 3) for t in range(1, int(duration / step))]
    print(f"    {len(timestamps)} frames at {FALLBACK_FPS}FPS", flush=True)
    return timestamps if timestamps else [min(1.0, duration / 2)]

def extract_frame_at(
    video_path: str,
    timestamp_sec: float,
    output_path: str,
    ffmpeg_path: str = 'ffmpeg'
) -> bool:
    """Extract exactly one frame at a given timestamp."""
    cmd = [
        ffmpeg_path, '-y',
        '-ss', str(timestamp_sec),
        '-i', video_path,
        '-vframes', '1',
        '-q:v', '2',
        output_path
    ]
    print("\nRunning:", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, capture_output=True)
    print("Return code:", result.returncode, flush=True)
    print("STDOUT:", result.stdout, flush=True)
    print("STDERR:", result.stderr, flush=True)

    print("Frame exists:", os.path.exists(output_path), flush=True)
    return result.returncode == 0 and os.path.exists(output_path)