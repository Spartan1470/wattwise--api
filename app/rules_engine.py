"""Motor determinístico: UPME 0355, cuestionario de 8 preguntas, standby y Mes 2."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import (
    AnalisisSubsidio,
    AnalyzeRequest,
    CuestionarioHogar,
    DesgloseEquipo,
    ExtractPDFResponse,
    ResumenFinanciero,
    UsoDiario,
    VerificacionCiclo,
)

UMBRAL_ALTO = 130.0
UMBRAL_BAJO = 173.0
SUBSIDIO_PCT = {1: 0.60, 2: 0.50, 3: 0.15}

NEVERA_BASE = {
    "Menos de 5 años": 32.0,
    "Entre 5 y 10 años": 45.0,
    "Más de 10 años": 60.0,
    "No sé": 60.0,
}
TV_HORAS = {
    "No tengo televisor": 0.0,
    "Menos de 3 horas": 1.5,
    "Entre 3 y 6 horas": 4.5,
    "Más de 6 horas": 7.5,
}
LAVADORAS = {
    "No tengo lavadora": 0.0,
    "1 o 2 veces": 1.5,
    "3 o 4 veces": 3.5,
    "5 o más veces": 5.5,
}
EQUIPOS_KW = {
    "microondas": 1.20,
    "plancha": 1.20,
    "ventilador": 0.065,
    "computador": 0.12,
    "licuadora": 0.45,
    "ducha_electrica": 3.50,
}
EQUIPOS_NOMBRE = {
    "microondas": "Microondas",
    "plancha": "Plancha",
    "ventilador": "Ventilador",
    "computador": "Computador",
    "licuadora": "Licuadora",
    "ducha_electrica": "Ducha eléctrica",
}
MENOS_1H = {
    "microondas": 0.15,
    "plancha": 0.25,
    "ventilador": 0.5,
    "computador": 0.5,
    "licuadora": 0.10,
    "ducha_electrica": 0.33,
}
STANDBY_W = {
    "Televisor": 8.0,
    "Decodificador": 15.0,
    "Cargadores de celular": 3.0,
    "Computador o cargador de portátil": 10.0,
    "Router de internet": 12.0,
    "Otro": 10.0,
}
META_PCT = {"5 %": 0.05, "10 %": 0.10, "15 % o más": 0.15}
PERSONAS_BASE = {"1 o 2": 90.0, "3 o 4": 130.0, "5 o 6": 180.0, "7 o más": 230.0}


def umbral_subsistencia(altitud_mayor_1000m: bool) -> float:
    return UMBRAL_ALTO if altitud_mayor_1000m else UMBRAL_BAJO


def _horas_uso(clave: str, uso: UsoDiario) -> float:
    if uso == "No lo uso":
        return 0.0
    if uso == "Menos de 1 h":
        return MENOS_1H[clave]
    if uso == "De 1 a 3 h":
        return 2.0
    return 4.0


def _dias(factura: ExtractPDFResponse) -> int:
    return factura.dias_facturados or 30


def desglosar(q: CuestionarioHogar, dias: int, consumo_factura: float | None) -> list[DesgloseEquipo]:
    filas: list[tuple[str, float]] = []

    nevera = q.nevera_etiqueta_kwh_mes if (q.nevera_etiqueta_kwh_mes or 0) > 0 else NEVERA_BASE[q.nevera_antiguedad]
    if q.nevera_cierra_bien == "No":
        nevera *= 1.30
        nombre_nevera = "Nevera (empaque dañado)"
    else:
        nombre_nevera = "Nevera"
    # Etiqueta kWh/mes es para un mes típico de 30 días; escalar a días facturados.
    nevera = nevera * (dias / 30.0)
    filas.append((nombre_nevera, nevera))

    h_tv = TV_HORAS[q.tv_horas_dia]
    if h_tv > 0:
        filas.append(("Televisor", 0.11 * h_tv * dias))

    veces = LAVADORAS[q.lavadora_veces_semana]
    if veces > 0:
        filas.append(("Lavadora", 0.55 * veces * (dias / 7.0)))

    diarios = q.equipos_diarios.model_dump()
    for clave, uso in diarios.items():
        horas = _horas_uso(clave, uso)
        if horas <= 0:
            continue
        filas.append((EQUIPOS_NOMBRE[clave], EQUIPOS_KW[clave] * horas * dias))

    watts = sum(STANDBY_W[item] for item in q.standby)
    if watts > 0:
        filas.append(("Consumo fantasma (standby)", (watts / 1000.0) * 24.0 * dias))

    total_est = sum(k for _, k in filas) or 1.0
    denom = consumo_factura if consumo_factura and consumo_factura > 0 else total_est
    return [
        DesgloseEquipo(
            equipo=nombre,
            kwh_mes=round(kwh, 2),
            porcentaje=round(100.0 * kwh / denom, 1),
            etiqueta="estimado",
        )
        for nombre, kwh in filas
        if kwh > 0
    ]


def resumen_financiero(factura: ExtractPDFResponse) -> ResumenFinanciero:
    energia = factura.valor_energia_cop
    total = factura.valor_total_factura_cop
    otros = None
    if total is not None and energia is not None:
        otros = round(total - energia, 2)
    elif factura.cuentas_vencidas_cop is not None or factura.otras_entidades_cop is not None:
        otros = round((factura.cuentas_vencidas_cop or 0) + (factura.otras_entidades_cop or 0), 2)
    pct = None
    if total and energia is not None and total > 0:
        pct = round(100.0 * energia / total, 1)
    return ResumenFinanciero(
        valor_energia_cop=energia,
        otros_cobros_y_vencidas_cop=otros,
        porcentaje_energia_sobre_total=pct,
        etiqueta="leido",
    )


def analisis_subsidio(factura: ExtractPDFResponse) -> AnalisisSubsidio:
    umbral = umbral_subsistencia(factura.altitud_mayor_1000m)
    consumo = factura.consumo_kwh
    aplica = factura.estrato in (1, 2, 3)
    sin_sub = 0.0
    if aplica and consumo is not None:
        sin_sub = max(0.0, consumo - umbral)
    pct = SUBSIDIO_PCT.get(factura.estrato or 0, 0.0)
    sobrecosto = None
    if aplica and factura.tarifa_kwh_cop is not None:
        sobrecosto = round(sin_sub * factura.tarifa_kwh_cop * pct, 1)
    return AnalisisSubsidio(
        aplica_subsidio=bool(aplica),
        umbral_subsistencia_kwh=umbral,
        kwh_consumidos=consumo,
        kwh_sin_subsidio=round(sin_sub, 2),
        sobrecosto_por_excedente_cop=sobrecosto,
        supera_umbral=bool(aplica and consumo is not None and consumo > umbral),
        etiqueta="leido",
    )


def verificar_ciclo(
    actual: ExtractPDFResponse,
    anterior: ExtractPDFResponse | None,
    meta_pct: float,
) -> VerificacionCiclo | None:
    if anterior is None:
        return None
    c1, c2 = anterior.consumo_kwh, actual.consumo_kwh
    if c1 is None or c2 is None:
        return VerificacionCiclo(
            ahorro_real_kwh=None,
            ahorro_real_cop=None,
            normalizado_por_dias=False,
            cumplimiento_meta=None,
            detalle="Falta consumo leído en uno de los dos ciclos.",
            etiqueta="verificado",
        )
    if actual.tipo_lectura in {"estimada", "promediada"}:
        return VerificacionCiclo(
            ahorro_real_kwh=None,
            ahorro_real_cop=None,
            normalizado_por_dias=False,
            cumplimiento_meta=None,
            detalle=(
                "La factura actual es lectura estimada o promediada (Ley 142): "
                "el usuario puede exigir ajuste contra lectura real. No se marca verificado."
            ),
            etiqueta="verificado",
        )
    d1, d2 = anterior.dias_facturados or 30, actual.dias_facturados or 30
    normalizar = abs(d2 - d1) / max(d1, 1) >= 0.20
    k1, k2 = c1, c2
    if normalizar:
        k1 = c1 / d1 * 30
        k2 = c2 / d2 * 30
    ahorro = round(k1 - k2, 2)
    cop = None
    if actual.tarifa_kwh_cop is not None:
        cop = round(ahorro * actual.tarifa_kwh_cop, 0)
    meta_kwh = k1 * meta_pct
    return VerificacionCiclo(
        ahorro_real_kwh=ahorro,
        ahorro_real_cop=cop,
        normalizado_por_dias=normalizar,
        cumplimiento_meta=ahorro >= meta_kwh * 0.8,
        detalle=(
            f"Ahorro real {ahorro:.1f} kWh "
            f"({'normalizado a 30 días' if normalizar else 'sin normalizar'})."
        ),
        etiqueta="verificado",
    )


@dataclass
class ResultadoReglas:
    resumen: ResumenFinanciero
    subsidio: AnalisisSubsidio
    desglose: list[DesgloseEquipo]
    residuo_kwh: float | None
    consumo_base_esperado: float
    meta_pct: float
    verificacion: VerificacionCiclo | None
    cambios_mes: str | None = None
    rag_hits: list = field(default_factory=list)


def analizar(req: AnalyzeRequest) -> ResultadoReglas:
    dias = _dias(req.factura)
    desglose = desglosar(req.cuestionario, dias, req.factura.consumo_kwh)
    estimado = sum(d.kwh_mes for d in desglose)
    residuo = None
    if req.factura.consumo_kwh is not None:
        residuo = round(req.factura.consumo_kwh - estimado, 2)
    meta = META_PCT[req.cuestionario.meta_ahorro]
    return ResultadoReglas(
        resumen=resumen_financiero(req.factura),
        subsidio=analisis_subsidio(req.factura),
        desglose=desglose,
        residuo_kwh=residuo,
        consumo_base_esperado=PERSONAS_BASE[req.cuestionario.personas],
        meta_pct=meta,
        verificacion=verificar_ciclo(req.factura, req.ciclo_anterior, meta),
        cambios_mes=req.cuestionario.cambios_mes,
    )
