"""Mini-RAG: embeddings google-genai o TF-IDF; similitud coseno en NumPy."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

from app.rules_engine import ResultadoReglas
from app.schemas import AnalyzeRequest

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = Path(os.getenv("WATTWISE_RAG_INDEX", ROOT / "data" / "rag_index.json"))
NORMATIVA_PATH = Path(os.getenv("WATTWISE_NORMATIVA", ROOT / "data" / "normativa_colombia.json"))

_INDEX: dict | None = None


def _chunks_normativa() -> list[dict]:
    if not NORMATIVA_PATH.exists():
        return []
    data = json.loads(NORMATIVA_PATH.read_text(encoding="utf-8"))
    return data.get("chunks", [])


def _embed_gemini(texts: list[str]) -> list[list[float]] | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        vecs: list[list[float]] = []
        for t in texts:
            r = client.models.embed_content(model="text-embedding-004", contents=t)
            emb = r.embeddings[0].values  # type: ignore[index]
            vecs.append(list(emb))
        return vecs
    except Exception:
        return None


def _embed_tfidf(texts: list[str], vectorizer=None):
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = vectorizer or TfidfVectorizer(max_features=256, ngram_range=(1, 2))
    if vectorizer is None:
        matrix = vec.fit_transform(texts)
    else:
        matrix = vec.transform(texts)
    dense = matrix.toarray().astype(float)
    return vec, dense.tolist()


def construir_indice() -> dict:
    chunks = _chunks_normativa()
    texts = [f"{c.get('titulo', '')} {c.get('texto', '')}" for c in chunks]
    if not texts:
        return {"model": "empty", "chunks": []}
    gem = _embed_gemini(texts)
    if gem:
        model = "text-embedding-004"
        vectors = gem
        tfidf_vocab = None
    else:
        vec, vectors = _embed_tfidf(texts)
        model = "tfidf"
        tfidf_vocab = {
            "vocabulary": vec.vocabulary_,
            "idf": vec.idf_.tolist(),
        }
    out_chunks = []
    for ch, v in zip(chunks, vectors):
        out_chunks.append(
            {
                "id": ch.get("id"),
                "titulo": ch.get("titulo"),
                "fuente": ch.get("fuente"),
                "texto": ch.get("texto"),
                "vector": v,
            }
        )
    return {"model": model, "tfidf": tfidf_vocab, "chunks": out_chunks}


def load_index() -> dict:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    if INDEX_PATH.exists():
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        chunks = data.get("chunks") or []
        if chunks and chunks[0].get("vector"):
            _INDEX = data
            return _INDEX
    _INDEX = construir_indice()
    return _INDEX


def _consulta(req: AnalyzeRequest, reglas: ResultadoReglas) -> str:
    return " ".join(
        [
            "UPME 0355 consumo de subsistencia umbral 130 173",
            f"municipio {req.factura.municipio}",
            f"estrato {req.factura.estrato}",
            f"kWh {req.factura.consumo_kwh}",
            "cuentas vencidas otras entidades total a pagar",
            "lectura estimada Ley 142",
            "subsidio estratos 1 2 3",
            reglas.subsidio.model_dump_json(),
            req.cuestionario.cambios_mes or "",
            "standby consumo fantasma nevera empaque",
        ]
    )


def _vector_consulta(index: dict, texto: str) -> np.ndarray | None:
    chunks = index.get("chunks") or []
    if not chunks:
        return None
    if index.get("model") == "tfidf" and index.get("tfidf"):
        from sklearn.feature_extraction.text import TfidfVectorizer

        vocab = index["tfidf"]["vocabulary"]
        idf = np.asarray(index["tfidf"]["idf"], dtype=float)
        vec = TfidfVectorizer(vocabulary=vocab)
        # idf_ must match fitted vectorizer
        vec.idf_ = idf
        vec._tfidf._idf_diag = None  # type: ignore[attr-defined]
        try:
            q = vec.transform([texto]).toarray()[0]
            return np.asarray(q, dtype=float)
        except Exception:
            pass
    gem = _embed_gemini([texto])
    if gem:
        return np.asarray(gem[0], dtype=float)
    # hashing fallback
    dim = len(chunks[0]["vector"])
    acc = np.zeros(dim, dtype=float)
    for w in re.findall(r"[a-záéíóúñü0-9]+", texto.lower()):
        acc[hash(w) % dim] += 1.0
    n = np.linalg.norm(acc) or 1.0
    return acc / n


def retrieve(req: AnalyzeRequest, reglas: ResultadoReglas, k: int = 3) -> list[dict]:
    index = load_index()
    chunks = index.get("chunks") or []
    q = _vector_consulta(index, _consulta(req, reglas))
    if q is None or not chunks:
        return []
    hits = []
    for ch in chunks:
        v = np.asarray(ch.get("vector") or [], dtype=float)
        if v.size != q.size:
            continue
        denom = float(np.linalg.norm(q) * np.linalg.norm(v)) or 1.0
        score = float(np.dot(q, v) / denom)
        hits.append(
            {
                "id": ch.get("id"),
                "fuente": ch.get("fuente"),
                "score": round(score, 4),
                "texto": (ch.get("texto") or "")[:700],
            }
        )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:k]
