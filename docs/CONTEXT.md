# Contexto Técnico y Reglas de Negocio — WattWise

## 1. Normativa Eléctrica Colombiana

- **Resolución UPME 0355 de 2004 (Consumo de Subsistencia):**
  - Municipios a ≥ 1.000 m.s.n.m. (ej. Medellín, Envigado, Sabaneta, Itagüí, Bello, Rionegro, Bogotá): **130 kWh/mes**.
  - Municipios a < 1.000 m.s.n.m. (ej. Barranquilla, Cartagena, Santa Marta, Apartadó): **173 kWh/mes**.
  - Aplica únicamente a **Estratos 1, 2 y 3**. Estrato 4 no tiene subsidio ni contribución. Estratos 5 y 6 pagan contribución del 20 %.
  - Todo kWh que exceda el umbral de subsistencia se cobra a tarifa plena (Costo Unitario - CU sin subsidio).
- **Ley 142 de 1994 (Servicios Públicos):**
  - Si `tipo_lectura` es `"estimada"` o `"promediada"`, el usuario tiene derecho a exigir revisión y ajuste contra lectura real del medidor.
  - Los cobros de *Otras entidades* (seguros, créditos, electrodomésticos) y *Cuentas vencidas* son independientes del consumo energético actual y no deben confundirse con el costo del kWh.
  - En EPM, `Estrato: Provisional` indica clasificación temporal mientras se actualiza el catastro o estratificación municipal.

Porcentajes de subsidio sobre el **bloque de subsistencia** (práctica EPM): estrato 1 = 60 %, estrato 2 = 50 %, estrato 3 = 15 %.

Sobrecosto por excedente (lo que se deja de ahorrar al cruzar el umbral):

```
kwh_sin_subsidio = max(0, consumo_kwh - umbral)
sobrecosto_por_excedente_cop = kwh_sin_subsidio × tarifa_kwh_cop × porcentaje_subsidio
```

Ejemplo PRD: 166 kWh, umbral 130, estrato 2, CU 890.5 → 36 × 890.5 × 0.50 = 16 029 COP.

## 2. Anatomía de la Factura EPM (Mapeo para `extractor.py`)

- **Página 1 (Resumen):**
  - Municipio y Estrato: línea tipo `Sabaneta - Antioquia Estrato: 2 - Provisional Ciclo: 5`
  - Periodo: `Periodo de consumo: Consumo del 18 Mar al 18 Abr`
  - Días: `Días de consumo: 31`
  - Energía: `Energía 166 kwh $ 66.566,90`
  - Otros rubros financieros: `Cuentas Vencidas $ 138.945,19`, `Otras entidades $ 19.784,50`, `Total a pagar`.
- **Página 2 (Detalle de Energía y Gráfico Histórico):**
  - Extraer el **Costo Unitario ($/kWh)** aplicado en el bloque de detalle de Energía (si no se detecta explícitamente, calcular fallback `valor_energia_cop / consumo_kwh`).
  - Extraer el vector de los últimos 6 meses de consumo en kWh si aparece en la tabla/gráfico de historial.

Sanitización Ley 1581: no capturar nombre del titular, cédula/NIT, dirección de cobro ni número de contrato. El PDF se lee en memoria (`BytesIO`).

PDF con `extract_text()` vacío o < 50 caracteres → HTTP 422 (no fotos/escaneos).

## 3. Mapeo del Cuestionario de 8 Preguntas (`Cuestionario_del_hogar.docx`)

Fórmula base por equipo: \(E_{\text{mes}} = P_{\text{kW}} \times h_{\text{día}} \times d_{\text{facturados}}\).

1. **`personas`:** `"1 o 2"`, `"3 o 4"`, `"5 o 6"`, `"7 o más"` (calibra consumo base esperado).
2. **`nevera_antiguedad` & `nevera_cierra_bien` & `nevera_etiqueta_kwh_mes`:**
   - Si `nevera_etiqueta_kwh_mes` tiene valor numérico > 0, usar ese valor como base.
   - Si no: `"Menos de 5 años"` = `32 kWh/mes`; `"Entre 5 y 10 años"` = `45 kWh/mes`; `"Más de 10 años"` o `"No sé"` = `60 kWh/mes`.
   - Penalización si `nevera_cierra_bien == "No"`: multiplicar consumo de nevera por `1.30` (+30 % por fuga térmica).
3. **`tv_horas_dia`:** `"No tengo televisor"` (`0 h`), `"Menos de 3 horas"` (`1.5 h`), `"Entre 3 y 6 horas"` (`4.5 h`), `"Más de 6 horas"` (`7.5 h`) × `0.11 kW`.
4. **`lavadora_veces_semana`:** `"No tengo lavadora"` (`0`), `"1 o 2 veces"` (`1.5`), `"3 o 4 veces"` (`3.5`), `"5 o más veces"` (`5.5`). Consumo por ciclo: `0.55 kWh/lavada` × `(d / 7)`.
5. **`equipos_diarios`** (mapeo de `"No lo uso"` = `0`, `"Menos de 1 h"` según equipo, `"De 1 a 3 h"` = `2.0 h`, `"Más de 3 h"` = `4.0 h`):
   - `microondas`: `1.20 kW` (`Menos de 1 h` = `0.15 h/día`).
   - `plancha`: `1.20 kW` (`Menos de 1 h` = `0.25 h/día`).
   - `ventilador`: `0.065 kW` (`Menos de 1 h` = `0.5 h/día`).
   - `computador`: `0.12 kW` (`Menos de 1 h` = `0.5 h/día`).
   - `licuadora`: `0.45 kW` (`Menos de 1 h` = `0.10 h/día`).
   - `ducha_electrica`: `3.50 kW` (`Menos de 1 h` = `0.33 h/día` [20 min]).
6. **`standby` (Consumo fantasma en W continuos 24/7):**
   - `Televisor`: `8 W`, `Decodificador`: `15 W`, `Cargadores de celular`: `3 W`, `Computador o cargador de portátil`: `10 W`, `Router de internet`: `12 W`, `Otro`: `10 W`.
   - Cálculo: \((\sum W / 1000) \times 24 \times d_{\text{facturados}}\).
7. **`meta_ahorro` & `cambios_mes`:**
   - `"5 %"` → `0.05`, `"10 %"` → `0.10`, `"15 % o más"` → `0.15`.
   - `cambios_mes` se pasa al LLM para contextualizar desviaciones frente al mes anterior (ej. `"Hay más personas o visitas"` explica un pico sin que sea falla eléctrica).

Residuo inexplicado = `consumo_kwh` − suma de equipos − standby. No afirmar hurto de energía.

## 4. Municipios (cabecera, m s.n.m.)

Usar altura IGAC de la cabecera. `altitud_mayor_1000m = altura >= 1000`.

| Municipio | m s.n.m. | Umbral |
| --- | --- | --- |
| Medellín, Bello, Envigado, Itagüí, Sabaneta, La Estrella, Copacabana, Girardota, Barbosa | ≥ 1000 | 130 |
| Rionegro, La Ceja, Marinilla, Bogotá | ≥ 1000 | 130 |
| Apartadó, Turbo, Caucasia, Barranquilla, Cartagena, Santa Marta | < 1000 | 173 |
| Santa Fe de Antioquia | 550 | 173 |

Si el municipio no está en tabla, default Valle de Aburrá (`true` / 130) y advertir en reglas, no en Gemini.

## 5. Mes 2 (`ciclo_anterior`)

Normalizar por días facturados si el periodo cambia ±20 %:

```
kwh_30 = consumo_kwh / dias_facturados × 30
ahorro_real_kwh = kwh_30_mes1 − kwh_30_mes2
```

Lectura estimada/promediada en Mes 2 → no marcar `verificado`; citar Ley 142 (derecho a ajuste con lectura real).
