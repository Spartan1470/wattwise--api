"""Entrena IsolationForest + RandomForestRegressor con facturas reales."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.extractor import extraer_texto, extract_from_bytes  # noqa: E402
from app.ml_engine import MODEL_PATH  # noqa: E402

LOTES = [
    ROOT / "data" / "facturas_epm",
    ROOT / "facturas epm",
    ROOT / "facturas epm" / "facturas epm",
]
COLS = ["kwh_dia", "estrato", "altitud_mayor_1000m", "mes_relativo"]


def _pdfs() -> list[Path]:
    vistos: set[Path] = set()
    out: list[Path] = []
    for d in LOTES:
        if not d.exists():
            continue
        for p in list(d.rglob("*.pdf")) + list(d.rglob("*.PDF")):
            rp = p.resolve()
            if rp not in vistos:
                vistos.add(rp)
                out.append(p)
    return out


def main() -> None:
    filas = []
    kwh_por_estrato: dict[str, list[float]] = {}
    for path in _pdfs():
        try:
            contenido = path.read_bytes()
            if len(re.sub(r"\s+", "", extraer_texto(contenido))) < 50:
                continue
            extraido = extract_from_bytes(contenido)
        except Exception:
            continue
        if extraido.consumo_kwh is None:
            continue
        serie = list(extraido.historico_kwh or [])
        if extraido.consumo_kwh not in serie:
            serie = serie + [extraido.consumo_kwh]
        dias = extraido.dias_facturados or 30
        estrato = extraido.estrato or 0
        alt = 1 if extraido.altitud_mayor_1000m else 0
        kwh_por_estrato.setdefault(str(estrato), []).append(extraido.consumo_kwh)
        for i, kwh in enumerate(serie):
            filas.append(
                {
                    "kwh_dia": kwh / dias,
                    "estrato": estrato,
                    "altitud_mayor_1000m": alt,
                    "mes_relativo": i - (len(serie) - 1),
                    "kwh": kwh,
                }
            )

    if len(filas) < 8:
        raise SystemExit(
            f"Solo {len(filas)} filas (histórico expandido). Se necesitan ≥8. "
            "Revisa scripts/inspect_pdfs.py y data/facturas_epm/."
        )

    df = pd.DataFrame(filas)
    X = df[COLS]
    y = df["kwh"]
    forest = IsolationForest(contamination=0.12, random_state=42)
    forest.fit(X)
    flags = forest.predict(X)
    pct_anom = 100.0 * float(np.mean(flags == -1))

    reg = RandomForestRegressor(n_estimators=80, max_depth=6, random_state=42)
    # Predice el siguiente kWh con las features del mes actual (objetivo = kwh).
    n = len(df)
    split = max(1, int(n * 0.8))
    reg.fit(X.iloc[:split], y.iloc[:split])
    pred = reg.predict(X.iloc[split:] if split < n else X)
    truth = y.iloc[split:] if split < n else y
    mae = float(mean_absolute_error(truth, pred))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(
        {
            "isolation_forest": forest,
            "regressor": reg,
            "feature_names": COLS,
            "kwh_por_estrato": kwh_por_estrato,
            "n_samples": len(df),
            "mae": mae,
            "pct_anomalias": pct_anom,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        },
        MODEL_PATH,
    )
    print(f"n={len(df)} MAE={mae:.2f} kWh  anomalías={pct_anom:.1f}%  → {MODEL_PATH}")


if __name__ == "__main__":
    main()
