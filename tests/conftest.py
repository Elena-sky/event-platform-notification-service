"""Load test env before importing ``app``."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / "test.env", override=True)
