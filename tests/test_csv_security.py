"""Exercise CSV neutralization through SQLite export, without altering stored values."""
import csv
from io import StringIO
from pathlib import Path

import pytest

import learning_app.db as db_module
from learning_app.db import connection_scope
from learning_app.services import experiment_analytics


@pytest.fixture()
def export_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "csv-security.db")
    with connection_scope() as connection:
        connection.execute(
            "CREATE TABLE csv_security_values "
            "(reviewer TEXT, notes TEXT, integer_value INTEGER, real_value REAL, nullable_value TEXT)"
        )
    monkeypatch.setitem(experiment_analytics.EXPORT_DATASETS, "csv_security_fixture", {
        "source_name": "csv_security_fixture",
        "query": "SELECT * FROM csv_security_values",
    })


def export_row(reviewer: str, notes: str = "Grüße aus Zürich") -> tuple[dict[str, str], tuple, tuple]:
    with connection_scope() as connection:
        connection.execute(
            "INSERT INTO csv_security_values VALUES (?, ?, ?, ?, ?)",
            (reviewer, notes, -42, -12.5, None),
        )
        before = tuple(connection.execute("SELECT * FROM csv_security_values").fetchone())
    payload, filename = experiment_analytics.export_experiment_dataset_csv("csv_security_fixture")
    assert filename == "csv_security_fixture.csv"
    parsed = list(csv.DictReader(StringIO(payload, newline="")))
    assert len(parsed) == 1
    with connection_scope() as connection:
        after = tuple(connection.execute("SELECT * FROM csv_security_values").fetchone())
    return parsed[0], before, after


@pytest.mark.parametrize("value", [
    "=1+1", "+SUM(1,2)", "-SUM(1,2)", "@SUM(1,2)",
    "  =1+1", " \t+SUM(1,2)", "\x00=1+1",
    "\ufeff=1+1", " \ufeff-1+1", "\u2003@SUM(1,2)",
    "\t=1+1", "\r=1+1", "\n=1+1",
    "\tMünchen", "\rZürich", "\nGrüße",
])
def test_export_neutralizes_formula_like_text_and_preserves_database(export_dataset: None, value: str) -> None:
    parsed, before, after = export_row(value)
    assert parsed["reviewer"] == "'" + value
    assert before == after
    assert after[0] == value


@pytest.mark.parametrize("value", [
    "Müller, Zürich", 'Er sagt "Grüße".', "Zeile eins\nZeile zwei",
    "Grüße – schön! 😊", "O'Connor", "00123", "", "   ", "'=1+1",
])
def test_export_preserves_ordinary_text_special_characters_and_unicode(
    export_dataset: None, value: str
) -> None:
    notes = 'Grüße, "Zürich"\nZweite Zeile.'
    parsed, before, after = export_row(value, notes)
    assert parsed["reviewer"] == value
    assert parsed["notes"] == notes
    assert before == after


def test_export_keeps_numeric_values_numeric_and_nulls_empty(export_dataset: None) -> None:
    parsed, before, after = export_row("fictional reviewer")
    assert parsed["integer_value"] == "-42"
    assert parsed["real_value"] == "-12.5"
    assert parsed["nullable_value"] == ""
    assert isinstance(after[2], int)
    assert isinstance(after[3], float)
    assert after[4] is None
    assert before == after
