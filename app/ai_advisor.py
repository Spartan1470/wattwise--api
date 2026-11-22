"""Gemini 2.5 Flash Structured Output. Solo redacta; no calcula."""

from __future__ import annotations

import json
import os

from app.schemas import AnalyzeResponse, NarrativaIA


def _payload(base: AnalyzeResponse, rag: list[dict], cambios_mes: str | None) -> dict:
    return {
        "resumen_financiero": base.resumen_financiero.model_dump(),
        "analisis_subsidio": base.analisis_subsidio.model_dump(),
        "analitica_ml": base.analitica_ml.model_dump(),
        "desglose_equipos": [d.model_dump() for d in base.desglose_equipos],
        "plan_ahorro": [a.model_dump() for a in base.plan_ahorro if a.prioridad != 99],
        "ahorro_total_optimizado_kwh": base.ahorro_total_optimizado_kwh,
        "ahorro_total_optimizado_cop": base.ahorro_total_optimizado_cop,
        "verificacion_ciclo_anterior": base.verificacion_ciclo_anterior.model_dump()
        if base.verificacion_ciclo_anterior
        else None,
        "cambios_mes": cambios_mes,
        "rag": rag,
    }


def fallback(base: AnalyzeResponse, cambios_mes: str | None = None) -> NarrativaIA:
    rf = base.resumen_financiero
    sub = base.analisis_subsidio
    energia = rf.valor_energia_cop
    otros = rf.otros_cobros_y_vencidas_cop
    pct = rf.porcentaje_energia_sobre_total
    expl = (
        f"De esta factura, la energía es {energia} COP"
        + (f" ({pct} % del total a pagar)." if pct is not None else ".")
        + (
            f" El resto ({otros} COP) incluye acueducto, gas, cuentas vencidas u otras entidades; "
            "no es consumo de kWh de este ciclo."
            if otros is not None
            else ""
        )
    )
    if sub.aplica_subsidio and sub.supera_umbral:
        alerta = (
            f"Consumiste {sub.kwh_consumidos} kWh y el umbral UPME 0355 es {sub.umbral_subsistencia_kwh:.0f} kWh. "
            f"{sub.kwh_sin_subsidio} kWh salen del subsidio"
            + (
                f" (sobrecosto estimado {sub.sobrecosto_por_excedente_cop} COP)."
                if sub.sobrecosto_por_excedente_cop is not None
                else "."
            )
        )
    elif sub.aplica_subsidio:
        alerta = (
            f"Sigues bajo el umbral de {sub.umbral_subsistencia_kwh:.0f} kWh. "
            "El siguiente tramo pierde el descuento de subsistencia."
        )
    else:
        alerta = "Este estrato no recibe subsidio de subsistencia sobre el bloque básico."
    if cambios_mes:
        alerta += f" Contexto del hogar: {cambios_mes}."
    cobros = (
        "Cuentas vencidas y otras entidades (seguros, créditos) no dependen del kWh de este mes. "
        "Separarlas del valor de energía evita la ilusión de que 'la luz está carísima'."
    )
    top = next((a for a in base.plan_ahorro if a.prioridad == 1), None)
    reco = (
        f"Prioriza: {top.accion} (ahorro simulado {top.ahorro_kwh} kWh)."
        if top
        else "Completa el cuestionario de equipos para armar un plan de ahorro."
    )
    return NarrativaIA(
        explicacion_factura=expl,
        alerta_pedagogica=alerta,
        explicacion_cobros_externos=cobros,
        recomendacion_general=reco,
    )


def advise(base: AnalyzeResponse, rag: list[dict], cambios_mes: str | None) -> NarrativaIA:
    if os.getenv("WATTWISE_ENABLE_GEMINI", "1") in {"0", "false", "False"}:
        return fallback(base, cambios_mes)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return fallback(base, cambios_mes)

    modelo = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    datos = _payload(base, rag, cambios_mes)
    prompt = (
        "Eres el asesor pedagógico de WattWise (Colombia). Español claro. "
        "PROHIBIDO inventar, redondear o recalcular kWh, pesos o umbrales: copia las cifras del JSON. "
        "Si un campo es null, dilo. Explica la diferencia entre valor de energía y "
        "cuentas vencidas / otras entidades / acueducto-gas. "
        "Usa los fragmentos rag para citar UPME 0355 o Ley 142 sin contradecirlos.\n\n"
        f"{json.dumps(datos, ensure_ascii=False)}"
    )
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=NarrativaIA.model_json_schema(),
                temperature=0.2,
            ),
        )
        return NarrativaIA.model_validate_json(response.text or "{}")
    except Exception:
        return fallback(base, cambios_mes)
