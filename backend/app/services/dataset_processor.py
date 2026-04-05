from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from aif360.datasets import BinaryLabelDataset
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    target_column: str | None = None
    sensitive_columns: list[str] = Field(default_factory=list)


class DatasetProcessor:
    _sensitive_keywords = {
        "gender",
        "sex",
        "race",
        "ethnicity",
        "ethnic",
        "age",
        "religion",
        "faith",
        "nationality",
        "citizenship",
        "disability",
        "handicap",
        "marital_status",
        "marital",
        "zip",
        "zipcode",
        "zip_code",
        "postal",
        "postal_code",
        "pregnant",
        "veteran",
        "language",
    }

    _target_keywords = [
        "target",
        "label",
        "outcome",
        "decision",
        "approved",
        "approval",
        "hired",
        "selected",
        "passed",
        "default",
        "fraud",
        "risk",
        "status",
        "result",
        "churn",
    ]

    def load_dataset(self, file_path: str | Path, file_type: str) -> pd.DataFrame:
        normalized_type = file_type.lower().replace(".", "").strip()
        path = str(file_path)

        if normalized_type == "csv":
            encodings_to_try = ["utf-8", "utf-8-sig", "cp1252", "latin1"]
            last_error: Exception | None = None
            for encoding in encodings_to_try:
                try:
                    return pd.read_csv(path, encoding=encoding)
                except Exception as exc:
                    last_error = exc
            raise ValueError(f"Unable to decode CSV file. Last error: {last_error}")

        if normalized_type in {"xls", "xlsx"}:
            try:
                return pd.read_excel(path, engine="openpyxl")
            except Exception as exc:
                raise ValueError(f"Unable to read Excel file: {exc}") from exc

        if normalized_type == "json":
            try:
                return pd.read_json(path)
            except ValueError:
                try:
                    return pd.read_json(path, lines=True)
                except Exception as exc:
                    raise ValueError(f"Unable to parse JSON file: {exc}") from exc

        raise ValueError("Unsupported file format. Allowed formats are CSV, Excel, and JSON.")

    def profile_dataset(self, df: pd.DataFrame) -> dict[str, Any]:
        sample_rows = df.head(5).replace({np.nan: None}).to_dict(orient="records")
        return {
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "null_counts": {col: int(df[col].isna().sum()) for col in df.columns},
            "unique_counts": {col: int(df[col].nunique(dropna=True)) for col in df.columns},
            "row_count": int(len(df)),
            "file_size": int(df.memory_usage(deep=True).sum()),
            "sample_rows": sample_rows,
        }

    def detect_sensitive_columns(self, df: pd.DataFrame) -> list[str]:
        detected: set[str] = set()
        row_count = max(len(df), 1)

        for column in df.columns:
            normalized = str(column).lower().replace("-", "_").replace(" ", "_")
            if any(keyword in normalized for keyword in self._sensitive_keywords):
                detected.add(column)
                continue

            series = df[column]
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_categorical_dtype(series):
                unique_count = int(series.nunique(dropna=True))
                if 2 <= unique_count <= min(30, max(2, int(row_count * 0.1))):
                    detected.add(column)

        return sorted(detected)

    def detect_target_column(self, df: pd.DataFrame) -> str | None:
        lowered_map: dict[str, str] = {str(col).lower(): str(col) for col in df.columns}

        for keyword in self._target_keywords:
            for lowered, original in lowered_map.items():
                if keyword == lowered or keyword in lowered:
                    return original

        candidate_columns: list[tuple[str, int]] = []
        for column in df.columns:
            unique_count = int(df[column].dropna().nunique())
            if unique_count == 2:
                null_count = int(df[column].isna().sum())
                candidate_columns.append((column, null_count))

        if candidate_columns:
            candidate_columns.sort(key=lambda item: item[1])
            return candidate_columns[0][0]

        return None

    def encode_for_analysis(
        self,
        df: pd.DataFrame,
        sensitive_cols: list[str],
        target_col: str,
    ) -> tuple[BinaryLabelDataset, dict[str, Any]]:
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in dataset.")

        missing_sensitive = [col for col in sensitive_cols if col not in df.columns]
        if missing_sensitive:
            raise ValueError(f"Sensitive columns missing in dataset: {missing_sensitive}")

        required_cols = [target_col, *sensitive_cols]
        working_df = df.dropna(subset=required_cols).copy()
        if working_df.empty:
            raise ValueError("No rows available after removing missing target/sensitive values.")

        encoded_df = working_df.copy()
        encoding_metadata: dict[str, Any] = {
            "column_mappings": {},
            "privileged_groups": [],
            "unprivileged_groups": [],
        }

        encoded_target = self._encode_binary_target(encoded_df[target_col])
        encoded_df[target_col] = encoded_target

        for column in encoded_df.columns:
            if column == target_col:
                continue

            if pd.api.types.is_numeric_dtype(encoded_df[column]):
                encoded_df[column] = pd.to_numeric(encoded_df[column], errors="coerce").fillna(0)
                continue

            codes, uniques = pd.factorize(encoded_df[column].astype(str), sort=True)
            encoded_df[column] = codes
            encoding_metadata["column_mappings"][column] = {
                str(value): int(index) for index, value in enumerate(uniques.tolist())
            }

        for sensitive_col in sensitive_cols:
            value_counts = encoded_df[sensitive_col].value_counts()
            privileged_value = int(value_counts.index[0])
            unprivileged_value = int(value_counts.index[-1])
            encoding_metadata["privileged_groups"].append({sensitive_col: privileged_value})
            encoding_metadata["unprivileged_groups"].append({sensitive_col: unprivileged_value})

        numeric_df = encoded_df.apply(pd.to_numeric, errors="coerce").fillna(0.0)
        numeric_df[target_col] = numeric_df[target_col].astype(float)

        dataset = BinaryLabelDataset(
            df=numeric_df,
            label_names=[target_col],
            protected_attribute_names=sensitive_cols,
            favorable_label=1.0,
            unfavorable_label=0.0,
        )
        return dataset, encoding_metadata

    def validate_dataset(self, df: pd.DataFrame) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if len(df) <= 100:
            errors.append("Dataset must contain more than 100 rows for reliable bias analysis.")

        target_column = self.detect_target_column(df)
        if target_column is None:
            errors.append("No target/decision column detected. Please specify one.")

        all_null_columns = [column for column in df.columns if df[column].isna().all()]
        if all_null_columns:
            errors.append(f"Columns contain only null values: {all_null_columns}")

        sensitive_columns = self.detect_sensitive_columns(df)
        for sensitive_col in sensitive_columns:
            series = df[sensitive_col]
            distribution = series.value_counts(normalize=True, dropna=True)
            if distribution.empty:
                warnings.append(f"Sensitive attribute '{sensitive_col}' has no usable values.")
                continue
            if len(distribution) < 2:
                warnings.append(f"Sensitive attribute '{sensitive_col}' has only one group.")
            if float(distribution.max()) > 0.98:
                warnings.append(
                    f"Sensitive attribute '{sensitive_col}' is highly imbalanced. "
                    "Bias metrics may be unstable."
                )

        return ValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
            target_column=target_column,
            sensitive_columns=sensitive_columns,
        )

    def compute_descriptive_stats(self, df: pd.DataFrame, sensitive_cols: list[str]) -> dict[str, Any]:
        target_col = self.detect_target_column(df)
        overall_stats: dict[str, Any] = {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "numeric_summary": df.describe(include=[np.number]).replace({np.nan: None}).to_dict(),
        }

        sensitive_stats: dict[str, Any] = {}
        for sensitive_col in sensitive_cols:
            if sensitive_col not in df.columns:
                continue

            counts = df[sensitive_col].value_counts(dropna=False).to_dict()
            percentages = (
                df[sensitive_col].value_counts(dropna=False, normalize=True).mul(100).round(2).to_dict()
            )
            entry: dict[str, Any] = {
                "counts": {str(key): int(value) for key, value in counts.items()},
                "percentages": {str(key): float(value) for key, value in percentages.items()},
            }

            if target_col and target_col in df.columns:
                grouped = (
                    df[[sensitive_col, target_col]]
                    .dropna()
                    .groupby(sensitive_col)[target_col]
                    .agg(["count", "mean"])
                    .rename(columns={"mean": "positive_rate"})
                )
                entry["target_distribution"] = grouped.replace({np.nan: None}).to_dict(orient="index")

            sensitive_stats[sensitive_col] = entry

        return {
            "overall": overall_stats,
            "by_sensitive_attribute": sensitive_stats,
            "target_column": target_col,
        }

    def _encode_binary_target(self, series: pd.Series) -> pd.Series:
        if pd.api.types.is_bool_dtype(series):
            return series.astype(int)

        if pd.api.types.is_numeric_dtype(series):
            unique_values = sorted(series.dropna().unique().tolist())
            if len(unique_values) != 2:
                raise ValueError("Target column must be binary for fairness analysis.")
            return series.map({unique_values[0]: 0, unique_values[1]: 1}).astype(int)

        normalized = series.astype(str).str.strip().str.lower()
        positive_tokens = {"1", "true", "yes", "approved", "accept", "accepted", "hired", "pass", "passed"}
        negative_tokens = {"0", "false", "no", "rejected", "reject", "denied", "failed"}

        token_values = set(normalized.dropna().unique().tolist())
        if token_values and token_values.issubset(positive_tokens.union(negative_tokens)):
            return normalized.apply(lambda value: 1 if value in positive_tokens else 0).astype(int)

        values = sorted(normalized.dropna().unique().tolist())
        if len(values) != 2:
            raise ValueError("Target column must be binary for fairness analysis.")

        mapping = {values[0]: 0, values[1]: 1}
        return normalized.map(mapping).astype(int)
