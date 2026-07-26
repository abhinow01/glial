"""
CLIP model — loaded once, reused for everything.

Batch embedding is the main performance win here.
Embedding 16 frames in one GPU call is ~10x faster than 16 separate calls.
"""
import numpy as np
import torch
import open_clip
from PIL import Image
from typing import List

from config import CLIP_MODEL, CLIP_PRETRAINED, EMBED_BATCH_SIZE

_model      = None
_preprocess = None
_tokenizer  = None
_device     = None


def _get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device('cuda')
    if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return torch.device('mps')   # Apple Silicon
    return torch.device('cpu')


def load_model():
    global _model, _preprocess, _tokenizer, _device
    if _model is not None:
        return

    _device = _get_device()
    print(f"  Loading CLIP ({CLIP_MODEL}) on {_device}...")
    _model, _, _preprocess = open_clip.create_model_and_transforms(
        CLIP_MODEL, pretrained=CLIP_PRETRAINED
    )
    _model     = _model.to(_device).eval()
    _tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
    print("  CLIP ready.")


def embed_images_batch(image_paths: List[str]) -> List[np.ndarray]:
    """
    Embed a list of image files in batches.
    Returns one 512-dim L2-normalised vector per image.
    Images that fail to open are silently skipped.
    """
    load_model()
    results   = []
    skipped   = 0

    for i in range(0, len(image_paths), EMBED_BATCH_SIZE):
        batch_paths = image_paths[i : i + EMBED_BATCH_SIZE]
        tensors = []

        for p in batch_paths:
            try:
                tensors.append(_preprocess(Image.open(p).convert('RGB')))
            except Exception:
                skipped += 1

        if not tensors:
            continue

        batch = torch.stack(tensors).to(_device)
        with torch.no_grad():
            f = _model.encode_image(batch)
            f /= f.norm(dim=-1, keepdim=True)

        results.extend(f.cpu().numpy().astype(np.float32))

    if skipped:
        print(f"    Skipped {skipped} unreadable frames")

    return results


def embed_text(query: str) -> np.ndarray:
    load_model()
    tokens = _tokenizer([query]).to(_device)
    with torch.no_grad():
        f = _model.encode_text(tokens)
        f /= f.norm(dim=-1, keepdim=True)
    return f.squeeze(0).cpu().numpy().astype(np.float32)


def mean_pool(embeddings: List[np.ndarray]) -> np.ndarray:
    """
    Video-level embedding = normalised mean of frame embeddings.
    Re-normalising after averaging keeps it in the same cosine space.
    """
    stacked = np.stack(embeddings)
    mean    = stacked.mean(axis=0)
    norm    = np.linalg.norm(mean)
    return (mean / norm).astype(np.float32) if norm > 0 else mean.astype(np.float32)