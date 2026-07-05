"""
CLIP embedding + LanceDB indexing + semantic search.
Usage:
  Index:  python3 index_search.py index  <frames_dir> <db_path>
  Search: python3 index_search.py search <db_path> "query text" [top_k]
"""
import sys, os, json, glob
import torch, open_clip
from PIL import Image
import lancedb, pyarrow as pa
import numpy as np
from collections import defaultdict
MODEL_NAME = 'ViT-B-32'
PRETRAINED  = 'laion2b_s34b_b79k'
_model = _preprocess = _tokenizer = None

def load_model():
    global _model, _preprocess, _tokenizer
    if _model is None:
        print('Loading CLIP model...')
        _model, _, _preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
        _tokenizer = open_clip.get_tokenizer(MODEL_NAME)
        _model.eval()
    return _model, _preprocess, _tokenizer

def embed_image(path):
    model, preprocess, _ = load_model()
    img = preprocess(Image.open(path).convert('RGB')).unsqueeze(0)
    with torch.no_grad():
        f = model.encode_image(img)
        f /= f.norm(dim=-1, keepdim=True)
    return f.squeeze(0).numpy().astype(np.float32)

def embed_text(query):
    model, _, tokenizer = load_model()
    tokens = tokenizer([query])
    with torch.no_grad():
        f = model.encode_text(tokens)
        f /= f.norm(dim=-1, keepdim=True)
    return f.squeeze(0).numpy().astype(np.float32)

def index_frames(frames_dir, db_path):
    meta_files = glob.glob(os.path.join(frames_dir, '*_meta.json'))
    if not meta_files:
        print('No metadata found. Run extract_frames.py first.')
        sys.exit(1)

    rows = []
    for mf in meta_files:
        entries = json.load(open(mf))
        for e in entries:
            if not os.path.exists(e['frame_path']):
                continue
            vec = embed_image(e['frame_path'])
            rows.append({
                'vector':       vec,
                'frame_path':   e['frame_path'],
                'source_video': e['source_video'],
                'timestamp_sec': e['timestamp_sec']
            })
            print(f"Indexed: {os.path.basename(e['frame_path'])} @ {e['timestamp_sec']}s")

    db = lancedb.connect(db_path)
    if 'frames' in db.table_names():
        db.drop_table('frames')
    db.create_table('frames', data=rows)
    print(f"Indexed {len(rows)} frames into {db_path}")

def search(db_path, query, top_k=20):
    db = lancedb.connect(db_path)
    table = db.open_table('frames')
    qvec = embed_text(query)
    results = table.search(qvec).limit(top_k * 10).to_list()
    videos = defaultdict(list)
    for r in results:
        videos[r['source_video']].append(r)
    video_results=[]
    for video , frames in videos.items():
        frames.sort(key=lambda x: x['_distance'])
        best_frame = frames[0]
        top_frame = frames[:5]
        avg_distance = sum(f.get('_distance', 0) for f in top_frame) / len(top_frame)
        video_results.append({
            "source_video": video,
            "best_timestamp": best_frame["timestamp_sec"],
            "best_frame": best_frame["frame_path"],
            "score": avg_distance,
            "matches": len(frames)
        })
    
    video_results.sort(key=lambda x: x["score"])
    best_score = video_results[0]["score"]
    threshold = best_score * 1.25
    filtered = [
        v for v in video_results if v["score"] <= threshold 
    ]
    
    print(json.dumps(filtered[:top_k]))

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'index':
        index_frames(sys.argv[2], sys.argv[3])
    elif mode == 'search':
        search(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 20)