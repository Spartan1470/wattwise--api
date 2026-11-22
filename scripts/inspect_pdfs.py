"""Inspecciona el lote EPM: texto extraíble y bloques clave del layout."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.extractor import MIN_CHARS_TEXTO, extraer_texto, extract_from_bytes  # noqa: E402

LOTES = [
    ROOT / "data" / "facturas_epm",
    ROOT / "facturas epm",
    ROOT / "facturas epm" / "facturas epm",
]


def _pdfs() -> list[Path]:
    vistos: set[Path] = set()
    out: list[Path] = []
    for d in LOTES:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.suffix.lower() == ".pdf" and p.resolve() not in vistos:
                vistos.add(p.resolve())
                out.append(p)
    return sorted(out)


def _snippet(texto: str, patron: str, n: int = 120) -> str | None:
    m = re.search(patron, texto, re.I)
    if not m:
        return None
    i = max(0, m.start() - 20)
    return re.sub(r"\s+", " ", texto[i : m.end() + n])[:n]


def main() -> None:
    files = _pdfs()
    print(f"PDFs encontrados: {len(files)}")
    filas = []
    digitales = 0
    for path in files:
        rec: dict = {"archivo": str(path.relative_to(ROOT)), "digital": False}
        try:
            contenido = path.read_bytes()
            texto = extraer_texto(contenido)
            rec["chars"] = len(texto)
            rec["digital"] = len(re.sub(r"\s+", "", texto)) >= MIN_CHARS_TEXTO
            rec["bloques"] = {
                "municipio_estrato": _snippet(texto, r"Estrato:\s*\d|Provisional"),
                "periodo": _snippet(texto, r"Periodo de consumo|Consumo del"),
                "dias": _snippet(texto, r"D[ií]as de consumo"),
                "energia": _snippet(texto, r"Energ[ií]a\s+\d"),
                "total": _snippet(texto, r"Total a pagar"),
                "historico": _snippet(texto, r"kwh"),
            }
            if rec["digital"]:
                digitales += 1
                extraido = extract_from_bytes(contenido)
                rec["extract"] = extraido.model_dump()
        except Exception as exc:
            rec["error"] = str(exc)
        filas.append(rec)
        marca = "OK" if rec.get("digital") else "SCAN"
        kwh = (rec.get("extract") or {}).get("consumo_kwh")
        print(f"[{marca}] {rec['archivo']} chars={rec.get('chars')} kWh={kwh}")

    resumen = {"total": len(files), "digitales": digitales}
    print("\nRESUMEN", json.dumps(resumen, ensure_ascii=False))
    out = ROOT / "data" / "inspect_pdfs_report.json"
    out.write_text(json.dumps({"resumen": resumen, "filas": filas}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Reporte: {out}")


if __name__ == "__main__":
    main()
