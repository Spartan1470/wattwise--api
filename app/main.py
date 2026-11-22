"""WattWise API: CORS abierto, POST /extract-pdf y POST /analyze."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import __version__, ai_advisor, extractor, ml_engine, optimizer, rag_engine, rules_engine
from app.extractor import ScannedPdfError
from app.schemas import AnalyzeRequest, AnalyzeResponse, ExtractPDFResponse, HealthResponse, NarrativaIA

load_dotenv()

app = FastAPI(
    title="WattWise API",
    version=__version__,
    description="Backend híbrido para facturas digitales EPM (Colombia).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    index = rag_engine.load_index()
    return HealthResponse(
        status="ok",
        version=__version__,
        gemini=bool(os.getenv("GEMINI_API_KEY"))
        and os.getenv("WATTWISE_ENABLE_GEMINI", "1") not in {"0", "false"},
        ml=ml_engine.MODEL_PATH.exists(),
        rag_chunks=len(index.get("chunks") or []),
    )


@app.post("/extract-pdf", response_model=ExtractPDFResponse)
async def extract_pdf(file: UploadFile = File(...)) -> ExtractPDFResponse:
    nombre = (file.filename or "").lower()
    if not nombre.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF.")
    contenido = await file.read()
    try:
        return extractor.extract_from_bytes(contenido)
    except ScannedPdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el PDF: {exc}") from exc


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    reglas = rules_engine.analizar(req)
    ml = ml_engine.inferir(req, reglas)
    plan, ahorro_kwh, ahorro_cop = optimizer.optimizar(req, reglas)
    rag = rag_engine.retrieve(req, reglas, k=3)

    respuesta = AnalyzeResponse(
        resumen_financiero=reglas.resumen,
        analisis_subsidio=reglas.subsidio,
        analitica_ml=ml,
        desglose_equipos=reglas.desglose,
        plan_ahorro=plan,
        ahorro_total_optimizado_kwh=ahorro_kwh,
        ahorro_total_optimizado_cop=ahorro_cop,
        narrativa_ia=NarrativaIA(
            explicacion_factura="",
            alerta_pedagogica="",
            explicacion_cobros_externos="",
            recomendacion_general="",
        ),
        verificacion_ciclo_anterior=reglas.verificacion,
    )
    respuesta.narrativa_ia = ai_advisor.advise(respuesta, rag, reglas.cambios_mes)
    return respuesta
