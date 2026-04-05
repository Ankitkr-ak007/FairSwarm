from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from app.core.database import get_supabase_client
from app.core.security import hash_password
from app.services.dataset_processor import DatasetProcessor
from app.services.fairness_metrics import FairnessMetricsEngine

DEMO_EMAIL = "demo@fairswarm.ai"
DEMO_PASSWORD = "Demo@123456"


def _compas_sample(rows: int = 400) -> pd.DataFrame:
    records = []
    for index in range(rows):
        race = "African-American" if index % 3 == 0 else "Caucasian"
        gender = "Male" if index % 2 == 0 else "Female"
        approved = 0 if race == "African-American" and index % 4 != 0 else 1
        records.append(
            {
                "race": race,
                "gender": gender,
                "risk_score": (index % 10) + 1,
                "approved": approved,
            }
        )
    return pd.DataFrame(records)


def _adult_sample(rows: int = 500) -> pd.DataFrame:
    records = []
    for index in range(rows):
        gender = "Female" if index % 2 == 0 else "Male"
        education = "Bachelors" if index % 3 == 0 else "HS-grad"
        income_high = 1 if (gender == "Male" and index % 4 != 0) else 0
        records.append(
            {
                "gender": gender,
                "education": education,
                "hours_per_week": 30 + (index % 25),
                "income_high": income_high,
            }
        )
    return pd.DataFrame(records)


def _ensure_demo_user() -> dict:
    supabase = get_supabase_client()
    existing = supabase.table("users").select("*").eq("email", DEMO_EMAIL).limit(1).execute()
    existing_user = existing.data[0] if existing.data else None
    if existing_user:
        return existing_user

    created = (
        supabase.table("users")
        .insert(
            {
                "email": DEMO_EMAIL,
                "hashed_password": hash_password(DEMO_PASSWORD),
                "full_name": "FairSwarm Demo",
                "organization": "FairSwarm Hackathon Demo",
                "is_active": True,
            }
        )
        .execute()
    )
    return created.data[0]


def _upload_dataset(user_id: str, name: str, df: pd.DataFrame, bucket_path: str) -> dict:
    processor = DatasetProcessor()
    supabase = get_supabase_client()

    with NamedTemporaryFile(delete=False, suffix=".csv") as temp:
        temp_path = Path(temp.name)
        df.to_csv(temp_path, index=False)

    file_bytes = temp_path.read_bytes()
    supabase.storage.from_("datasets").upload(bucket_path, file_bytes, {"content-type": "text/csv", "upsert": "true"})

    profile = processor.profile_dataset(df)
    sensitive_cols = processor.detect_sensitive_columns(df)

    result = (
        supabase.table("datasets")
        .insert(
            {
                "user_id": user_id,
                "name": name,
                "description": "Demo seeded dataset",
                "file_path": bucket_path,
                "file_size": len(file_bytes),
                "columns": profile,
                "row_count": profile["row_count"],
                "sensitive_columns": sensitive_cols,
                "status": "uploaded",
            }
        )
        .execute()
    )

    temp_path.unlink(missing_ok=True)
    return result.data[0]


def _run_analysis_for_dataset(user_id: str, dataset: dict, target_column: str, sensitive_columns: list[str]) -> None:
    processor = DatasetProcessor()
    engine = FairnessMetricsEngine()
    supabase = get_supabase_client()

    file_bytes = supabase.storage.from_("datasets").download(dataset["file_path"])
    with NamedTemporaryFile(delete=False, suffix=".csv") as temp:
        temp_path = Path(temp.name)
        temp.write(file_bytes)

    df = processor.load_dataset(str(temp_path), "csv")
    encoded, _ = processor.encode_for_analysis(df, sensitive_columns, target_column)

    fairness = {attr: engine.compute_all_metrics(encoded, attr).model_dump() for attr in sensitive_columns}
    intersectional = engine.compute_intersectional_bias(df, sensitive_columns, target_column)

    analysis_result = (
        supabase.table("analyses")
        .insert(
            {
                "dataset_id": dataset["id"],
                "user_id": user_id,
                "status": "completed",
                "progress": 100,
                "swarm_config": {
                    "analysis_name": f"Seeded analysis - {dataset['name']}",
                    "sensitive_columns": sensitive_columns,
                    "target_column": target_column,
                },
            }
        )
        .execute()
    )
    analysis = analysis_result.data[0]

    overall_score = sum(item["fairness_score"] for item in fairness.values()) / max(len(fairness), 1)
    recommendations = []
    for payload in fairness.values():
        recommendations.extend(payload.get("mitigations", []))

    supabase.table("bias_reports").insert(
        {
            "analysis_id": analysis["id"],
            "overall_score": round(overall_score, 2),
            "fairness_metrics": {
                "metrics_by_sensitive_attribute": fairness,
                "intersectional_bias": intersectional,
            },
            "sensitive_attribute": ",".join(sensitive_columns),
            "model_recommendations": recommendations,
            "swarm_consensus": {"status": "seeded"},
        }
    ).execute()

    temp_path.unlink(missing_ok=True)


async def main() -> None:
    user = _ensure_demo_user()
    user_id = user["id"]

    compas = _upload_dataset(user_id, "COMPAS Sample", _compas_sample(), f"{user_id}/compas_seed.csv")
    adult = _upload_dataset(user_id, "Adult Income Sample", _adult_sample(), f"{user_id}/adult_seed.csv")

    _run_analysis_for_dataset(user_id, compas, target_column="approved", sensitive_columns=["race", "gender"])
    _run_analysis_for_dataset(user_id, adult, target_column="income_high", sensitive_columns=["gender"])

    print("Seed completed successfully")
    print(f"Demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
