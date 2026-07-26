"""
Two-stage semantic search with frame clustering.

Stage 1 — video index:
  Searches ~N_videos vectors. Fast. Returns candidate shortlist.

Stage 2 — frame index (candidates only):
  Searches only frames belonging to shortlisted videos.
  Bounded: N_candidates × avg_scenes_per_video — not the full frame corpus.

Clustering:
  Frames within CLUSTER_GAP_SEC of each other collapse into one scene result.
  Prevents returning 6 near-identical thumbnails from the same 10-second window.
"""
import json
from typing import List, Dict, Any

import lancedb
import numpy as np

from config import VIDEO_CANDIDATES, SIMILARITY_THRESHOLD, CLUSTER_GAP_SEC, MIN_GAP_TO_FILTER
from embedder import embed_text


def search(db_path: str, query: str, top_k: int = 10) -> list:
    db = lancedb.connect(db_path)

    if 'videos' not in db.table_names() or 'frames' not in db.table_names():
        print('[]')
        return []

    query_vec = embed_text(query)

    # Stage 1 — video level
    video_hits = (
        db.open_table('videos')
        .search(query_vec)
        .metric('cosine')
        .limit(VIDEO_CANDIDATES)
        .to_list()
    )

    if not video_hits:
        print('[]')
        return []

    # Filter by absolute threshold
    passed = [r for r in video_hits if r.get('_distance', 1.0) < SIMILARITY_THRESHOLD]

    if not passed:
        print('[]')
        return []

    # Filter by relative gap — drop anything scoring much worse than the best
    best_distance = passed[0]['_distance']
    candidates = {
        r['source_video']: r['_distance']
        for r in passed
        if r['_distance'] <= best_distance + MIN_GAP_TO_FILTER
    }

    print(f"  {len(candidates)} candidate video(s) after gap filter", flush=True)

    # Stage 2 — frame level, only for candidate videos
    frame_hits = (
        db.open_table('frames')
        .search(query_vec)
        .metric('cosine')
        .limit(VIDEO_CANDIDATES * 50)
        .to_list()
    )

    relevant_frames = [
        r for r in frame_hits
        if r['source_video'] in candidates
        and r.get('_distance', 1.0) < SIMILARITY_THRESHOLD
    ]

    if not relevant_frames:
        # Fall back to best frame per candidate video ignoring frame threshold
        relevant_frames = [
            r for r in frame_hits
            if r['source_video'] in candidates
        ]

    by_video = {}
    for r in relevant_frames:
        by_video.setdefault(r['source_video'], []).append(r)

    results = []
    for video_path, frames in by_video.items():
        frames.sort(key=lambda x: x['timestamp_sec'])
        clusters = _cluster(frames)
        best     = min(clusters, key=lambda c: c['distance'])
        results.append({
            'source_video':    video_path,
            'best_frame':      best['frame_path'],
            'best_timestamp':  best['timestamp'],
            'video_score':     round(candidates[video_path], 4),
            'frame_score':     round(best['distance'], 4),
            'confidence':      round((1 - best['distance'] / 2) * 100, 1),  # rescaled to 0-100
            'matching_scenes': len(clusters),
        })

    results.sort(key=lambda x: x['frame_score'])
    print(json.dumps(results[:top_k]))
    return results[:top_k]

def _cluster(frames: List[Dict]) -> List[Dict]:
    """
    Merge adjacent frames into scenes.
    Returns the best (lowest distance) frame from each cluster.
    """
    if not frames:
        return []

    clusters      = []
    current       = [frames[0]]

    for frame in frames[1:]:
        if frame['timestamp_sec'] - current[-1]['timestamp_sec'] <= CLUSTER_GAP_SEC:
            current.append(frame)
        else:
            clusters.append(current)
            current = [frame]
    clusters.append(current)

    return [
        {
            'frame_path': best['frame_path'],
            'timestamp':  best['timestamp_sec'],
            'distance':   best.get('_distance', 1.0),
        }
        for cluster in clusters
        for best in [min(cluster, key=lambda f: f.get('_distance', 1.0))]
    ]