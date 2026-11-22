"""Knapsack 0-1: acciones para cumplir meta_ahorro y bajar del umbral UPME."""

from __future__ import annotations

from dataclasses import dataclass

from app.rules_engine import ResultadoReglas
from app.schemas import AccionPlan, AnalyzeRequest, CuestionarioHogar


@dataclass
class Candidato:
    id: str
    accion: str
    categoria: str
    requiere_inversion: bool
    ahorro_kwh: float
    ayuda_subsidio: bool
    peso: int  # 1 = hábito, 3 = mantenimiento, 5 = compra (minimizar esfuerzo)


def _cop(kwh: float, tarifa: float | None) -> float | None:
    if tarifa is None:
        return None
    return round(kwh * tarifa, 0)


def _kwh_equipo(desglose, nombre_sub: str) -> float:
    for d in desglose:
        if nombre_sub.lower() in d.equipo.lower():
            return d.kwh_mes
    return 0.0


def _candidatos(q: CuestionarioHogar, reglas: ResultadoReglas) -> list[Candidato]:
    items: list[Candidato] = []
    nevera = _kwh_equipo(reglas.desglose, "nevera")
    if q.nevera_cierra_bien == "No" and nevera > 0:
        ahorro = round(nevera - nevera / 1.30, 2)
        items.append(
            Candidato(
                "act_empaque_nevera",
                "Cambiar el empaque magnético de la puerta de la nevera",
                "mantenimiento",
                True,
                ahorro,
                True,
                3,
            )
        )
    ducha = _kwh_equipo(reglas.desglose, "ducha")
    if ducha >= 5:
        items.append(
            Candidato(
                "act_ducha_2min",
                "Recortar 2 minutos la ducha eléctrica cada día",
                "habito",
                False,
                round(min(ducha * 0.20, 3.50 * (2 / 60) * 30), 2),
                True,
                1,
            )
        )
    plancha = _kwh_equipo(reglas.desglose, "plancha")
    if plancha >= 2:
        items.append(
            Candidato(
                "act_plancha_semanal",
                "Planchar una vez por semana, carga completa",
                "habito",
                False,
                round(plancha * 0.40, 2),
                True,
                1,
            )
        )
    standby = _kwh_equipo(reglas.desglose, "fantasma")
    if standby >= 1 and q.standby:
        items.append(
            Candidato(
                "act_standby",
                "Desconectar TV, decodificador, cargadores y router en una regleta con interruptor",
                "habito",
                False,
                round(standby * 0.90, 2),
                True,
                1,
            )
        )
    tv = _kwh_equipo(reglas.desglose, "televisor")
    if q.tv_horas_dia == "Más de 6 horas" and tv > 0:
        items.append(
            Candidato(
                "act_tv_horas",
                "Bajar el televisor a menos de 6 horas al día y apagarlo en el equipo",
                "habito",
                False,
                round(0.11 * (7.5 - 4.5) * 30, 2),
                True,
                1,
            )
        )
    micro = _kwh_equipo(reglas.desglose, "microondas")
    if micro >= 2:
        items.append(
            Candidato(
                "act_microondas",
                "Limitar el microondas a calentados cortos (menos de 1 h/día equivalente)",
                "habito",
                False,
                round(micro * 0.25, 2),
                False,
                1,
            )
        )
    if reglas.residuo_kwh and reglas.residuo_kwh >= 15:
        items.append(
            Candidato(
                "act_residuo",
                "Revisar nevera, fugas y equipos no declarados que expliquen el residuo inexplicado",
                "mantenimiento",
                False,
                round(min(reglas.residuo_kwh * 0.30, 20.0), 2),
                True,
                3,
            )
        )
    return [c for c in items if c.ahorro_kwh > 0]


def _knapsack(items: list[Candidato], objetivo_kwh: float) -> list[Candidato]:
    """Minimiza peso (esfuerzo) sujeto a ahorro >= objetivo; desempate: más kWh y más ayuda_subsidio."""
    n = len(items)
    if n == 0:
        return []
    objetivo = max(objetivo_kwh, 0.0)
    # DP sobre ahorro en décimas de kWh.
    scale = 10
    caps = [max(1, int(round(c.ahorro_kwh * scale))) for c in items]
    max_cap = sum(caps)
    target = min(max_cap, int(round(objetivo * scale)))
    inf = 10**9
    dp = [inf] * (max_cap + 1)
    take = [-1] * (max_cap + 1)
    prev = [-1] * (max_cap + 1)
    dp[0] = 0
    for i, c in enumerate(items):
        wi = c.peso
        vi = caps[i]
        for s in range(max_cap - vi, -1, -1):
            if dp[s] == inf:
                continue
            ns = s + vi
            cost = dp[s] + wi
            if cost < dp[ns]:
                dp[ns] = cost
                take[ns] = i
                prev[ns] = s
    best_s = None
    for s in range(target, max_cap + 1):
        if dp[s] < inf:
            best_s = s
            break
    if best_s is None:
        # No alcanza el objetivo: tomar todo, priorizando subsidio.
        return sorted(items, key=lambda c: (not c.ayuda_subsidio, -c.ahorro_kwh))
    chosen_idx: list[int] = []
    s = best_s
    while s > 0 and take[s] >= 0:
        i = take[s]
        if i in chosen_idx:
            break
        chosen_idx.append(i)
        s = prev[s]
    chosen = [items[i] for i in chosen_idx]
    chosen.sort(key=lambda c: (not c.ayuda_subsidio, -c.ahorro_kwh))
    return chosen


def optimizar(req: AnalyzeRequest, reglas: ResultadoReglas) -> tuple[list[AccionPlan], float, float | None]:
    cand = _candidatos(req.cuestionario, reglas)
    consumo = req.factura.consumo_kwh or 0.0
    meta_kwh = consumo * reglas.meta_pct
    umbral_gap = reglas.subsidio.kwh_sin_subsidio
    objetivo = max(meta_kwh, umbral_gap)
    elegidos = _knapsack(cand, objetivo)
    ids = {c.id for c in elegidos}
    tarifa = req.factura.tarifa_kwh_cop
    acciones: list[AccionPlan] = []
    prio = 1
    orden = list(elegidos) + [c for c in cand if c.id not in ids]
    for c in orden:
        acciones.append(
            AccionPlan(
                id=c.id,
                prioridad=prio if c.id in ids else 99,
                accion=c.accion,
                categoria=c.categoria,  # type: ignore[arg-type]
                requiere_inversion=c.requiere_inversion,
                ahorro_kwh=c.ahorro_kwh,
                ahorro_cop=_cop(c.ahorro_kwh, tarifa),
                ayuda_recuperar_subsidio=c.ayuda_subsidio,
                etiqueta="estimado",
            )
        )
        if c.id in ids:
            prio += 1
    acciones.sort(key=lambda a: a.prioridad)
    for i, a in enumerate(acciones, start=1):
        if a.prioridad != 99:
            a.prioridad = i
    ahorro = round(sum(c.ahorro_kwh for c in elegidos), 2)
    return acciones, ahorro, _cop(ahorro, tarifa)
