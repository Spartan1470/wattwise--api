"""Extractor determinístico de facturas digitales EPM (pdfplumber + regex). Ley 1581: sin PII."""

from __future__ import annotations

import io
import re
from datetime import date, datetime

import pdfplumber

from app.schemas import ExtractPDFResponse

MIN_CHARS_TEXTO = 50

MUNICIPIOS_MSNM: dict[str, float] = {
    "medellin": 1495,
    "medellín": 1495,
    "bello": 1450,
    "envigado": 1575,
    "itagui": 1550,
    "itagüí": 1550,
    "sabaneta": 1550,
    "la estrella": 1775,
    "copacabana": 1305,
    "girardota": 1325,
    "barbosa": 1325,
    "rionegro": 2130,
    "la ceja": 2200,
    "marinilla": 2100,
    "bogota": 2640,
    "bogotá": 2640,
    "santa fe de antioquia": 550,
    "apartado": 25,
    "apartadó": 25,
    "turbo": 2,
    "caucasia": 50,
    "barranquilla": 18,
    "cartagena": 2,
    "santa marta": 2,
    "cali": 1018,
    "bucaramanga": 959,
}

_PII_PATTERNS = [
    re.compile(r"(?:c[eé]dula|nit|cc)\s*[:\-]?\s*[\d.]+", re.I),
    re.compile(r"(?:contrato|cuenta\s+contrato)\s*[:\-]?\s*[\d\-]+", re.I),
    re.compile(r"(?:direcci[oó]n(?:\s+de\s+cobro)?)\s*[:\-].+", re.I),
    re.compile(r"(?:se[ñn]or(?:es)?|titular)\s*[:\-].+", re.I),
]

_RE_MUNI_ESTRATO = re.compile(
    r"([A-ZÁÉÍÓÚÑÜ][A-Za-záéíóúñüÁÉÍÓÚÑÜ\s]+?)\s*[-–]\s*"
    r"(?:Antioquia|Cundinamarca|Valle(?:\s+del\s+Cauca)?|Atl[aá]ntico|Bol[ií]var|Magdalena)"
    r".{0,40}Estrato:\s*(\d|Provisional)",
    re.I,
)
_RE_ESTRATO = re.compile(r"Estrato:\s*(\d|Provisional)", re.I)
_RE_MUNICIPIO_LINEA = re.compile(
    r"\b(Medell[ií]n|Bello|Envigado|Itag[uü][ií]|Sabaneta|La Estrella|Copacabana|"
    r"Girardota|Barbosa|Rionegro|La Ceja|Marinilla|Bogot[aá]|Apartad[oó]|Turbo|"
    r"Caucasia|Barranquilla|Cartagena|Santa Marta|Cali|Bucaramanga|"
    r"Santa Fe de Antioquia)\b",
    re.I,
)
_RE_PERIODO = re.compile(
    r"(?:Periodo(?:\s+de\s+consumo)?|Consumo(?:\s+del)?)\s*[:\-]?\s*"
    r"(?:Consumo\s+del\s+)?(\d{1,2}\s+[A-Za-záéíóú]{3,9}\s+al\s+\d{1,2}\s+[A-Za-záéíóú]{3,9})",
    re.I,
)
_RE_DIAS = re.compile(r"D[ií]as\s+de\s+consumo\s*[:\-]?\s*(\d{1,2})", re.I)
_RE_ENERGIA = re.compile(
    r"Energ[ií]a\s+([\d]{1,4}(?:[.,]\d+)?)\s*kwh\s*\$?\s*([\d]{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)",
    re.I,
)
_RE_CONSUMO_KWH = re.compile(r"\b([\d]{2,4}(?:[.,]\d+)?)\s*kwh\b", re.I)
_RE_CUENTAS_VENCIDAS = re.compile(
    r"Cuentas\s+Vencidas\s*\$?\s*([\d]{1,3}(?:\.\d{3})*(?:,\d+)?)",
    re.I,
)
_RE_OTRAS_ENTIDADES = re.compile(
    r"Otras\s+entidades\s*\$?\s*([\d]{1,3}(?:\.\d{3})*(?:,\d+)?)",
    re.I,
)
_RE_TOTAL = re.compile(
    r"Total\s+a\s+pagar\s*\$?\s*([\d]{1,3}(?:\.\d{3})*(?:,\d+)?)",
    re.I,
)
_RE_TARIFA = re.compile(
    r"(?:Costo\s+unitario|Valor\s+unitario|\$\s*/\s*kwh|\$\/kwh)\s*[:\-]?\s*\$?\s*"
    r"([\d]{2,4}(?:[.,]\d+)?)",
    re.I,
)
_RE_ESTIMADA = re.compile(r"\b(estimad[oa]|promediad[oa]|sin\s+lectura)\b", re.I)
# Miles colombianos: 314.382, 1.250.000 (puntos de 3 dígitos, sin coma decimal).
_RE_MILES_CO = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_RE_PERIODO_FECHAS = re.compile(
    r"(\d{1,2})\s+([A-Za-záéíóúñ]{3,10})\s+al\s+(\d{1,2})\s+([A-Za-záéíóúñ]{3,10})",
    re.I,
)
_MESES = {
    "ene": 1,
    "enero": 1,
    "feb": 2,
    "febrero": 2,
    "mar": 3,
    "marzo": 3,
    "abr": 4,
    "abril": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "jul": 7,
    "julio": 7,
    "ago": 8,
    "agosto": 8,
    "sep": 9,
    "set": 9,
    "septiembre": 9,
    "setiembre": 9,
    "oct": 10,
    "octubre": 10,
    "nov": 11,
    "noviembre": 11,
    "dic": 12,
    "diciembre": 12,
}


class ScannedPdfError(ValueError):
    """PDF sin texto seleccionable (foto o escaneo)."""


def parse_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".") if len(s.split(",")[-1]) <= 2 else s.replace(",", "")
    elif _RE_MILES_CO.fullmatch(s):
        s = s.replace(".", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _mes_numero(token: str) -> int | None:
    clave = token.strip().lower()
    if clave in _MESES:
        return _MESES[clave]
    return _MESES.get(clave[:3])


def dias_desde_periodo(periodo: str | None) -> int | None:
    """Diferencia de días en '17 feb al 18 mar'. None si no se puede parsear."""
    if not periodo:
        return None
    m = _RE_PERIODO_FECHAS.search(periodo)
    if not m:
        return None
    d1, mes1, d2, mes2 = int(m.group(1)), _mes_numero(m.group(2)), int(m.group(3)), _mes_numero(m.group(4))
    if mes1 is None or mes2 is None:
        return None
    anio = datetime.now().year

    def _fecha(dia: int, mes: int, anio_ref: int) -> date | None:
        try:
            return date(anio_ref, mes, dia)
        except ValueError:
            try:
                return date(2024, mes, dia)
            except ValueError:
                return None

    inicio = _fecha(d1, mes1, anio)
    fin = _fecha(d2, mes2, anio)
    if inicio is None or fin is None:
        return None
    if fin <= inicio:
        fin = _fecha(d2, mes2, anio + 1)
        if fin is None:
            return None
    delta = (fin - inicio).days
    if 1 <= delta <= 62:
        return delta
    return None


def sanitizar(texto: str) -> str:
    limpio = texto.replace("\xa0", " ")
    for patron in _PII_PATTERNS:
        limpio = patron.sub("[REDACTADO]", limpio)
    return limpio


def extraer_texto(contenido: bytes) -> str:
    partes: list[str] = []
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        for page in pdf.pages:
            partes.append(page.extract_text() or "")
            for table in page.extract_tables() or []:
                for row in table:
                    celdas = [c for c in row if c]
                    if celdas:
                        partes.append(" | ".join(celdas))
    return sanitizar("\n".join(partes))


def altitud_mayor_1000m(municipio: str | None) -> bool:
    if not municipio:
        return True
    altura = MUNICIPIOS_MSNM.get(municipio.strip().lower())
    if altura is None:
        return True
    return altura >= 1000.0


def _historico(texto: str, actual: float | None) -> list[float]:
    valores: list[float] = []
    for m in _RE_CONSUMO_KWH.finditer(texto):
        n = parse_number(m.group(1))
        if n is None or n < 20 or n > 5000:
            continue
        if not valores or abs(n - valores[-1]) > 0.4:
            valores.append(n)
    if actual is not None:
        valores = [v for v in valores if abs(v - actual) > 0.4] + [actual]
    # últimos 6, sin el duplicado final si es el actual
    uniq: list[float] = []
    for v in valores:
        if not uniq or abs(v - uniq[-1]) > 0.4:
            uniq.append(v)
    return uniq[-6:]


def extraer_campos(texto: str) -> ExtractPDFResponse:
    municipio = None
    estrato = None
    provisional = False
    m_combo = _RE_MUNI_ESTRATO.search(texto)
    if m_combo:
        municipio = m_combo.group(1).strip().title()
        raw_est = m_combo.group(2)
        if raw_est.lower() == "provisional":
            provisional = True
        else:
            estrato = int(raw_est)
    if municipio is None:
        m_mun = _RE_MUNICIPIO_LINEA.search(texto)
        if m_mun:
            municipio = m_mun.group(1).title()
    if estrato is None:
        m_est = _RE_ESTRATO.search(texto)
        if m_est:
            if m_est.group(1).lower() == "provisional":
                provisional = True
            else:
                estrato = int(m_est.group(1))

    consumo = None
    valor_energia = None
    m_en = _RE_ENERGIA.search(texto)
    if m_en:
        consumo = parse_number(m_en.group(1))
        valor_energia = parse_number(m_en.group(2))

    periodo = None
    m_per = _RE_PERIODO.search(texto)
    if m_per:
        periodo = m_per.group(1).strip()
        periodo = re.sub(r"\s+", " ", periodo)

    dias = None
    m_dias = _RE_DIAS.search(texto)
    if m_dias:
        dias = int(m_dias.group(1))
    if dias is None:
        dias = dias_desde_periodo(periodo)
    if dias is None:
        dias = 30

    tarifa = _primer(_RE_TARIFA, texto)
    if tarifa is None and consumo and valor_energia and consumo > 0:
        tarifa = round(valor_energia / consumo, 2)

    tipo: str = "real"
    if re.search(r"promediad", texto, re.I):
        tipo = "promediada"
    elif _RE_ESTIMADA.search(texto):
        tipo = "estimada"

    return ExtractPDFResponse(
        consumo_kwh=consumo,
        periodo_facturado=periodo,
        dias_facturados=dias,
        valor_energia_cop=valor_energia,
        valor_total_factura_cop=_primer(_RE_TOTAL, texto),
        cuentas_vencidas_cop=_primer(_RE_CUENTAS_VENCIDAS, texto),
        otras_entidades_cop=_primer(_RE_OTRAS_ENTIDADES, texto),
        estrato=estrato,
        estrato_provisional=provisional,
        municipio=municipio,
        altitud_mayor_1000m=altitud_mayor_1000m(municipio),
        tipo_lectura=tipo,  # type: ignore[arg-type]
        tarifa_kwh_cop=tarifa,
        historico_kwh=_historico(texto, consumo),
        etiqueta="leido",
    )


def _primer(patron: re.Pattern[str], texto: str) -> float | None:
    m = patron.search(texto)
    return parse_number(m.group(1)) if m else None


def extract_from_bytes(contenido: bytes) -> ExtractPDFResponse:
    if not contenido:
        raise ScannedPdfError("El archivo está vacío.")
    texto = extraer_texto(contenido)
    if len(re.sub(r"\s+", "", texto)) < MIN_CHARS_TEXTO:
        raise ScannedPdfError(
            "El PDF no tiene texto seleccionable (menos de 50 caracteres). "
            "Solo se soportan PDFs digitales de EPM con texto seleccionable; no fotos ni escaneos."
        )
    return extraer_campos(texto)
