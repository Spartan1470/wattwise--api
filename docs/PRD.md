# PRD — WattWise Hybrid AI Backend

## 1. Objetivo del Producto

Proveer una API REST stateless en Python que transforme facturas residenciales de energía eléctrica en PDF digital (EPM - Colombia) y un cuestionario de hábitos del hogar en un diagnóstico energético interpretable, detección estadística de anomalías, pronóstico de consumo, plan de ahorro optimizado y verificación ciclo a ciclo.

## 2. Problema que Resuelve (Hallazgos de Facturas Reales)

1. **Ilusión de ahorro:** Una factura puede mostrar indicador verde ("Disminuyó", ej. 166 kWh), pero en estratos 1–3 de municipios a ≥ 1.000 m.s.n.m. sigue superando el umbral de subsistencia (130 kWh), pagando 36 kWh sin subsidio.
2. **Distorsión financiera en el total a pagar:** La factura integra Acueducto, Alcantarillado, Gas, *Cuentas Vencidas* y *Otras entidades*, haciendo creer al usuario que el costo elevado proviene exclusivamente del consumo de energía.
3. **Consumo invisible:** El usuario desconoce qué electrodomésticos o fugas (ej. empaque de nevera dañado o cargas standby) explican el consumo facturado.

## 3. Alcance del Backend (Solo 2 Endpoints)

- **Frontend & Persistencia (fuera de este repo):** Desarrollado por el equipo estudiantil en Google Antigravity + Supabase/Firestore. Incluye checkboxes interactivos en el plan de ahorro (reemplazando cualquier chatbot).
- **Backend IA (este repo):** Desplegado en Render, expuesto vía HTTPS con Swagger en `/docs`.

### Endpoint 1: `POST /extract-pdf`

- **Input:** `multipart/form-data` con campo `file` (`.pdf` digital de EPM).
- **Validación:** Si `extract_text()` devuelve vacío o < 50 caracteres, retornar HTTP `422` indicando que solo se soportan PDFs digitales con texto seleccionable (no fotos/escaneos).
- El archivo se lee en `BytesIO` y **nunca** se escribe a disco ni se extrae nombre, cédula/NIT, dirección o número de contrato (Ley 1581 de 2012).
- **Output (`ExtractPDFResponse`):**

```json
{
  "consumo_kwh": 166.0,
  "periodo_facturado": "18 Mar al 18 Abr",
  "dias_facturados": 31,
  "valor_energia_cop": 66566.9,
  "valor_total_factura_cop": 243683.4,
  "cuentas_vencidas_cop": 138945.19,
  "otras_entidades_cop": 19784.5,
  "estrato": 2,
  "estrato_provisional": false,
  "municipio": "Sabaneta",
  "altitud_mayor_1000m": true,
  "tipo_lectura": "real",
  "tarifa_kwh_cop": 890.5,
  "historico_kwh": [182.0, 175.0, 179.0, 171.0, 174.0, 166.0],
  "etiqueta": "leido"
}
```

### Endpoint 2: `POST /analyze`

- **Input (`AnalyzeRequest`):** Datos confirmados de la factura actual + respuestas del cuestionario de 8 preguntas + ciclo anterior opcional (`null` en Mes 1).
- **Pipeline interno:**
  1. **Motor de Reglas:** umbral UPME (130 o 173 kWh), kWh sin subsidio, sobrecosto perdido, consumo por equipo \(E = P \times h \times d\), fantasma y residuo inexplicado. Si `ciclo_anterior != null`, ahorro real normalizado por días (verificado).
  2. **Motor ML (scikit-learn):** anomalía (IsolationForest) frente a hogares del mismo estrato; `prediccion_proximo_mes_kwh` + `riesgo_perder_subsidio`.
  3. **Optimizador (Knapsack):** subconjunto de acciones según `meta_ahorro` (5 %, 10 %, 15 %+) priorizando bajar del umbral de subsistencia.
  4. **Mini-RAG + Gemini 2.5 Flash:** normativa (UPME 0355, CREG, Ley 142) y explicación en JSON estructurado. Gemini no recalcula cifras.

- **Output (`AnalyzeResponse`):**

```json
{
  "resumen_financiero": {
    "valor_energia_cop": 66566.9,
    "otros_cobros_y_vencidas_cop": 177116.5,
    "porcentaje_energia_sobre_total": 27.3,
    "etiqueta": "leido"
  },
  "analisis_subsidio": {
    "aplica_subsidio": true,
    "umbral_subsistencia_kwh": 130,
    "kwh_consumidos": 166.0,
    "kwh_sin_subsidio": 36.0,
    "sobrecosto_por_excedente_cop": 16029.0,
    "supera_umbral": true,
    "etiqueta": "leido"
  },
  "analitica_ml": {
    "es_consumo_anomalo": true,
    "score_anomalia": -0.14,
    "percentil_estrato": 82,
    "prediccion_proximo_mes_kwh": 163.5,
    "riesgo_perder_subsidio": "alto",
    "etiqueta": "estimado"
  },
  "desglose_equipos": [
    { "equipo": "Nevera (empaque dañado)", "kwh_mes": 58.5, "porcentaje": 35.2, "etiqueta": "estimado" },
    { "equipo": "Ducha eléctrica", "kwh_mes": 35.0, "porcentaje": 21.1, "etiqueta": "estimado" },
    { "equipo": "Consumo fantasma (standby)", "kwh_mes": 14.2, "porcentaje": 8.6, "etiqueta": "estimado" }
  ],
  "plan_ahorro": [
    {
      "id": "act_1",
      "prioridad": 1,
      "accion": "Cambiar el empaque magnético de la puerta de la nevera",
      "categoria": "mantenimiento",
      "requiere_inversion": true,
      "ahorro_kwh": 16.0,
      "ahorro_cop": 14248.0,
      "ayuda_recuperar_subsidio": true,
      "etiqueta": "estimado"
    }
  ],
  "ahorro_total_optimizado_kwh": 38.0,
  "ahorro_total_optimizado_cop": 33839.0,
  "narrativa_ia": {
    "explicacion_factura": "...",
    "alerta_pedagogica": "...",
    "explicacion_cobros_externos": "...",
    "recomendacion_general": "..."
  },
  "verificacion_ciclo_anterior": null
}
```

## 4. Arquitectura híbrida

1. Extraer (regex) → 2. Reglas + ML + Knapsack + RAG → 3. Gemini redacta `narrativa_ia`.
2. Si Gemini falla (cuota/red), el fallback determinístico llena el mismo `AnalyzeResponse`.
3. API stateless. CORS abierto. Swagger en `/docs`.

## 5. Criterios de aceptación

- PDF digital EPM extrae al menos `consumo_kwh` o el par energía/valor.
- Foto o escaneo → 422, sin llamar a Gemini.
- Sabaneta / Medellín / Envigado → `altitud_mayor_1000m: true`, umbral 130.
- Estrato 2 y 166 kWh → `kwh_sin_subsidio: 36` y sobrecosto = excedente × CU × % subsidio.
- `otros_cobros_y_vencidas_cop` = total a pagar − valor energía (ilusión del total).
- Gemini no introduce un kWh o peso ausente del JSON de reglas.
