"""
Incremental indexer.

Two LanceDB tables:
  'videos' — one row per video, video-level embedding (mean-pooled from scenes)
  'frames' — one row per scene frame, individual frame embedding + timestamp

Incremental logic:
  A JSON sidecar tracks {video_path: mtime+hash} so unchanged videos are skipped.
  On re-index, stale rows are removed and replaced — nothing accumulates.
"""
import os
import json
import hashlib

import lancedb
import numpy as np

from config import VIDEO_EXTENSIONS, HASH_CHUNK_BYTES, ANN_MIN_ROWS, IVF_PARTITIONS, IVF_SUB_VECTORS
from scene_detector import get_representative_timestamps, extract_frame_at
from embedder import embed_images_batch, mean_pool

SIDECAR = 'indexed_videos.json'


# ── Change detection ──────────────────────────────────────────────────────────

def _signature(path: str) -> str:
    """mtime + first-64KB hash — fast, reliable change indicator."""
    stat = os.stat(path)
    h    = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read(HASH_CHUNK_BYTES))
    return f"{stat.st_mtime}:{h.hexdigest()}"


def _load_sidecar(db_path: str) -> dict:
    p = os.path.join(db_path, SIDECAR)
    return json.load(open(p)) if os.path.exists(p) else {}


def _save_sidecar(db_path: str, data: dict):
    os.makedirs(db_path, exist_ok=True)
    with open(os.path.join(db_path, SIDECAR), 'w') as f:
        json.dump(data, f, indent=2)


# ── ANN index ─────────────────────────────────────────────────────────────────

def _build_ann_index(table, label: str):
    """
    IVF-PQ approximate nearest neighbour index.
    IVF partitions the space so we search a fraction of vectors.
    PQ compresses vectors so each comparison is cheaper.
    Falls back to exact search for small tables — no point building an index on 50 rows.
    """
    count = table.count_rows()
    if count < ANN_MIN_ROWS:
        print(f"    '{label}' has {count} rows — flat search (no ANN needed yet)")
        return
    partitions = min(IVF_PARTITIONS, count // 4)
    try:
        table.create_index(
            metric="cosine",
            num_partitions=partitions,
            num_sub_vectors=IVF_SUB_VECTORS,
            replace=True
        )
        print(f"    ANN index built on '{label}' ({partitions} partitions)")
    except Exception as e:
        print(f"    ANN index skipped on '{label}': {e}")


# ── Main entry ────────────────────────────────────────────────────────────────
def _rows_from_table(table):
    rows = table.to_pandas().to_dict('records')
    for r in rows:
        if 'vector' in r and hasattr(r['vector'], 'astype'):
            r['vector'] = r['vector'].astype(np.float32)
    return rows
def index_folder(
    folder_path:    str,
    db_path:        str,
    frames_cache:   str,
    ffmpeg_path:    str = 'ffmpeg'
):
    print(f"DB path: {db_path}", flush=True)      
    print(f"Frames cache: {frames_cache}", flush=True)  
    os.makedirs(frames_cache, exist_ok=True)

    sidecar = _load_sidecar(db_path)
    db      = lancedb.connect(db_path)
    
    # Load whatever is already indexed
    old_video_rows = _rows_from_table(db.open_table('videos')) if 'videos' in db.table_names() else []
    old_frame_rows = _rows_from_table(db.open_table('frames')) if 'frames' in db.table_names() else []
    video_files = sorted(
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(VIDEO_EXTENSIONS)
    )

    if not video_files:
        print(f"No videos found in {folder_path}")
        return

    print(f"Found {len(video_files)} video(s). Checking for changes...\n")

    new_video_rows  = []
    new_frame_rows  = []
    changed_videos  = set()   # videos that need their old rows dropped

    for video_path in video_files:
        sig = _signature(video_path)

        if sidecar.get(video_path) == sig:
            print(f"  ✓ Unchanged: {os.path.basename(video_path)}")
            continue

        print(f"  ↻ Indexing: {os.path.basename(video_path)}")
        changed_videos.add(video_path)

        # 1. Scene timestamps
        timestamps = get_representative_timestamps(video_path)
        print(f"Timestamps: {timestamps}")
        print(f"Count: {len(timestamps)}")
        # 2. Extract one JPEG per scene
        safe = "".join(
            c if c.isalnum() or c in '-_' else '_'
            for c in os.path.splitext(os.path.basename(video_path))[0]
        )
        frame_paths      = []
        valid_timestamps = []
        for i, ts in enumerate(timestamps):
            out = os.path.join(frames_cache, f"{safe}_{i:06d}.jpg")
            if extract_frame_at(video_path, ts, out, ffmpeg_path):
                frame_paths.append(out)
                valid_timestamps.append(ts)

        if not frame_paths:
            print(f"    Warning: no frames extracted")
            continue

        # 3. Batch-embed frames
        print(f"    Embedding {len(frame_paths)} frames...")
        embeddings = embed_images_batch(frame_paths)

        if len(embeddings) != len(frame_paths):
            # Some frames failed — align lists
            frame_paths      = frame_paths[:len(embeddings)]
            valid_timestamps = valid_timestamps[:len(embeddings)]

        if not embeddings:
            continue

        # 4. Video-level embedding
        video_emb = mean_pool(embeddings)

        # 5. Accumulate rows
        new_video_rows.append({
            'vector':       video_emb,
            'source_video': video_path,
            'scene_count':  len(frame_paths),
        })

        for fp, ts, emb in zip(frame_paths, valid_timestamps, embeddings):
            new_frame_rows.append({
                'vector':        emb,
                'frame_path':    fp,
                'source_video':  video_path,
                'timestamp_sec': float(ts),
            })

        sidecar[video_path] = sig
        print(f"    Indexed {len(frame_paths)} scenes\n")

    # Merge: drop changed videos' old rows, append new rows
    final_video_rows = [r for r in old_video_rows if r['source_video'] not in changed_videos] + new_video_rows
    final_frame_rows = [r for r in old_frame_rows if r['source_video'] not in changed_videos] + new_frame_rows

    if not final_video_rows:
        print("Nothing indexed yet.")
        return

    # Write both tables + ANN index
    for name, rows in [('videos', final_video_rows), ('frames', final_frame_rows)]:
        if name in db.table_names():
            db.drop_table(name)
        tbl = db.create_table(name, data=rows)
        _build_ann_index(tbl, name)
        print(f"  Saved {len(rows)} rows → '{name}'")

    _save_sidecar(db_path, sidecar)
    print(f"\nDone. {len(final_video_rows)} videos in index.")