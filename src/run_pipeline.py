"""
run_pipeline.py — Orquesta el pipeline completo de LatamPulse.

Fase 1 (extracción): corre las 5 fuentes automatizables (dolarapi, World
Bank, IBGE, DANE, INE Uruguay). INDEC NO se re-extrae acá porque requiere
descarga manual — usa el archivo que ya esté en data/raw/indec/.

Fase 2 (transformación): lee el archivo más reciente de cada fuente,
aplica la función de transform correspondiente, une las 4 series de
inflación en una sola tabla, procesa el research manual (Excel) y calcula
USD nominal/PPP, y guarda todo en data/processed/ como CSV.
"""

from pathlib import Path

import pandas as pd

from src.extract import (
    extract_dolarapi,
    extract_worldbank,
    extract_ibge,
    extract_dane,
    extract_ine_uruguay,
)
from src.transform import (
    load_latest_raw,
    transform_dolarapi,
    transform_worldbank,
    transform_ibge,
    transform_dane,
    transform_ine_uruguay,
    transform_indec,
    compute_usd_values,
)
from src.utils import get_logger

logger = get_logger("latampulse.pipeline")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MANUAL_RESEARCH_PATH = PROJECT_ROOT / "data" / "manual" / "research_template_1.xlsx"


def run_extraction(dane_year: int = 2026, dane_month: int = 6) -> None:
    logger.info("=== Fase 1: Extracción ===")
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
        extract_dane(year=dane_year, month=dane_month)
    except Exception as e:
        logger.error(f"extract_dane() falló: {e}")
    try:
        extract_ine_uruguay()
    except Exception as e:
        logger.error(f"extract_ine_uruguay() falló: {e}")
    logger.info("Extracción finalizada. INDEC no se re-extrae (requiere descarga manual).")


def run_transformation() -> dict:
    logger.info("=== Fase 2: Transformación ===")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    try:
        p = load_latest_raw("exchange_rates", "json")
        results["exchange_rates"] = transform_dolarapi(p)
    except Exception as e:
        logger.error(f"transform_dolarapi falló: {e}")

    try:
        p = load_latest_raw("worldbank", "json")
        results["ppp_factors"] = transform_worldbank(p)
    except Exception as e:
        logger.error(f"transform_worldbank falló: {e}")

    inflation_frames = []
    for source, ext, fn in [
        ("ibge", "json", transform_ibge),
        ("dane", "xlsx", transform_dane),
        ("ine_uy", "ods", transform_ine_uruguay),
        ("indec", "csv", transform_indec),
    ]:
        try:
            p = load_latest_raw(source, ext)
            inflation_frames.append(fn(p))
        except Exception as e:
            logger.error(f"transform de '{source}' falló: {e}")

    if inflation_frames:
        results["inflation_indices"] = pd.concat(inflation_frames, ignore_index=True)

    try:
        prices_raw = pd.read_excel(MANUAL_RESEARCH_PATH, sheet_name="Research")
        prices_raw = prices_raw.dropna(subset=["country", "price_local"])

        if "exchange_rates" in results and "ppp_factors" in results:
            results["prices"] = compute_usd_values(
                prices_raw, results["exchange_rates"], results["ppp_factors"]
            )
        else:
            logger.warning(
                "Faltan exchange_rates o ppp_factors — 'prices' se guarda "
                "sin USD nominal/PPP calculated"
            )
            results["prices"] = prices_raw
    except Exception as e:
        logger.error(f"Procesamiento del research manual falló: {e}")

    for name, df in results.items():
        if df is not None and not df.empty:
            out_path = PROCESSED_DIR / f"{name}.csv"
            df.to_csv(out_path, index=False)
            logger.info(f"Guardado: {out_path} ({len(df)} filas)")
        else:
            logger.warning(f"'{name}' quedó vacío, no se guarda archivo")

    return results


if __name__ == "__main__":
    run_extraction()
    results = run_transformation()

    logger.info("=== Resumen final ===")
    expected = ["exchange_rates", "ppp_factors", "inflation_indices", "prices"]
    for name in expected:
        status = "OK" if name in results and not results[name].empty else "FALTANTE"
        rows = len(results[name]) if name in results else 0
        logger.info(f"  {name}: {status} ({rows} filas)")
