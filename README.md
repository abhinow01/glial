# Clippit

> Semantic search for your video footage. Describe what you're looking for in plain English — Clippit finds the exact video.

---

## What this is

If you shoot or edit video, you know the problem. You have a folder of clips — maybe dozens, maybe hundreds — and you need *that one shot*. The person laughing. The cat jumping off the table. The sunset from day three. So you scrub. And scrub. And scrub.

Clippit fixes this. You type what you're looking for, and it finds it. Not by filename, not by tag you manually added — by actually understanding what's *in* the video, frame by frame.

It runs entirely on your laptop. Your footage never leaves your machine.

---

## Demo

```
You type:    "cat jumping on table"
Clippit:     cats_video.mp4  →  best match at 0:34  (71% confidence)
```

Click the thumbnail → video opens at that exact moment.
Drag the thumbnail → drop it straight into Premiere, Resolve, or Final Cut.

---

## How it works under the hood

This section explains the actual mechanism .

### The core idea: turning images into numbers

Every frame of your footage gets converted into a list of 512 numbers. That list is called a **vector** or **embedding**. The magic is that these numbers encode *meaning* — not pixels, not colors, but what's actually happening in the image.

A frame with a cat produces a vector. The text "cat" also produces a vector. And those two vectors are *close to each other* in mathematical space — even though one came from an image and one came from text. This is what lets you search with words and find images.

This is done by a model called **CLIP** (Contrastive Language-Image Pretraining), trained by OpenAI on 400 million image-text pairs scraped from the internet. It learned that the word "cat" and pictures of cats belong together, that "sunset" and orange skies belong together, and so on — for essentially every concept in human language.

### Step 1 — Indexing (happens once per folder)

When you click "Index footage", this is what runs:

```
Your video files
      │
      ▼
Scene detection (PySceneDetect)
      │
      │  Instead of extracting every frame (which would be
      │  thousands per video), we detect scene cuts — moments
      │  where the visual content changes significantly.
      │  A 2-hour video might have 300 scenes instead of 7,200 frames.
      │
      ▼
Frame extraction (ffmpeg)
      │
      │  One JPEG is pulled from the middle of each scene.
      │  These are the "representative frames" — the best single
      │  image to describe what's happening in that part of the video.
      │
      ▼
CLIP image encoder
      │
      │  Each frame gets passed through CLIP's image encoder.
      │  Output: one 512-dimensional vector per frame.
      │  This is the mathematical fingerprint of what's in that frame.
      │
      ▼
Mean pooling → video-level vector
      │
      │  All the frame vectors for a single video get averaged
      │  into one vector. This is the "summary" of the whole video.
      │  Think of it as: what is this video about, overall?
      │
      ▼
LanceDB (stored on disk)
      │
      │  Two tables get written:
      │  • 'videos' table — one row per video, with its summary vector
      │  • 'frames' table — one row per scene frame, with its vector + timestamp
      │
      ▼
Done. Index persists between app restarts.
```

**Incremental indexing:** Clippit stores a fingerprint (hash) of each video file. On subsequent runs, it checks whether the file has changed. If it hasn't, it skips it entirely. Only new or modified videos get re-indexed.

---

### Step 2 — Searching

When you type a query and hit Search, this runs in under a second:

```
Your text query: "cat jumping on table"
      │
      ▼
CLIP text encoder
      │
      │  The same CLIP model that encoded your frames also
      │  encodes your text. Output: one 512-dimensional vector.
      │  Crucially, this vector lives in the SAME mathematical
      │  space as the image vectors — that's the whole trick.
      │
      ▼
Stage 1: Search the VIDEO table
      │
      │  We compare your query vector against every video's
      │  summary vector. This is fast because there are few videos.
      │  Output: top 15 candidate videos that might match.
      │
      │  Videos above the similarity threshold get dropped.
      │  (A distance score > 0.80 means "probably unrelated".)
      │
      ▼
Stage 2: Search the FRAME table (candidates only)
      │
      │  Now we search frame-by-frame — but ONLY inside the
      │  candidate videos from Stage 1. This keeps it fast
      │  regardless of how many total videos you have indexed.
      │  Output: the specific frames that best match your query.
      │
      ▼
Scene clustering
      │
      │  If 4 frames from the same video all match, and they're
      │  all within 3 seconds of each other, they collapse into
      │  one result. You get "match at 0:34", not 4 separate
      │  cards for 0:33, 0:34, 0:35, 0:36.
      │
      ▼
Results: video cards with thumbnail + timestamp + confidence
```

**Why two stages?** If you have 500 videos with 200 scenes each, that's 100,000 frame vectors. Searching all of them every query would be slow. Stage 1 narrows it down to 15 candidate videos first (~3,000 frames max), then Stage 2 searches only those. The search stays fast no matter how large your library grows.

---

### What "distance" means

CLIP gives every comparison a **cosine distance** score between 0 and 1:

| Distance | What it means |
|---|---|
| 0.0 – 0.60 | Strong match — this is almost certainly relevant |
| 0.60 – 0.75 | Good match — probably what you're looking for |
| 0.75 – 0.85 | Weak match — loosely related |
| 0.85+ | Unrelated — filtered out |

Note that cross-modal CLIP distances (text vs image) naturally sit higher than same-modal (image vs image). A "strong match" at 0.65 is genuinely good — don't compare these numbers to other similarity systems.

---

## Project structure

```
clippit/
│
├── main.js                  Electron main process
│                            Controls the window, native dialogs,
│                            spawns Python scripts, handles IPC
│
├── preload.js               Security bridge
│                            Exposes only specific APIs to the UI
│                            (Electron's contextIsolation pattern)
│
├── index.html               The full UI
│                            Splash screen + search interface
│
├── renderer.js              UI logic
│                            Handles button clicks, renders results,
│                            drag-and-drop, rename
│
├── package.json             Electron app config + dependencies
│
└── backend/
    │
    ├── config.py            Every tunable number in one place
    │                        Adjust thresholds, batch sizes, model
    │                        choice here — nowhere else
    │
    ├── scene_detector.py    Scene cut detection + frame extraction
    │                        Uses PySceneDetect, falls back to 1FPS
    │                        sampling if unavailable
    │
    ├── embedder.py          CLIP model wrapper
    │                        Loads once, stays in memory
    │                        Handles batch embedding for speed
    │                        Auto-detects GPU/Apple Silicon/CPU
    │
    ├── indexer.py           Incremental indexing pipeline
    │                        Detects changed files via hash
    │                        Writes both LanceDB tables
    │                        Builds ANN index when table is large enough
    │
    ├── searcher.py          Two-stage search + clustering
    │                        Stage 1: video table
    │                        Stage 2: frame table (candidates only)
    │                        Clusters nearby frames into scenes
    │
    ├── index_search.py      Thin CLI entry point
    │                        main.js calls this — nothing else should
    │
    └── requirements.txt     Python dependencies
```

---

## Installation

### Prerequisites

- **Node.js** v18+ — [nodejs.org](https://nodejs.org)
- **Python** 3.10+ — [python.org](https://python.org)
- **ffmpeg** — used for frame extraction

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
# Add the bin/ folder to your PATH
```

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/yourname/clippit.git
cd clippit

# 2. Install Python dependencies
cd backend
pip install -r requirements.txt
cd ..

# 3. Install Electron
npm install

# 4. Run
npm start
```

First run will download the CLIP model weights (~350MB, one-time, then cached).

---

## Usage

1. **Choose folder** — point Clippit at any folder containing `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, or `.m4v` files
2. **Index footage** — Clippit processes every video (this takes a while the first time; subsequent runs skip unchanged files)
3. **Search** — type anything in plain English and press Enter
4. **Click a result** — opens the video at the matched timestamp in your default player
5. **Drag a result** — drag the thumbnail into Premiere, Resolve, Final Cut, or anywhere else that accepts file drops
6. **Rename** — edit the filename inline and press Enter or click Rename

---

## Configuration

All tunable parameters live in `backend/config.py`:

```python
# How sensitive scene detection is — lower = more scenes detected
SCENE_THRESHOLD = 27.0

# Distance cutoff — raise if you get zero results, lower if junk slips through
SIMILARITY_THRESHOLD = 0.80

# How many candidate videos Stage 1 shortlists
VIDEO_CANDIDATES = 15

# Frames within this many seconds collapse into one scene result
CLUSTER_GAP_SEC = 3.0

# Frames per CLIP batch — raise if you have a GPU
EMBED_BATCH_SIZE = 16
```

### Upgrading the model

The default model is `ViT-B-32` — fast, good quality, runs on CPU. To get ~15% better accuracy at the cost of ~3x slower indexing:

```python
# In config.py
CLIP_MODEL      = "ViT-L-14"
CLIP_PRETRAINED = "laion2b_s32b_b82k"
```

Delete your existing index after changing the model — old embeddings are incompatible.

---

## Troubleshooting

**No results returned**

Raise `SIMILARITY_THRESHOLD` in `config.py` toward `0.85`. CLIP cross-modal distances are higher than people expect — the default may be too strict for your footage type.

**Wrong videos returned**

Lower `SIMILARITY_THRESHOLD` toward `0.75`. Also check that indexing completed fully — partial indexes produce noisy results.

**Indexing is slow**

Normal on CPU. A 10-minute video with 40 scenes takes ~2–3 minutes to embed on CPU, ~20 seconds on a GPU. Set `EMBED_BATCH_SIZE = 32` or higher if you have VRAM to spare.

**"Unchanged" shown but index seems stale**

Delete the LanceDB folder and re-index from scratch:
```bash
# macOS
rm -rf ~/Library/Application\ Support/clippit/lancedb
rm -rf ~/Library/Application\ Support/clippit/frames
```

**NumPy version error**

```bash
pip install "numpy<2"
```

---

## Roadmap

- [ ] NLE panel — run Clippit as a sidebar inside Premiere Pro and DaVinci Resolve, so search results drop directly into your timeline
- [ ] Audio/transcript search — run Whisper on the audio track so you can search spoken words ("find the part where she says 'we need to talk'")
- [ ] Face clustering — group shots by who's in them automatically
- [ ] Auto-tagging — pre-label footage as it's imported (drone shot, close-up, indoor, outdoor, etc.)
- [ ] Selects reel — given a query, auto-assemble the top N matching moments into a rough cut

---

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| App shell | Electron | Native file system access, OS-level drag-and-drop, cross-platform |
| UI | Vanilla HTML/CSS/JS | No framework overhead for a single-window app |
| Frame extraction | ffmpeg | Industry standard, handles every video codec |
| Scene detection | PySceneDetect | Avoids embedding thousands of near-identical frames |
| Embeddings | CLIP via open_clip | Best-in-class cross-modal (text↔image) understanding |
| Vector storage | LanceDB | Embedded, no server, fast ANN search, persists to disk |
| ML runtime | PyTorch | CLIP runs on CPU, CUDA, or Apple Silicon MPS automatically |

---

## License

MIT
