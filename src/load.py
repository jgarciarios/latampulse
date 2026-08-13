"""
load.py — Carga los datos transformados a Postgres.
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src.utils import get_logger

logger = get_logger("latampulse.load")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"

DB_USER = os.environ.get("LATAMPULSE_DB_USER", "latampulse")
DB_PASSWORD = os.environ.get("LATAMPULSE_DB_PASSWORD", "latampulse_dev")
DB_HOST = os.environ.get("LATAMPULSE_DB_HOST", "localhost")
DB_PORT = os.environ.get("LATAMPULSE_DB_PORT", "5432")
DB_NAME = os.environ.get("LATAMPULSE_DB_NAME", "latampulse")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def get_engine():
    return create_engine(DATABASE_URL)


def apply_schema(engine) -> None:
    logger.info(f"Aplicando schema desde {SCHEMA_PATH}...")
    sql_text = SCHEMA_PATH.read_text()

    lines_without_comments = [
        line for line in sql_text.splitlines()
        if not line.strip().startswith("--")
    ]
    cleaned_sql = "\n".join(lines_without_comments)

    statements = [s.strip() for s in cleaned_sql.split(";") if s.strip()]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    logger.info(f"Schema aplicado — {len(statements)} sentencias ejecutadas.")


TABLE_CONFIG = {
    "exchange_rates": {"csv": "exchange_rates.csv", "rename": {}},
    "ppp_factors": {"csv": "ppp_factors.csv", "rename": {}},
    "inflation_indices": {"csv": "inflation_indices.csv", "rename": {}},
    "prices": {"csv": "prices.csv", "rename": {"country": "country_code"}},
}


def load_table(engine, table_name: str, config: dict) -> None:
    csv_path = PROCESSED_DIR / config["csv"]
    if not csv_path.exists():
        logger.warning(f"{csv_path} no existe — se omite carga de '{table_name}'")
        return

    df = pd.read_csv(csv_path)
    if config["rename"]:
        df = df.rename(columns=config["rename"])

    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))

    df.to_sql(table_name, engine, if_exists="append", index=False)
    logger.info(f"Cargado: {table_name} ({len(df)} filas desde {csv_path.name})")


if __name__ == "__main__":
    logger.info("=== LatamPulse — Carga a Postgres ===")
    logger.info(f"Conectando a {DB_HOST}:{DB_PORT}/{DB_NAME} como {DB_USER}...")

    engine = get_engine()
    apply_schema(engine)

    for table_name, config in TABLE_CONFIG.items():
        try:
            load_table(engine, table_name, config)
        except Exception as e:
            logger.error(f"Carga de '{table_name}' falló: {e}")

    logger.info("=== Carga finalizada — revisar en pgAdmin ===")
