"""
utils.py — Funciones compartidas para todo el pipeline de LatamPulse.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


logger = get_logger("latampulse")

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def save_raw_json(data, source: str, filename_prefix: str) -> Path:
    target_dir = RAW_DATA_DIR / source
    target_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = target_dir / f"{filename_prefix}_{today}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Guardado: {filepath} ({_human_size(filepath)})")
    return filepath


def save_raw_bytes(content: bytes, source: str, filename: str) -> Path:
    target_dir = RAW_DATA_DIR / source
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename
    with open(filepath, "wb") as f:
        f.write(content)
    logger.info(f"Guardado: {filepath} ({_human_size(filepath)})")
    return filepath


def _human_size(path: Path) -> str:
    size_bytes = path.stat().st_size
    for unit in ("B", "KB", "MB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}GB"


def fetch_with_retry(url, max_retries=3, timeout=15, headers=None):
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            last_exception = e
            wait = 2 ** (attempt - 1)
            logger.warning(
                f"Intento {attempt}/{max_retries} falló para {url}: {e}. "
                f"Reintentando en {wait}s..."
            )
            if attempt < max_retries:
                time.sleep(wait)
    logger.error(f"Se agotaron los reintentos para {url}")
    raise last_exception


def build_extraction_envelope(payload, source_name, source_url):
    return {
        "_metadata": {
            "source_name": source_name,
            "source_url": source_url,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        },
        "data": payload,
    }
