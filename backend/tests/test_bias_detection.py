from __future__ import annotations

import pandas as pd
import pytest

from app.services.dataset_processor import DatasetProcessor
from app.services.fairness_metrics import FairnessMetricsEngine


def _biased_dataframe() -> pd.DataFrame:
    rows: list[dict[str, int]] = []
    for index in range(200):
        gender = 0 if index < 100 else 1
        # strong disparity: group 0 mostly approved, group 1 mostly denied
        approved = 1 if (gender == 0 and index % 10 != 0) or (gender == 1 and index % 20 == 0) else 0
        rows.append({"gender": gender, "approved": approved, "score": index % 50})
    return pd.DataFrame(rows)


def test_fairness_metrics_engine_on_biased_dataset():
    processor = DatasetProcessor()
    engine = FairnessMetricsEngine()

    df = _biased_dataframe()
    dataset, _ = processor.encode_for_analysis(df, sensitive_cols=["gender"], target_col="approved")
    result = engine.compute_all_metrics(dataset, sensitive_attr="gender")

    metrics = {metric.metric_name: metric for metric in result.metrics}
    assert result.fairness_score <= 70
    assert "Disparate Impact Ratio" in metrics
    assert metrics["Disparate Impact Ratio"].is_fair is False


def test_single_class_target_raises_value_error():
    processor = DatasetProcessor()
    df = pd.DataFrame(
        {
            "gender": [0, 1, 0, 1],
            "approved": [1, 1, 1, 1],
            "score": [10, 20, 30, 40],
        }
    )

    with pytest.raises(ValueError):
        processor.encode_for_analysis(df, sensitive_cols=["gender"], target_col="approved")


def test_intersectional_edge_case_no_sensitive_attributes():
    engine = FairnessMetricsEngine()
    df = pd.DataFrame(
        {
            "approved": [1, 0, 1, 0, 1],
            "score": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
    )

    result = engine.compute_intersectional_bias(df, sensitive_cols=[], target_col="approved")
    assert result["combination_count"] == 0
    assert result["top_disparities"] == []
