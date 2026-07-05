"""
Extracts frames from every video in a folder using ffmpeg.
Output: JPEG frames + a metadata JSON per video (timestamp mapping).
Usage: python3 extract_frames.py <folder> <output_dir> <interval_seconds>
"""
import subprocess, sys, os, json, glob
ffmpeg_path = os.environ.get('FFMPEG_PATH', 'ffmpeg')  # Use env var if set, else default to 'ffmpeg'
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v')

def extract_frames(video_path, output_dir, interval_sec=1.5):
    os.makedirs(output_dir, exist_ok=True)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    # sanitise filename for use in frame filenames
    safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in video_name)
    fps = 1.0 / interval_sec
    out_pattern = os.path.join(output_dir, f"{safe_name}_%06d.jpg")

    cmd = [ffmpeg_path, '-y', '-i', video_path, '-vf', f'fps={fps}', '-q:v', '3', out_pattern]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Warning: ffmpeg error on {video_path}: {result.stderr[-200:]}")
        return []

    frame_files = sorted(
        f for f in os.listdir(output_dir)
        if f.startswith(safe_name) and f.endswith('.jpg')
    )
    metadata = [
        {
            'frame_file': fname,
            'frame_path': os.path.join(output_dir, fname),
            'source_video': video_path,
            'timestamp_sec': round(i * interval_sec, 2)
        }
        for i, fname in enumerate(frame_files)
    ]
    meta_path = os.path.join(output_dir, f"{safe_name}_meta.json")
    with open(meta_path, 'w') as f:
        json.dump(metadata, f)
    print(f"Extracted {len(metadata)} frames from {os.path.basename(video_path)}")
    return metadata

if __name__ == '__main__':
    folder      = sys.argv[1]
    output_dir  = sys.argv[2]
    interval    = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    videos = [
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(VIDEO_EXTENSIONS)
    ]
    if not videos:
        print(f"No video files found in {folder}")
        sys.exit(0)
    print(f"Found {len(videos)} video(s). Extracting frames...")
    for v in videos:
        extract_frames(v, output_dir, interval)
    print("Frame extraction complete.")