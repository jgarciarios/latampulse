"""
extract.py — Extracción de datos crudos para LatamPulse.

Regla de diseño para todo este archivo: CERO transformación de datos acá.
Cada función pega a una fuente, guarda la respuesta tal cual vino (envuelta
en metadata de trazabilidad), y listo. Limpieza, normalización a USD, y
cálculo de PPP son responsabilidad de transform.py (Día 3-4).

Cobertura de este archivo:
  - extract_dolarapi()              → tipo de cambio Argentina
  - extract_worldbank()             → PPP y GDP per cápita, los 4 países
  - extract_ibge()                  → IPCA Brasil vía SIDRA
  - extract_dane()                  → IPC Colombia (Excel, URL por mes)
  - extract_ine_uruguay()           → IPC Uruguay vía DGI (.ods)
  - register_indec_manual_download()→ registra el CSV de INDEC bajado a mano
"""

from pathlib import Path

from src.utils import (
    build_extraction_envelope,
    fetch_with_retry,
    get_logger,
    save_raw_bytes,
    save_raw_json,
)

logger = get_logger("latampulse.extract")

COUNTRIES = ["AR", "BR", "UY", "CO"]

DOLARAPI_URL = "https://dolarapi.com/v1/dolares"


def extract_dolarapi():
    logger.info("Extrayendo tipo de cambio Argentina desde dolarapi.com...")
    response = fetch_with_retry(DOLARAPI_URL)
    payload = response.json()
    envelope = build_extraction_envelope(payload, "dolarapi", DOLARAPI_URL)
    filepath = save_raw_json(envelope, "exchange_rates", "dolarapi_ar")
    logger.info(f"OK — {len(payload)} cotizaciones guardadas en {filepath}")
    return envelope


WORLDBANK_BASE_URL = "https://api.worldbank.org/v2/country"

WORLDBANK_COUNTRY_CODES = {"AR": "ARG", "BR": "BRA", "UY": "URY", "CO": "COL"}

WORLDBANK_INDICATORS = {
    "gdp_per_capita_ppp_current": "NY.GDP.PCAP.PP.CD",
    "gdp_per_capita_ppp_constant": "NY.GDP.PCAP.PP.KD",
    "ppp_conversion_factor": "PA.NUS.PPP",
}


def extract_worldbank(start_year: int = 2015, end_year: int = 2024) -> dict:
    """
    Extrae PPP y GDP per cápita para los 4 países del proyecto.

    Usamos rango de fechas explícito en vez de 'mrnev' porque confirmamos
    que la API del Banco Mundial es inestable bajo carga con ese parámetro
    puntual. El rango de fechas está documentado como universalmente
    soportado. Traemos el rango completo sin filtrar "el más reciente"
    acá — esa lógica es de transform.py, no de extracción.
    """
    logger.info("Extrayendo PPP y GDP per cápita desde World Bank API...")

    iso3_codes = ";".join(WORLDBANK_COUNTRY_CODES.values())
    all_results = {}

    for indicator_key, indicator_code in WORLDBANK_INDICATORS.items():
        url = (
            f"{WORLDBANK_BASE_URL}/{iso3_codes}/indicator/{indicator_code}"
            f"?format=json&per_page=100&date={start_year}:{end_year}"
        )

        response = fetch_with_retry(url, max_retries=5)
        payload = response.json()

        if len(payload) < 2 or payload[1] is None:
            logger.warning(f"Sin datos para indicador {indicator_key} ({indicator_code})")
            all_results[indicator_key] = []
            continue

        all_results[indicator_key] = payload[1]
        logger.info(f"  {indicator_key}: {len(payload[1])} registros")

    envelope = build_extraction_envelope(
        payload=all_results,
        source_name="world_bank",
        source_url=f"{WORLDBANK_BASE_URL}/{iso3_codes}/indicator/...",
    )

    filepath = save_raw_json(
        data=envelope,
        source="worldbank",
        filename_prefix="ppp_gdp",
    )

    logger.info(f"OK — guardado en {filepath}")
    return envelope


SIDRA_BASE_URL = "https://apisidra.ibge.gov.br/values"
IPCA_TABLE = "1737"


def extract_ibge(last_n_months=24):
    logger.info(f"Extrayendo IPCA (Brasil) desde SIDRA — últimos {last_n_months} meses...")
    url = f"{SIDRA_BASE_URL}/t/{IPCA_TABLE}/n1/all/v/63/p/last%20{last_n_months}"
    response = fetch_with_retry(url)
    payload = response.json()
    if not payload or len(payload) < 2:
        logger.error("SIDRA devolvió una respuesta vacía o inesperada")
        raise ValueError("Respuesta vacía de SIDRA — revisar la URL/tabla")
    envelope = build_extraction_envelope(payload, "ibge_sidra", url)
    filepath = save_raw_json(envelope, "ibge", "ipca")
    logger.info(f"OK — {len(payload) - 1} registros guardados en {filepath}")
    return envelope


DANE_MONTH_ABBR = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

DANE_BASE_URL = "https://www.dane.gov.co/files/operaciones/IPC"


def extract_dane(year: int, month: int) -> Path:
    """Descarga el Excel de IPC de DANE para un mes/año específico."""
    month_abbr = DANE_MONTH_ABBR[month]
    period = f"{month_abbr}{year}"
    url = f"{DANE_BASE_URL}/{period}/anex-IPC-Indices-{period}.xlsx"
    logger.info(f"Extrayendo IPC Colombia desde DANE — período {period}...")
    response = fetch_with_retry(url)
    filepath = save_raw_bytes(
        content=response.content, source="dane", filename=f"ipc_{year}_{month:02d}.xlsx"
    )
    logger.info(f"OK — {len(response.content)} bytes guardados en {filepath}")
    return filepath


INE_URUGUAY_ODS_URL = (
    "https://www.gub.uy/direccion-general-impositiva/sites/"
    "direccion-general-impositiva/files/2026-02/"
    "%C3%8Dndice%20de%20Precios%20al%20Consumo%202011-2025%20"
    "Base%20octubre%202022_0.ods"
)


def extract_ine_uruguay() -> Path:
    """Descarga la serie de IPC Uruguay (vía DGI, fuente = INE) en .ods."""
    logger.info("Extrayendo IPC Uruguay desde DGI (fuente: INE)...")
    response = fetch_with_retry(INE_URUGUAY_ODS_URL)
    today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    filepath = save_raw_bytes(
        content=response.content, source="ine_uy", filename=f"ipc_{today}.ods"
    )
    logger.info(f"OK — {len(response.content)} bytes guardados en {filepath}")
    return filepath


def register_indec_manual_download(local_csv_path: str) -> Path:
    """Copia un CSV de INDEC descargado a mano hacia data/raw/indec/."""
    source_path = Path(local_csv_path)
    if not source_path.exists():
        raise FileNotFoundError(
            f"No encontré el archivo en {local_csv_path}. "
            f"Confirmá que la ruta es correcta antes de registrar."
        )
    logger.info(f"Registrando descarga manual de INDEC: {source_path}...")
    today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    filepath = save_raw_bytes(
        content=source_path.read_bytes(), source="indec", filename=f"ipc_{today}.csv"
    )
    logger.info(
        f"OK — registrado en {filepath}. Fuente original: descarga manual, no automatizada."
    )
    return filepath


if __name__ == "__main__":
    logger.info("=== LatamPulse — Extracción Día 1 ===")

    try:
        extract_dolarapi()
    except Exception as e:
        logger.error(f"extract_dolarapi() falló: {e}")

    try:
        extract_worldbank()
    except Exception as e:
        logger.error(f"extract_worldbank() falló: {e}")

    try:
        extract_ibge()
    except Exception as e:
        logger.error(f"extract_ibge() falló: {e}")

    try:
        extract_dane(year=2026, month=6)
    except Exception as e:
        logger.error(f"extract_dane() falló: {e}")

    try:
        extract_ine_uruguay()
    except Exception as e:
        logger.error(f"extract_ine_uruguay() falló: {e}")

    try:
        register_indec_manual_download("data/manual/serie_ipc_divisiones.csv")
    except Exception as e:
        logger.error(f"register_indec_manual_download() falló: {e}")

    logger.info("=== Extracción Día 1 finalizada — revisar data/raw/ ===")
