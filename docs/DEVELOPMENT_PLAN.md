# Development Plan — WattWise API (Sprint de 6 Horas)

## Fase 1: Setup e Inspección del Lote de Facturas (30 min)

1. Inicializa entorno virtual (`python -m venv .venv`), instala dependencias (`fastapi uvicorn pdfplumber scikit-learn pandas numpy joblib google-genai python-multipart python-dotenv`) y crea `.env` con `GEMINI_API_KEY`.
2. **Prompt para Cursor:**
   > "Lee @docs/PRD.md y @docs/CONTEXT.md. Crea `requirements.txt`, `.env.example`, `app/schemas.py` con todos los modelos Pydantic v2 de entrada/salida, y un script `scripts/inspect_pdfs.py` que recorra todos los PDF en `data/facturas_epm/`, extraiga el texto con `pdfplumber` e imprima en consola los bloques clave (municipio, estrato, periodo, días, energía kWh, valor energía, total a pagar y tabla histórica) para validar variaciones de formato."

## Fase 2: Extractor Determinístico de PDFs EPM (45 min)

1. Revisa la salida de `scripts/inspect_pdfs.py` sobre tus facturas reales.
2. **Prompt para Cursor:**
   > "Implementa `app/extractor.py` usando `pdfplumber` y expresiones regulares robustas para extraer todos los campos de `ExtractPDFResponse` a partir de facturas PDF digitales de EPM según @docs/CONTEXT.md. Incluye un diccionario de municipios colombianos a >= 1000 m.s.n.m. (Valle de Aburrá, Oriente Antioqueño, Bogotá, etc.) para calcular `altitud_mayor_1000m`, sanitización estricta para descartar nombre, cédula, dirección y contrato (Ley 1581), y manejo de error HTTP 422 si el PDF es escaneado sin texto."

## Fase 3: Entrenamiento del Modelo ML (`scikit-learn`) con Facturas Reales (45 min)

1. Aprovecha el historial de 6 meses incluido en cada PDF para multiplicar el dataset de entrenamiento.
2. **Prompt para Cursor:**
   > "Crea `scripts/train_ml.py` y `app/ml_engine.py`. El script debe leer todas las facturas reales en `data/facturas_epm/` usando `app/extractor.py`, expandir cada factura con su vector `historico_kwh` para construir un dataset tabular (`kwh_dia`, `estrato`, `altitud_mayor_1000m`, `mes_relativo`), y entrenar: (1) un `IsolationForest` para detección de consumo anómalo por estrato, y (2) un modelo de regresión (`Ridge` o `RandomForestRegressor`) para predecir el consumo del próximo mes. Imprime métricas de validación (MAE y % de anomalías detectadas) para la sustentación y guarda los artefactos en `models/wattwise_ml.joblib`."

## Fase 4: Motor Determinístico, Optimizador Knapsack y Mini-RAG (60 min)

1. **Prompt para Cursor:**
   > "Implementa tres módulos según @docs/CONTEXT.md y @docs/PRD.md:
   > 1. `app/rules_engine.py`: calcula subsidio UPME 0355 (130/173 kWh), kWh sin subsidio, sobrecosto, consumo mensual por equipo desde las 8 respuestas del cuestionario, consumo standby y verificación Mes 1 vs Mes 2 cuando `ciclo_anterior` no es nulo.
   > 2. `app/optimizer.py`: genera acciones candidatas personalizadas según los equipos/hábitos del usuario y resuelve un problema de optimización combinatoria (Knapsack exacto) para seleccionar las acciones que cumplan `meta_ahorro` y prioricen bajar del umbral de subsistencia.
   > 3. `data/normativa_colombia.json`, `scripts/build_rag.py` y `app/rag_engine.py`: 15 fragmentos regulatorios colombianos (UPME 0355, subsidios CREG, Ley 142 lectura estimada, cobros de otras entidades y cuentas vencidas en EPM) con embeddings de `google-genai` guardados en JSON y búsqueda por similitud coseno en NumPy (con fallback TF-IDF)."

## Fase 5: Agente Narrativo con Gemini 2.5 Flash y Ensamblaje FastAPI (45 min)

1. **Prompt para Cursor:**
   > "Implementa `app/ai_advisor.py` usando `google-genai` (`gemini-2.5-flash`) con Structured Output (`response_schema`) para generar el bloque `narrativa_ia` a partir del JSON ya calculado y los 3 fragmentos recuperados por `rag_engine.py`, prohibiendo inventar cifras y exigiendo explicar diferencias entre valor de energía y otros cobros/vencidas. Luego conecta `POST /extract-pdf` y `POST /analyze` en `app/main.py` con CORS abierto y fallback determinístico si falla Gemini."

## Fase 6: Pruebas End-to-End y Despliegue en Render (30 min)

1. Prueba ambos endpoints desde `http://localhost:8000/docs` usando 3 facturas reales distintas y simula un Mes 2 enviando `ciclo_anterior`.
2. Sube el repo a GitHub y créalo como Web Service gratuito en **Render** (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`). Define `GEMINI_API_KEY` como secret. Verifica `/docs` y `/health` en el HTTPS de Render.

## Comandos locales

El antivirus puede bloquear el shell embebido de Cursor. Usar la terminal integrada del IDE:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python scripts/inspect_pdfs.py
python scripts/build_rag.py
python scripts/train_ml.py
uvicorn app.main:app --reload --port 8000
```

Los PDF reales del equipo están en `facturas epm/`; los scripts también recorren `data/facturas_epm/`.
