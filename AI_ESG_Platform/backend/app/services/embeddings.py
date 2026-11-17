import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# Ensure Hugging Face and Transformers operate strictly offline in local environments
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

try:
    from sentence_transformers import SentenceTransformer
    # Try loading locally without network checks
    try:
        _model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    except Exception:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    logger.warning(f"SentenceTransformer model unavailable ({e}); will use fallback embeddings.")
    _model = None  # type: ignore


def generate_embeddings(texts):
    """
    Convert a list of text chunks into embedding vectors.
    Uses SentenceTransformer if available, with robust deterministic fallback.
    """
    if _model is not None:
        try:
            embeddings = _model.encode(texts)
            return embeddings.tolist()
        except Exception as e:
            logger.warning(f"SentenceTransformer encoding error: {e}; falling back.")

    # 384-dimensional normalized bag-of-words / hash embedding fallback
    dim = 384
    fallback_embs = []
    for text in texts:
        vec = [0.0] * dim
        tokens = text.lower().split()
        if not tokens:
            fallback_embs.append(vec)
            continue
        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            val = ((h >> 8) % 1000) / 1000.0 - 0.5
            vec[idx] += val
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        fallback_embs.append(vec)

    return fallback_embs
