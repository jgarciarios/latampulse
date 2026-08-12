# LatamPulse

Pipeline de extracción y análisis de datos macroeconómicos de América Latina.

## Fuentes

| Fuente | Qué extrae |
|---|---|
| [DolarAPI](https://dolarapi.com) | Tipos de cambio USD/ARS (oficial, blue, MEP, CCL, crypto) |
| [World Bank](https://data.worldbank.org) | Indicadores macroeconómicos (PIB, inflación, desempleo, etc.) |
| [IBGE / SIDRA](https://sidra.ibge.gov.br) | Datos estadísticos de Brasil |

## Estructura

```
LatamPulse/
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── utils.py       # logger, save_raw, retry
│   └── extract.py     # extractores por fuente
└── data/
    ├── raw/           # CSVs con timestamp generados por save_raw()
    └── manual/        # archivos cargados manualmente
```

## Setup

```bash
pip install -r requirements.txt
```

## Uso rápido

```python
from src.extract import fetch_dolar_api, fetch_worldbank, fetch_ibge
from src.utils import save_raw

df = fetch_dolar_api()
save_raw(df, "dolar")

df_wb = fetch_worldbank(["NY.GDP.MKTP.CD", "FP.CPI.TOTL.ZG"])
save_raw(df_wb, "worldbank")

df_ibge = fetch_ibge()
save_raw(df_ibge, "ibge")
```
