"""IsolationForest + regresor. Fallback estadístico si no hay .joblib."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from app.rules_engine import ResultadoReglas, umbral_subsistencia
from app.schemas import AnaliticaML, AnalyzeRequest

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.getenv("WATTWISE_ML_MODEL", ROOT / "models" / "wattwise_ml.joblib"))

_CACHE: dict | None = None
_TRIED = False


def _cargar() -> dict | None:
    global _CACHE, _TRIED
    if _TRIED:
        return _CACHE
    _TRIED = True
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib

        _CACHE = joblib.load(MODEL_PATH)
    except Exception:
        _CACHE = None
    return _CACHE


def _kwh_dia(req: AnalyzeRequest) -> float:
    kwh = req.factura.consumo_kwh or 0.0
    dias = req.factura.dias_facturados or 30
    return kwh / max(dias, 1)


def _features(req: AnalyzeRequest, mes_relativo: int = 0) -> np.ndarray:
    return np.array(
        [
            [
                _kwh_dia(req),
                float(req.factura.estrato or 0),
                1.0 if req.factura.altitud_mayor_1000m else 0.0,
                float(mes_relativo),
            ]
        ],
        dtype=float,
    )


def _riesgo(prediccion: float | None, umbral: float, aplica: bool, consumo: float | None) -> str:
    if not aplica:
        return "bajo"
    ref = prediccion if prediccion is not None else consumo
    if ref is None:
        return "medio"
    if ref > umbral:
        return "alto"
    if ref >= umbral * 0.90:
        return "medio"
    return "bajo"


def _percentil(consumo: float | None, muestras: list[float] | None) -> int | None:
    if consumo is None or not muestras:
        return None
    arr = np.asarray(muestras, dtype=float)
    return int(round(100.0 * float(np.mean(arr <= consumo))))


def _fallback(req: AnalyzeRequest, reglas: ResultadoReglas) -> AnaliticaML:
    hist = [x for x in req.factura.historico_kwh if x > 0]
    consumo = req.factura.consumo_kwh
    prediccion = None
    anomalo = False
    score = None
    if hist:
        prediccion = round(float(np.mean(hist[-3:])), 1)
        if consumo is not None and len(hist) >= 3:
            media, desv = float(np.mean(hist)), float(np.std(hist))
            if desv > 1e-6:
                z = (consumo - media) / desv
                score = round(z, 3)
                anomalo = abs(z) >= 2.0
    umbral = umbral_subsistencia(req.factura.altitud_mayor_1000m)
    return AnaliticaML(
        es_consumo_anomalo=anomalo,
        score_anomalia=score,
        percentil_estrato=_percentil(consumo, hist),
        prediccion_proximo_mes_kwh=prediccion,
        riesgo_perder_subsidio=_riesgo(  # type: ignore[arg-type]
            prediccion, umbral, reglas.subsidio.aplica_subsidio, consumo
        ),
        etiqueta="estimado",
    )


def inferir(req: AnalyzeRequest, reglas: ResultadoReglas) -> AnaliticaML:
    paquete = _cargar()
    if not paquete:
        return _fallback(req, reglas)
    try:
        x = _features(req)
        forest = paquete["isolation_forest"]
        reg = paquete["regressor"]
        pred = int(forest.predict(x)[0])
        score = float(forest.decision_function(x)[0])
        yhat = max(0.0, float(reg.predict(x)[0]))
        por_estrato = (paquete.get("kwh_por_estrato") or {}).get(str(req.factura.estrato or 0))
        umbral = umbral_subsistencia(req.factura.altitud_mayor_1000m)
        return AnaliticaML(
            es_consumo_anomalo=pred == -1,
            score_anomalia=round(score, 4),
            percentil_estrato=_percentil(req.factura.consumo_kwh, por_estrato),
            prediccion_proximo_mes_kwh=round(yhat, 1),
            riesgo_perder_subsidio=_riesgo(  # type: ignore[arg-type]
                yhat, umbral, reglas.subsidio.aplica_subsidio, req.factura.consumo_kwh
            ),
            etiqueta="estimado",
        )
    except Exception:
        return _fallback(req, reglas)
