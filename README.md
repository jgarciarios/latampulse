# LatamPulse

**🔗 [Ver dashboard en vivo →](https://latampulse.streamlit.app)**

**¿Cuánto cuesta vivir en Argentina, Brasil, Uruguay y Colombia — y qué tan lejos llega realmente un sueldo en cada país?**

Pipeline de datos de punta a punta que extrae, limpia y compara costo de vida y poder adquisitivo entre 4 países de Latinoamérica, combinando fuentes oficiales (bancos centrales, institutos de estadística, Banco Mundial) con research de precios cotidianos verificado a mano.

El diferenciador del proyecto no es solo "juntar datos" — es la distinción entre **USD nominal** (precio al tipo de cambio del día) y **USD PPP** (precio ajustado por poder de compra real). Esa brecha es la historia: en Argentina, por ejemplo, el dólar oficial está subvaluado respecto al poder de compra real, así que un mismo producto puede verse "barato" en dólares del día y "caro" en términos de lo que realmente rinde ese sueldo.

## Por qué este proyecto es más que un scraper

La parte interesante no es la extracción — es todo lo que **no sale bien a la primera** y cómo se manejó:

- Seis fuentes con seis formatos distintos (JSON, Excel con headers multi-fila, ODS, CSV con encoding latin-1), cada una con su propia forma de romperse.
- Un bug real de SIDRA (IBGE) donde el layout de columnas cambia según qué tabla/variable se pide — no es un formato fijo.
- Un bug silencioso en la serie de Uruguay: usar `ffill()` sobre una columna de tipo mixto (año como número vs. como texto de título) mal-etiquetaba años enteros sin tirar ningún error — se detectó comparando contra el archivo fuente, no porque el código "se rompiera".
- Comas decimales, fechas cargadas por error en columnas de precio, filas duplicadas de research manual — cada uno con su propio fix, probado antes de aplicarse.
- Una regla de diseño que se sostuvo en todo el proyecto: **si un dato no es verificable, no se inventa.** Se documenta como faltante (`confidence` field) en vez de rellenarse con una estimación.

Todo el proceso de debugging —hipótesis, reproducción del bug con datos sintéticos, fix, verificación— queda documentado en [`AGENTS.md`](./AGENTS.md).

## Arquitectura

```
Fuentes (6) ──▶ extract.py ──▶ data/raw/ ──▶ transform.py ──▶ data/processed/ ──▶ load.py ──▶ Postgres
                                                                       │
                                                                       ▼
                                                     notebooks/01_exploratory_analysis.ipynb
```

Cada capa tiene una única responsabilidad:
- **`extract.py`** — pega a cada fuente, guarda la respuesta cruda tal cual vino. Cero transformación acá.
- **`transform.py`** — normaliza los 6 formatos heterogéneos a un schema común, calcula USD nominal/PPP.
- **`load.py`** — carga a Postgres (corriendo en Docker localmente).
- **`notebooks/`** — análisis exploratorio: comparación de precios, brecha nominal/PPP, inflación normalizada entre países, poder adquisitivo.

## Fuentes de datos

| Fuente | País | Qué extrae | Formato |
|---|---|---|---|
| [dolarapi.com](https://dolarapi.com) | Argentina | Tipo de cambio (oficial, blue, MEP, CCL, cripto, tarjeta) | API REST / JSON |
| [World Bank API](https://api.worldbank.org) | Los 4 | PPP conversion factor, GDP per cápita | API REST / JSON |
| [IBGE / SIDRA](https://sidra.ibge.gov.br) | Brasil | IPCA (inflación) | API REST / JSON |
| [DANE](https://www.dane.gov.co) | Colombia | IPC (inflación) | Excel |
| [INE Uruguay (vía DGI)](https://www.gub.uy) | Uruguay | IPC (inflación) | ODS |
| [INDEC](https://www.indec.gob.ar) | Argentina | IPC por división, nivel general | CSV |
| Research manual | Los 4 | Precios cotidianos (streaming, alquiler, transporte, alimentos) sin fuente oficial | Excel, verificado a mano con fuente y fecha por fila |

Se evaluó Numbeo como fuente adicional y se descartó: sus Términos de Servicio prohíben explícitamente el scraping automatizado.

## Stack

Python (pandas, requests) · Postgres (Docker) · SQLAlchemy · Jupyter/matplotlib · GitHub

## Estructura del repo

```
LatamPulse/
├── src/
│   ├── extract.py         # 6 extractores, uno por fuente
│   ├── transform.py       # normalización + cálculo de USD nominal/PPP
│   ├── load.py             # carga a Postgres
│   ├── run_pipeline.py    # orquesta extract → transform → CSV
│   └── utils.py            # logging, retry con backoff, guardado con trazabilidad
├── sql/
│   └── schema.sql         # 5 tablas: countries, exchange_rates, ppp_factors, inflation_indices, prices
├── notebooks/
│   └── 01_exploratory_analysis.ipynb
├── data/
│   ├── raw/                # salida cruda de extract.py (no versionado)
│   ├── processed/         # CSV listos para cargar (no versionado)
│   └── manual/             # research manual verificado a mano
├── docker-compose.yml     # Postgres local
├── AGENTS.md                # bitácora técnica: decisiones, bugs encontrados y cómo se resolvieron
└── requirements.txt
```

## Setup

**Para solo ver el resultado:** entrá directo a [latampulse.streamlit.app](https://latampulse.streamlit.app), no hace falta instalar nada.

**Para correr el proyecto completo** (pipeline de extracción + base de datos + notebook):

```bash
# 1. Entorno
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Base de datos
docker compose up -d

# 3. Pipeline completo (extracción + transformación)
python -m src.run_pipeline

# 4. Carga a Postgres
python -m src.load

# 5. Análisis
jupyter notebook notebooks/01_exploratory_analysis.ipynb
```

## Reglas de diseño del proyecto

- **Nunca inventar datos.** Un precio sin fuente verificable no se estima ni se completa — la fila directamente no existe, y queda documentado como faltante.
- **Extracción y transformación separadas.** `extract.py` nunca limpia ni convierte nada; `transform.py` nunca vuelve a pegarle a una fuente externa.
- **Todo cambio de esquema o parser se prueba con datos sintéticos antes de tocar datos reales**, y se valida contra los datos reales después.
- **Cada fuente citada, cada dato del research manual con fecha de captura.**

La bitácora completa de decisiones técnicas, bugs encontrados y su resolución está en [`AGENTS.md`](./AGENTS.md).
