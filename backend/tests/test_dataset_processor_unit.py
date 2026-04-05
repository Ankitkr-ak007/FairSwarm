from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.services.dataset_processor import DatasetProcessor


def test_load_dataset_csv_and_json_lines(tmp_path: Path) -> None:
    processor = DatasetProcessor()

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("gender,approved\nM,1\nF,0\n", encoding="utf-8")
    csv_df = processor.load_dataset(csv_path, "csv")
    assert list(csv_df.columns) == ["gender", "approved"]
    assert len(csv_df) == 2

    jsonl_path = tmp_path / "sample.json"
    records = [{"gender": "M", "approved": 1}, {"gender": "F", "approved": 0}]
    jsonl_path.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")
    json_df = processor.load_dataset(jsonl_path, "json")
    assert len(json_df) == 2
    assert set(json_df.columns) == {"gender", "approved"}


def test_load_dataset_unsupported_format_raises(tmp_path: Path) -> None:
    processor = DatasetProcessor()
    unsupported = tmp_path / "sample.txt"
    unsupported.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        processor.load_dataset(unsupported, "txt")


def test_detect_sensitive_columns_and_target_column() -> None:
    processor = DatasetProcessor()
    df = pd.DataFrame(
        {
            "customer_gender": ["M", "F", "M", "F"],
            "zip_code": ["10001", "10002", "10003", "10004"],
            "Outcome": [1, 0, 1, 0],
            "feature": [10, 20, 30, 40],
        }
    )

    sensitive = processor.detect_sensitive_columns(df)
    assert "customer_gender" in sensitive
    assert "zip_code" in sensitive

    target = processor.detect_target_column(df)
    assert target == "Outcome"


def test_detect_target_binary_fallback_prefers_fewer_nulls() -> None:
    processor = DatasetProcessor()
    df = pd.DataFrame(
        {
            "candidate_a": [1, 0, 1, 0, None],
            "candidate_b": [1, 0, 1, 0, 1],
            "feature": [5, 4, 3, 2, 1],
        }
    )

    target = processor.detect_target_column(df)
    assert target == "candidate_b"


def test_encode_for_analysis_rejects_missing_columns() -> None:
    processor = DatasetProcessor()
    df = pd.DataFrame({"gender": ["M", "F"], "approved": [1, 0]})

    with pytest.raises(ValueError, match="Target column 'decision' not found"):
        processor.encode_for_analysis(df, sensitive_cols=["gender"], target_col="decision")

    with pytest.raises(ValueError, match="Sensitive columns missing"):
        processor.encode_for_analysis(df, sensitive_cols=["race"], target_col="approved")


def test_encode_for_analysis_with_string_target_and_metadata() -> None:
    processor = DatasetProcessor()
    df = pd.DataFrame(
        {
            "gender": ["M", "F", "M", "F"],
            "city": ["A", "B", "A", "C"],
            "approved": ["yes", "no", "yes", "no"],
        }
    )

    dataset, metadata = processor.encode_for_analysis(
        df,
        sensitive_cols=["gender"],
        target_col="approved",
    )

    assert dataset.labels.shape[0] == 4
    assert set(dataset.labels.flatten().tolist()) == {0.0, 1.0}
    assert "city" in metadata["column_mappings"]
    assert metadata["privileged_groups"]
    assert metadata["unprivileged_groups"]


def test_validate_dataset_collects_errors_and_warnings() -> None:
    processor = DatasetProcessor()
    df = pd.DataFrame(
        {
            "gender": ["M"] * 99 + ["F"],
            "approved": [1] * 100,
            "all_null": [None] * 100,
        }
    )

    result = processor.validate_dataset(df)

    assert result.is_valid is False
    assert any("more than 100 rows" in item for item in result.errors)
    assert any("Columns contain only null values" in item for item in result.errors)
    assert any("only one group" in item or "highly imbalanced" in item for item in result.warnings)


def test_compute_descriptive_stats_includes_sensitive_breakdown() -> None:
    processor = DatasetProcessor()
    df = pd.DataFrame(
        {
            "gender": ["M", "F", "M", "F", "F"],
            "approved": [1, 0, 1, 0, 1],
            "score": [10, 20, 15, 25, 30],
        }
    )

    stats = processor.compute_descriptive_stats(df, sensitive_cols=["gender"])

    assert stats["overall"]["row_count"] == 5
    assert stats["target_column"] == "approved"
    assert "gender" in stats["by_sensitive_attribute"]
    assert "target_distribution" in stats["by_sensitive_attribute"]["gender"]


def test_encode_binary_target_variants() -> None:
    processor = DatasetProcessor()

    bool_series = pd.Series([True, False, True])
    encoded_bool = processor._encode_binary_target(bool_series)
    assert encoded_bool.tolist() == [1, 0, 1]

    numeric_series = pd.Series([5, 9, 5, 9])
    encoded_num = processor._encode_binary_target(numeric_series)
    assert set(encoded_num.tolist()) == {0, 1}

    with pytest.raises(ValueError, match="must be binary"):
        processor._encode_binary_target(pd.Series([1, 2, 3]))
