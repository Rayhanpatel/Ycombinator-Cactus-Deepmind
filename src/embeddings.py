"""
Offline Embedding Pipeline — Compute MiniLM embeddings for all KB entries.

Reads each KB JSON, embeds `symptom + diagnosis + tags`, and writes:
  1. An `embedding` field (384-dim float list) into each KB JSON
  2. A consolidated `kb/kb_index.json` for fast runtime loading

Run once as a build step:
    python -m src.embeddings

No model dependency at runtime — embeddings are baked into the JSON files.
"""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

KB_DIR = Path("kb")
INDEX_FILE = KB_DIR / "kb_index.json"
MODEL_NAME = "all-MiniLM-L6-v2"


def build_search_text(entry: dict) -> str:
    """
    Combine the fields we want to embed into a single search string.
    Prioritizes symptom and diagnosis (what the tech will describe),
    with tags and model info for extra signal.
    """
    parts = [
        entry.get("brand", ""),
        entry.get("model", ""),
        entry.get("symptom", ""),
        entry.get("diagnosis", ""),
        " ".join(entry.get("tags", [])),
    ]
    return " ".join(p for p in parts if p).strip()


def main():
    """Compute embeddings for all KB entries and write to disk."""
    # Load the model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.error(
            "❌ sentence-transformers not installed.\n"
            "   Run: pip install sentence-transformers\n"
            "   Then re-run: python -m src.embeddings"
        )
        sys.exit(1)

    logger.info(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    logger.info("✅ Model loaded")

    # Find all KB entry files
    kb_files = sorted(
        f for f in KB_DIR.glob("*.json")
        if f.name not in ("kb_index.json",) and not f.name.startswith(".")
    )

    if not kb_files:
        logger.error(f"❌ No KB entries found in {KB_DIR}/")
        sys.exit(1)

    logger.info(f"Found {len(kb_files)} KB entries")

    entries = []
    for kb_file in kb_files:
        with open(kb_file) as f:
            entry = json.load(f)

        search_text = build_search_text(entry)
        logger.info(f"  Embedding: {entry.get('id', kb_file.stem)}")
        logger.info(f"    Text ({len(search_text)} chars): {search_text[:100]}...")

        # Compute embedding
        embedding = model.encode(search_text, convert_to_numpy=True)
        entry["embedding"] = embedding.tolist()

        # Write embedding back into the individual KB file
        with open(kb_file, "w") as f:
            json.dump(entry, f, indent=2)
            f.write("\n")

        entries.append(entry)

    # Write consolidated index
    index_data = {
        "model": MODEL_NAME,
        "embedding_dim": len(entries[0]["embedding"]),
        "count": len(entries),
        "entries": entries,
    }

    with open(INDEX_FILE, "w") as f:
        json.dump(index_data, f, indent=2)
        f.write("\n")

    logger.info(f"\n✅ Done! Wrote {len(entries)} entries to {INDEX_FILE}")
    logger.info(f"   Embedding dim: {len(entries[0]['embedding'])}")
    logger.info(f"   Total index size: {INDEX_FILE.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
