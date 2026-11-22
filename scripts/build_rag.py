"""Genera data/rag_index.json (Gemini embeddings o TF-IDF)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag_engine import INDEX_PATH, NORMATIVA_PATH, construir_indice  # noqa: E402


def main() -> None:
    if not NORMATIVA_PATH.exists():
        raise SystemExit(f"No existe {NORMATIVA_PATH}")
    index = construir_indice()
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
    json.dumps(
        index,
        ensure_ascii=False,
        default=lambda o: o.item() if hasattr(o, "item") else o.tolist(),
    ),
    encoding="utf-8",
)
    print(f"{len(index.get('chunks', []))} chunks model={index.get('model')} → {INDEX_PATH}")


if __name__ == "__main__":
    main()
