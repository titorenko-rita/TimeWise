import logging
from pathlib import Path


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "service.log", encoding="utf-8"),
            logging.StreamHandler()
        ],
    )


def get_logger(name: str):
    return logging.getLogger(name)