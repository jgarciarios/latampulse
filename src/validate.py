"""
validate.py — Validación de calidad de datos sobre data/processed/.
Corré con: python -m src.validate
"""

import sys
from pathlib import Path

import pandas as pd

from src.utils import get_logger

logger = get_logger("latampulse.validate")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

VALID_COUNTRIES = {"AR", "BR", "UY", "CO"}


class ValidationResult:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg: str):
        self.errors.append(msg)
        logger.error(msg)

    def warning(self, msg: str):
        self.warnings.append(msg)
        logger.warning(msg)

    def ok(self, msg: str):
        logger.info(f"✅ {msg}")


def validate_prices(result: ValidationResult) -> None:
    path = PROCESSED_DIR / "prices.csv"
    if not path.exists():
        result.error(f"{path} no existe")
        return

    df = pd.read_csv(path)

    dups = df[df.duplicated(subset=["item_name", "country"], keep=False)]
    if len(dups) > 0:
        pares_duplicados = dups[["item_name", "country"]].drop_duplicates().values.tolist()
        result.error(
            f"prices.csv: {len(dups)} filas duplicadas (mismo item_name + country). "
            f"Pares: {pares_duplicados}"
        )
    else:
        result.ok(f"prices.csv: sin duplicados ({len(df)} filas)")

    paises_invalidos = set(df["country"].unique()) - VALID_COUNTRIES
    if paises_invalidos:
        result.error(f"prices.csv: países inesperados encontrados: {paises_invalidos}")
    else:
        result.ok("prices.csv: todos los country_code son válidos (AR/BR/UY/CO)")

    precios_invalidos = df[df["price_local"] <= 0]
    if len(precios_invalidos) > 0:
        result.error(
            f"prices.csv: {len(precios_invalidos)} filas con price_local <= 0: "
            f"{precios_invalidos[['country', 'item_name', 'price_local']].to_dict('records')}"
        )
    else:
        result.ok("prices.csv: todos los price_local son positivos")

    tipos_invalidos = df[~df["price_local"].apply(lambda x: isinstance(x, (int, float)))]
    if len(tipos_invalidos) > 0:
        result.error(
            f"prices.csv: {len(tipos_invalidos)} filas con price_local de tipo "
            f"no-numérico (debería haber sido filtrado por compute_usd_values)"
        )
    else:
        result.ok("prices.csv: price_local es numérico en todas las filas")

    if "source" in df.columns:
        sin_confirmar = (df["source"] == "Fuente sin confirmar — pedir a Juani").sum()
        confirmadas = len(df) - sin_confirmar
        pct = 100 * confirmadas / len(df) if len(df) > 0 else 0
        logger.info(f"ℹ️  prices.csv: {confirmadas}/{len(df)} filas con fuente confirmada ({pct:.0f}%)")


def validate_inflation_indices(result: ValidationResult) -> None:
    path = PROCESSED_DIR / "inflation_indices.csv"
    if not path.exists():
        result.error(f"{path} no existe")
        return

    df = pd.read_csv(path)

    paises_invalidos = set(df["country_code"].unique()) - VALID_COUNTRIES
    if paises_invalidos:
        result.error(f"inflation_indices.csv: países inesperados: {paises_invalidos}")
    else:
        result.ok("inflation_indices.csv: todos los country_code son válidos")

    paises_faltantes = VALID_COUNTRIES - set(df["country_code"].unique())
    if paises_faltantes:
        result.error(f"inflation_indices.csv: faltan países completos: {paises_faltantes}")
    else:
        result.ok("inflation_indices.csv: las 4 fuentes de inflación están presentes")


def validate_exchange_rates(result: ValidationResult) -> None:
    path = PROCESSED_DIR / "exchange_rates.csv"
    if not path.exists():
        result.error(f"{path} no existe")
        return

    df = pd.read_csv(path)

    tasas_invalidas = df[df["rate_to_usd"] <= 0]
    if len(tasas_invalidas) > 0:
        result.error(f"exchange_rates.csv: {len(tasas_invalidas)} filas con rate_to_usd <= 0")
    else:
        result.ok("exchange_rates.csv: todas las tasas son positivas")

    if "AR" not in df["country_code"].unique():
        result.warning(
            "exchange_rates.csv: no hay datos de Argentina — gap conocido, "
            "documentado en AGENTS.md, no bloquea el pipeline"
        )


def validate_ppp_factors(result: ValidationResult) -> None:
    path = PROCESSED_DIR / "ppp_factors.csv"
    if not path.exists():
        result.error(f"{path} no existe")
        return

    df = pd.read_csv(path)

    paises_faltantes = VALID_COUNTRIES - set(df["country_code"].unique())
    if paises_faltantes:
        result.error(f"ppp_factors.csv: faltan países: {paises_faltantes}")
    else:
        result.ok("ppp_factors.csv: los 4 países tienen factor PPP")

    factores_invalidos = df[df["ppp_conversion_factor"] <= 0]
    if len(factores_invalidos) > 0:
        result.error(f"ppp_factors.csv: {len(factores_invalidos)} filas con ppp_conversion_factor <= 0")


if __name__ == "__main__":
    logger.info("=== LatamPulse — Validación de calidad de datos ===")

    result = ValidationResult()

    validate_prices(result)
    validate_inflation_indices(result)
    validate_exchange_rates(result)
    validate_ppp_factors(result)

    logger.info("=== Resumen ===")
    logger.info(f"Errores: {len(result.errors)}")
    logger.info(f"Warnings: {len(result.warnings)}")

    if result.errors:
        logger.error("❌ Validación FALLÓ — corregir antes de confiar en los datos")
        sys.exit(1)
    else:
        logger.info("✅ Validación OK — todos los checks pasaron")
        sys.exit(0)
