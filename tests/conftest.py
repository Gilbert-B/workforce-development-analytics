"""Shared test fixtures.

`dataset` generates the default synthetic data once into a temporary folder
and gives every test the tables as lists of dicts (all values are strings,
exactly as they appear in the CSV files).
"""

import csv
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

import generate_synthetic_data as gen  # noqa: E402

CONFIG = REPO_ROOT / "config" / "build01_synthetic.toml"


def read_tables(folder: Path) -> dict[str, list[dict]]:
    tables = {}
    for path in sorted(folder.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            tables[path.stem] = list(csv.DictReader(f))
    return tables


@pytest.fixture(scope="session")
def config():
    return gen.load_config(CONFIG)


@pytest.fixture(scope="session")
def as_of(config) -> date:
    return date.fromisoformat(config["run"]["as_of_date"])


@pytest.fixture(scope="session")
def generated_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("synthetic")
    gen.generate(CONFIG, out)
    return out


@pytest.fixture(scope="session")
def dataset(generated_dir) -> dict[str, list[dict]]:
    return read_tables(generated_dir)
