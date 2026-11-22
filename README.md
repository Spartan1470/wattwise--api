# WattWise API

Backend FastAPI **stateless** para facturas digitales de energía EPM (Colombia). Extrae el PDF con regex, calcula subsidio UPME 0355, desglosa equipos del cuestionario, detecta anomalías con scikit-learn, arma un plan de ahorro (knapsack) y redacta la explicación con Gemini 2.5 Flash.

La IA **no calcula** kWh ni pesos: solo narra el JSON ya calculado.

## Endpoints

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Estado, Gemini, modelo ML y chunks RAG |
| `POST` | `/extract-pdf` | PDF digital EPM → campos leídos (sin PII) |
| `POST` | `/analyze` | Factura + cuestionario de 8 preguntas → diagnóstico |
| `GET` | `/docs` | Swagger |

PDF foto/escaneo (menos de 50 caracteres de texto) → HTTP **422**.

## Stack

Python 3.11+ · FastAPI · Pydantic v2 · pdfplumber · scikit-learn · NumPy · pandas · `google-genai` (`gemini-2.5-flash`)

## Arranque local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

En `.env` define `GEMINI_API_KEY`. Sin clave, `/analyze` usa el fallback determinístico.

```powershell
python scripts/inspect_pdfs.py
python scripts/build_rag.py
python scripts/train_ml.py
uvicorn app.main:app --reload --port 8000
```

Coloca PDFs digitales de EPM en `data/facturas_epm/` (no se versionan). El lote local `facturas epm/` también lo leen los scripts.

## Arquitectura

1. `extractor.py` — pdfplumber + regex. Ley 1581: no extrae nombre, cédula, dirección ni contrato.
2. `rules_engine.py` — umbral 130/173 kWh, \(E = P \times h \times d\), standby, Mes 2.
3. `ml_engine.py` — IsolationForest + regresor (`models/wattwise_ml.joblib`).
4. `optimizer.py` — knapsack según `meta_ahorro`, prioriza bajar del umbral.
5. `rag_engine.py` — normativa colombiana + coseno NumPy.
6. `ai_advisor.py` — Gemini Structured Output; fallback si falla la API.

Contratos: `docs/PRD.md`. Dominio: `docs/CONTEXT.md`. Plan: `docs/DEVELOPMENT_PLAN.md`.

## Render

`render.yaml` expone `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Configura el secret `GEMINI_API_KEY` en el dashboard.

## Privacidad

El API no guarda el PDF ni tiene base de datos. Las facturas reales y `.env` están en `.gitignore`.
