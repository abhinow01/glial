# ── Model ─────────────────────────────────────────────────────────────────────
CLIP_MODEL      = "ViT-B-32"
CLIP_PRETRAINED = "laion2b_s34b_b79k"
# Upgrade path: swap to "ViT-L-14" + "laion2b_s32b_b82k" for ~15% better accuracy
# at cost of ~3x slower embedding and ~4x more VRAM.

# Minimum distance gap between best and worst result.
# If stars scores 0.90 and cats scores 0.72, the gap is 0.18 — clearly different.
MIN_GAP_TO_FILTER = 0.08

# ── Scene detection ────────────────────────────────────────────────────────────
SCENE_THRESHOLD     = 27.0   # ContentDetector sensitivity. Lower = more scenes detected.
MIN_SCENE_LEN       = 15     # Minimum scene length in frames. Prevents flash cuts creating noise.
FALLBACK_FPS        = 1.0    # Frames per second if scene detection fails.

# ── Indexing ───────────────────────────────────────────────────────────────────
VIDEO_EXTENSIONS    = ('.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v')
HASH_CHUNK_BYTES    = 65536  # First 64 KB hashed for fast change detection.
EMBED_BATCH_SIZE    = 16     # Frames per CLIP batch. Raise if you have a GPU.

# ── Search ─────────────────────────────────────────────────────────────────────
VIDEO_CANDIDATES    = 15     # Stage 1: how many candidate videos to shortlist.
SIMILARITY_THRESHOLD = 0.80  # Cosine distance ceiling. 0 = identical, 1 = unrelated.
                              # Raise if you get zero results. Lower if junk slips through.
CLUSTER_GAP_SEC     = 3.0    # Frames within this gap merge into one scene result.

# ── ANN index (LanceDB IVF-PQ) ────────────────────────────────────────────────
ANN_MIN_ROWS        = 256    # Need this many rows before IVF-PQ is worth building.
IVF_PARTITIONS      = 32     # Roughly sqrt(N). More = faster search, slower build.
IVF_SUB_VECTORS     = 16     # Must divide embedding dim evenly. 512 / 16 = 32. ✓