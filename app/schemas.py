"""Contratos Pydantic v2. Deben coincidir con docs/PRD.md."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Etiqueta = Literal["leido", "estimado", "simulado", "verificado"]
TipoLectura = Literal["real", "estimada", "promediada"]
Personas = Literal["1 o 2", "3 o 4", "5 o 6", "7 o más"]
NeveraAntiguedad = Literal["Menos de 5 años", "Entre 5 y 10 años", "Más de 10 años", "No sé"]
SiNo = Literal["Sí", "No"]
TvHoras = Literal["No tengo televisor", "Menos de 3 horas", "Entre 3 y 6 horas", "Más de 6 horas"]
LavadoraVeces = Literal["No tengo lavadora", "1 o 2 veces", "3 o 4 veces", "5 o más veces"]
UsoDiario = Literal["No lo uso", "Menos de 1 h", "De 1 a 3 h", "Más de 3 h"]
MetaAhorro = Literal["5 %", "10 %", "15 % o más"]
StandbyItem = Literal[
    "Televisor",
    "Decodificador",
    "Cargadores de celular",
    "Computador o cargador de portátil",
    "Router de internet",
    "Otro",
]
CategoriaAccion = Literal["habito", "mantenimiento", "compra"]
RiesgoSubsidio = Literal["bajo", "medio", "alto"]

_CAMPOS_EQUIPO = (
    "microondas",
    "plancha",
    "ventilador",
    "computador",
    "licuadora",
    "ducha_electrica",
)


def _fold(valor: object) -> str:
    texto = unicodedata.normalize("NFD", str(valor).strip())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.lower()
    texto = re.sub(r"\s*%\s*", "%", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _tabla(*canonicos: str, extras: dict[str, str] | None = None) -> dict[str, str]:
    mapa = {_fold(c): c for c in canonicos}
    if extras:
        mapa.update({_fold(k): v for k, v in extras.items()})
    return mapa


def _remap(valor: object, tabla: dict[str, str]) -> object:
    if not isinstance(valor, str):
        return valor
    return tabla.get(_fold(valor), valor)


_MAP_PERSONAS = _tabla("1 o 2", "3 o 4", "5 o 6", "7 o más")
_MAP_NEVERA = _tabla(
    "Menos de 5 años",
    "Entre 5 y 10 años",
    "Más de 10 años",
    "No sé",
    extras={"no se": "No sé", "mas de 10 anos": "Más de 10 años"},
)
_MAP_SINO = _tabla("Sí", "No", extras={"si": "Sí", "s": "Sí", "n": "No"})
_MAP_TV = _tabla(
    "No tengo televisor",
    "Menos de 3 horas",
    "Entre 3 y 6 horas",
    "Más de 6 horas",
)
_MAP_LAVADORA = _tabla(
    "No tengo lavadora",
    "1 o 2 veces",
    "3 o 4 veces",
    "5 o más veces",
)
_MAP_USO = _tabla(
    "No lo uso",
    "Menos de 1 h",
    "De 1 a 3 h",
    "Más de 3 h",
    extras={
        "menos de 1h": "Menos de 1 h",
        "menos de 1 hora": "Menos de 1 h",
        "de 1 a 3 horas": "De 1 a 3 h",
        "mas de 3 horas": "Más de 3 h",
        "mas de 3 h": "Más de 3 h",
    },
)
_MAP_META = _tabla(
    "5 %",
    "10 %",
    "15 % o más",
    extras={
        "5%": "5 %",
        "10%": "10 %",
        "15%": "15 % o más",
        "5": "5 %",
        "10": "10 %",
        "15": "15 % o más",
        "15% o mas": "15 % o más",
        "15 % o mas": "15 % o más",
    },
)
_MAP_STANDBY = _tabla(
    "Televisor",
    "Decodificador",
    "Cargadores de celular",
    "Computador o cargador de portátil",
    "Router de internet",
    "Otro",
    extras={
        "tv": "Televisor",
        "cargador de celular": "Cargadores de celular",
        "cargadores": "Cargadores de celular",
        "computador": "Computador o cargador de portátil",
        "portatil": "Computador o cargador de portátil",
        "router": "Router de internet",
    },
)


class EquiposDiarios(BaseModel):
    model_config = ConfigDict(extra="ignore")

    microondas: UsoDiario = "No lo uso"
    plancha: UsoDiario = "No lo uso"
    ventilador: UsoDiario = "No lo uso"
    computador: UsoDiario = "No lo uso"
    licuadora: UsoDiario = "No lo uso"
    ducha_electrica: UsoDiario = "No lo uso"

    @model_validator(mode="before")
    @classmethod
    def normalizar_usos(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        return {k: _remap(v, _MAP_USO) if k in _CAMPOS_EQUIPO else v for k, v in data.items()}


class CuestionarioHogar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    personas: Personas
    nevera_antiguedad: NeveraAntiguedad = "No sé"
    nevera_cierra_bien: SiNo = "Sí"
    nevera_etiqueta_kwh_mes: float | None = Field(default=None, ge=0)
    tv_horas_dia: TvHoras
    lavadora_veces_semana: LavadoraVeces
    equipos_diarios: EquiposDiarios = Field(default_factory=EquiposDiarios)
    standby: list[StandbyItem] = Field(default_factory=list)
    meta_ahorro: MetaAhorro = "10 %"
    cambios_mes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalizar_literales(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        campos = {
            "personas": _MAP_PERSONAS,
            "nevera_antiguedad": _MAP_NEVERA,
            "nevera_cierra_bien": _MAP_SINO,
            "tv_horas_dia": _MAP_TV,
            "lavadora_veces_semana": _MAP_LAVADORA,
            "meta_ahorro": _MAP_META,
        }
        for campo, tabla in campos.items():
            if campo in out:
                out[campo] = _remap(out[campo], tabla)
        if isinstance(out.get("equipos_diarios"), dict):
            out["equipos_diarios"] = {
                k: _remap(v, _MAP_USO) if k in _CAMPOS_EQUIPO else v
                for k, v in out["equipos_diarios"].items()
            }
        if isinstance(out.get("standby"), list):
            out["standby"] = [_remap(item, _MAP_STANDBY) for item in out["standby"]]
        return out


class ExtractPDFResponse(BaseModel):
    consumo_kwh: float | None = Field(default=None, ge=0)
    periodo_facturado: str | None = None
    dias_facturados: int | None = Field(default=None, ge=1, le=62)
    valor_energia_cop: float | None = Field(default=None, ge=0)
    valor_total_factura_cop: float | None = Field(default=None, ge=0)
    cuentas_vencidas_cop: float | None = Field(default=None, ge=0)
    otras_entidades_cop: float | None = Field(default=None, ge=0)
    estrato: int | None = Field(default=None, ge=1, le=6)
    estrato_provisional: bool = False
    municipio: str | None = None
    altitud_mayor_1000m: bool = True
    tipo_lectura: TipoLectura = "real"
    tarifa_kwh_cop: float | None = Field(default=None, ge=0)
    historico_kwh: list[float] = Field(default_factory=list)
    etiqueta: Literal["leido"] = "leido"


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    factura: ExtractPDFResponse
    cuestionario: CuestionarioHogar
    ciclo_anterior: ExtractPDFResponse | None = None


class ResumenFinanciero(BaseModel):
    valor_energia_cop: float | None
    otros_cobros_y_vencidas_cop: float | None
    porcentaje_energia_sobre_total: float | None
    etiqueta: Etiqueta = "leido"


class AnalisisSubsidio(BaseModel):
    aplica_subsidio: bool
    umbral_subsistencia_kwh: float
    kwh_consumidos: float | None
    kwh_sin_subsidio: float
    sobrecosto_por_excedente_cop: float | None
    supera_umbral: bool
    etiqueta: Etiqueta = "leido"


class AnaliticaML(BaseModel):
    es_consumo_anomalo: bool
    score_anomalia: float | None = None
    percentil_estrato: int | None = None
    prediccion_proximo_mes_kwh: float | None = None
    riesgo_perder_subsidio: RiesgoSubsidio = "medio"
    etiqueta: Literal["estimado"] = "estimado"


class DesgloseEquipo(BaseModel):
    equipo: str
    kwh_mes: float
    porcentaje: float
    etiqueta: Literal["estimado"] = "estimado"


class AccionPlan(BaseModel):
    id: str
    prioridad: int
    accion: str
    categoria: CategoriaAccion
    requiere_inversion: bool
    ahorro_kwh: float
    ahorro_cop: float | None
    ayuda_recuperar_subsidio: bool
    etiqueta: Literal["estimado"] = "estimado"


class NarrativaIA(BaseModel):
    explicacion_factura: str
    alerta_pedagogica: str
    explicacion_cobros_externos: str
    recomendacion_general: str


class VerificacionCiclo(BaseModel):
    ahorro_real_kwh: float | None
    ahorro_real_cop: float | None
    normalizado_por_dias: bool
    cumplimiento_meta: bool | None
    etiqueta: Literal["verificado"] = "verificado"
    detalle: str


class AnalyzeResponse(BaseModel):
    resumen_financiero: ResumenFinanciero
    analisis_subsidio: AnalisisSubsidio
    analitica_ml: AnaliticaML
    desglose_equipos: list[DesgloseEquipo]
    plan_ahorro: list[AccionPlan]
    ahorro_total_optimizado_kwh: float
    ahorro_total_optimizado_cop: float | None
    narrativa_ia: NarrativaIA
    verificacion_ciclo_anterior: VerificacionCiclo | None


class HealthResponse(BaseModel):
    status: str
    version: str
    gemini: bool
    ml: bool
    rag_chunks: int
