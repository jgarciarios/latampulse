# AGENTS.md — LatamPulse

Este archivo lo leen automáticamente los agentes de código que trabajan en este
proyecto (Claude Code, y el agente de Antigravity). Si sos un agente leyendo
esto: las reglas de abajo no son sugerencias, son requisitos — varias existen
porque las violamos primero y nos rompieron el proyecto.

## Qué es este proyecto

Pipeline de datos de costo de vida y poder adquisitivo en 4 países de LATAM
(Argentina, Brasil, Uruguay, Colombia). Portfolio de datos — la prioridad
número uno es que cada dato sea rastreable a una fuente real y verificable,
no que el pipeline "funcione" a cualquier costo.

## Regla de oro: nunca inventar datos

Si un dato no está disponible, la fila correspondiente **no existe** —
nunca se rellena con un valor estimado, interpolado o inventado sin dejarlo
explícitamente marcado como tal. El campo `confidence` existe para esto.
Esta regla es la razón de ser del proyecto — no la rompas para "completar"
algo, ni siquiera si te lo piden de forma ambigua.

## División de responsabilidades: quién diseña vs. quién ejecuta

- **El chat de Claude (claude.ai)** es donde se diseña, se prueba localmente
  contra datos simulados, y se decide la lógica. El código que llega a este
  proyecto ya fue corrido y validado ahí antes de pedir que lo apliques.
- **El agente de ejecución** (Claude Code en terminal, o el agente de
  Antigravity) corre exactamente el script que se le da. **No mejores, no
  reformatees, no "arregles" nada por tu cuenta** — si algo parece raro,
  reportalo y esperá instrucciones en vez de improvisar. Esto no es
  desconfianza gratuita: reescribir código "mejorándolo" ya causó bugs reales
  en este proyecto (indicadores de World Bank cambiados sin avisar, países
  agregados que nadie pidió, funciones a medio escribir).

## Reglas técnicas para aplicar patches

1. **Nunca hagas un edit parcial cuando el prompt pide sobreescribir un
   archivo entero.** Si el prompt dice `cat > archivo << EOF`, es así — no
   un diff selectivo de "lo que cambió".
2. **Si un script de reemplazo por texto exacto no encuentra el bloque que
   busca, no lo apliques a mano ni improvises el fix.** Reportá el mensaje
   de error completo y el contexto real del archivo, y esperá el próximo
   script. Aplicar el mismo cambio "a mano" cuando el automático falla ya
   generó parches silenciosamente distintos a los especificados.
3. **En `re.sub()`, si el string de reemplazo tiene backslashes (`\xa0`,
   `\u00f1`, etc.), usá `pattern.sub(lambda m: texto, contenido)` — nunca
   `pattern.sub(texto, contenido)` directo.** Sin el lambda, `re.sub`
   interpreta esos backslashes como secuencias de escape y tira
   `PatternError: bad escape`.
4. **Después de aplicar un patch, validá con `python -m py_compile` antes
   de correr nada.** Si compila pero el resultado no se ve bien, usá
   `ast.parse()` para verificar estructuralmente (funciones presentes,
   constantes presentes, sin duplicados) en vez de confiar solo en que
   "no tiró error".
5. **Si te piden pegar el contenido completo de un archivo en el chat, y
   el archivo es largo, hacelo en texto plano vía `cat`, no en captura de
   pantalla.** Las capturas cortan líneas largas a la mitad y generan
   falsas alarmas de "archivo corrupto" que no existen en el archivo real.

## Estructura del pipeline

```
src/
  utils.py       → logging, guardado de raw con trazabilidad, retry con backoff
  extract.py     → CERO transformación. Pega a la fuente, guarda tal cual vino.
  transform.py   → normaliza los formatos heterogéneos al schema común
  load.py        → (pendiente) carga a la base de datos
data/
  raw/{fuente}/  → salida de extract.py, nunca se sobreescribe (fecha en el nombre)
  manual/        → research manual cargado a mano, con fuente y fecha por fila
```

**extract.py nunca transforma.** Si estás tentado a limpiar o convertir un
dato ahí, para — esa lógica va en transform.py. Mezclar las dos capas es la
forma más común de terminar con un pipeline indebuggeable.

## Fuentes y gotchas específicos por fuente

### dolarapi (Argentina, tipo de cambio) — JSON
Sin sorpresas. `rate_type` usa nombres largos reales de la API: `bolsa` y
`contadoconliqui`, no `mep`/`ccl` como se podría asumir por las siglas
coloquiales.

### World Bank (PPP + GDP per cápita) — JSON
Usa rango de fechas explícito (`date=2015:2024`), no el parámetro `mrnev`
— confirmado que `mrnev` es válido pero la API es inestable con él bajo
carga. Cada indicador puede tener su año más reciente con dato distinto
entre sí — nunca asumas que todos comparten el mismo año de referencia.

### IBGE/SIDRA (Brasil, IPCA) — JSON
El elemento `[0]` del array de respuesta es una fila de ETIQUETAS de
columna, no datos — hay que saltarlo. **El layout de dimensiones (qué
columna es el mes, cuál es la variable) NO es universal en SIDRA — cambia
según la combinación de tabla/variable pedida.** Para esta combinación
específica (tabla 1737, variable 63), D2C/D2N = variable, D3C/D3N = mes.
Si se cambia la tabla o variable en `extract.py`, hay que re-verificar esto
con un one-liner de inspección antes de asumir que sigue igual. SIDRA marca
"sin dato" con el string literal `"..."`, no con null.

### DANE (Colombia, IPC) — Excel
Hoja `IndicesIPC`. Formato wide: fila 9 = header (años en columnas B-Y),
filas 10-21 = meses (Enero-Diciembre). Los nombres de mes vienen con
comillas simples embebidas (`"'Enero'"`) — hay que `.strip("'")`. El año en
curso tiene `None` en los meses todavía no publicados — se omiten, no se
rellenan. El archivo no tiene metadata de fecha de extracción embebida (a
diferencia de los JSON) — se usa el mtime del archivo como proxy.

### INE Uruguay (vía DGI) — .ods
Requiere `engine="odf"` en pandas (paquete `odfpy`, se importa como `odf`).
**Nunca uses `ffill()` vectorizado sobre la columna de año** — es una
columna de tipo mixto (int y texto de título como "Año 2019" mezclados), y
un ffill ingenuo propaga el ÚLTIMO valor no-nulo sea del tipo que sea. Si un
bloque de año no tiene su propio marcador int (solo aparece en el título de
texto), el ffill le asigna el año del bloque ANTERIOR — un error silencioso
mucho peor que perder esas filas, porque no se nota a simple vista. La
solución correcta es parsear el año fila por fila, aceptando tanto int
limpio como texto "Año YYYY" vía regex. Además: valores con coma decimal
("99,47"), filas de header que se cuelan con texto no-numérico en la
columna de valor, y "Setiembre" sin tilde como variante real de
"Septiembre" — el diccionario de meses tiene que incluir ambas grafías.

### INDEC (Argentina, IPC) — CSV, descarga manual
Separador `;`, encoding `latin-1` (NO utf-8 — tiene tildes que rompen si
se lee mal). 7 regiones en el archivo — filtrar `Region == "Nacional"`
para que sea comparable con los otros 3 países. Valores con coma decimal.
`Codigo == "0"` es el Nivel General (IPC headline).

## Research manual (data/manual/)

Cada fila necesita: fuente específica (no "Google" o "IA"), fecha de
captura real, y `confidence = 'manual_research'`. Si no hay fuente
verificable, se documenta igual el rango/valor en `notes` pero se marca
"Fuente sin confirmar" en vez de inventar una cita — mejor honesto que
falso.

## Countries / currencies de referencia

| country_code | currency | 
|---|---|
| AR | ARS |
| BR | BRL |
| UY | UYU |
| CO | COP |

## Estado del proyecto (actualizar a medida que avanza)

- [x] Extracción (6/6 fuentes)
- [x] Research manual (48/52 filas — 4 pendientes documentadas)
- [x] transform.py: dolarapi, worldbank, ibge, dane, ine_uruguay, indec (6/6)
- [ ] transform.py: compute_usd_values()
- [ ] load.py
- [ ] Análisis exploratorio
- [ ] Visualización / dashboard
- [ ] Deploy + README + presentación
