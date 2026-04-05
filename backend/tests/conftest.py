from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest


@dataclass
class FakeResult:
    data: Any
    count: int = 0


class FakeStorageBucket:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def upload(self, path: str, file: bytes, file_options: dict[str, Any] | None = None) -> None:
        self.files[path] = bytes(file)

    def download(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def remove(self, paths: list[str]) -> None:
        for path in paths:
            self.files.pop(path, None)


class FakeStorage:
    def __init__(self) -> None:
        self.buckets: dict[str, FakeStorageBucket] = {}

    def from_(self, bucket: str) -> FakeStorageBucket:
        if bucket not in self.buckets:
            self.buckets[bucket] = FakeStorageBucket()
        return self.buckets[bucket]


class FakeTableQuery:
    def __init__(self, supabase: "FakeSupabase", name: str) -> None:
        self.supabase = supabase
        self.name = name
        self._mode = "select"
        self._columns: list[str] | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._order: tuple[str, bool] | None = None
        self._range: tuple[int, int] | None = None
        self._insert_payload: Any = None
        self._update_payload: dict[str, Any] | None = None
        self._on_conflict: str | None = None

    def select(self, columns: str = "*", count: str | None = None) -> "FakeTableQuery":
        if columns != "*":
            self._columns = [item.strip() for item in columns.split(",") if item.strip()]
        return self

    def eq(self, key: str, value: Any) -> "FakeTableQuery":
        self._filters.append(("eq", key, value))
        return self

    def neq(self, key: str, value: Any) -> "FakeTableQuery":
        self._filters.append(("neq", key, value))
        return self

    def in_(self, key: str, values: list[Any]) -> "FakeTableQuery":
        self._filters.append(("in", key, values))
        return self

    def limit(self, value: int) -> "FakeTableQuery":
        self._limit = value
        return self

    def order(self, key: str, desc: bool = False) -> "FakeTableQuery":
        self._order = (key, desc)
        return self

    def range(self, start: int, end: int) -> "FakeTableQuery":
        self._range = (start, end)
        return self

    def insert(self, payload: Any) -> "FakeTableQuery":
        self._mode = "insert"
        self._insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self._mode = "update"
        self._update_payload = payload
        return self

    def upsert(self, payload: dict[str, Any], on_conflict: str | None = None) -> "FakeTableQuery":
        self._mode = "upsert"
        self._insert_payload = payload
        self._on_conflict = on_conflict
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        for op, key, value in self._filters:
            if op == "eq" and row.get(key) != value:
                return False
            if op == "neq" and row.get(key) == value:
                return False
            if op == "in" and row.get(key) not in value:
                return False
        return True

    def execute(self) -> FakeResult:
        rows = self.supabase.tables.setdefault(self.name, [])

        if self._mode == "insert":
            payloads = self._insert_payload if isinstance(self._insert_payload, list) else [self._insert_payload]
            inserted: list[dict[str, Any]] = []
            for payload in payloads:
                row = dict(payload)
                row.setdefault("id", str(uuid4()))
                row.setdefault("created_at", datetime.now(UTC).isoformat())
                rows.append(row)
                inserted.append(row)
            return FakeResult(data=inserted, count=len(inserted))

        if self._mode == "upsert":
            payload = dict(self._insert_payload)
            conflict_key = self._on_conflict
            existing = None
            if conflict_key:
                for row in rows:
                    if row.get(conflict_key) == payload.get(conflict_key):
                        existing = row
                        break

            if existing:
                existing.update(payload)
                return FakeResult(data=[existing], count=1)

            payload.setdefault("id", str(uuid4()))
            payload.setdefault("created_at", datetime.now(UTC).isoformat())
            rows.append(payload)
            return FakeResult(data=[payload], count=1)

        filtered = [row for row in rows if self._matches(row)]

        if self._mode == "update":
            updated: list[dict[str, Any]] = []
            for row in filtered:
                row.update(self._update_payload or {})
                updated.append(row)
            return FakeResult(data=updated, count=len(updated))

        if self._order:
            key, desc = self._order
            filtered = sorted(filtered, key=lambda item: item.get(key), reverse=desc)

        if self._range:
            start, end = self._range
            filtered = filtered[start : end + 1]

        if self._limit is not None:
            filtered = filtered[: self._limit]

        if self._columns:
            filtered = [
                {key: row.get(key) for key in self._columns}
                for row in filtered
            ]

        return FakeResult(data=filtered, count=len(filtered))


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "users": [],
            "datasets": [],
            "analyses": [],
            "bias_reports": [],
            "ai_swarm_results": [],
            "token_blocklist": [],
            "refresh_tokens": [],
            "rate_limit_counters": [],
            "audit_logs": [],
            "runtime_config": [],
        }
        self.storage = FakeStorage()

    def table(self, name: str) -> FakeTableQuery:
        return FakeTableQuery(self, name)


@pytest.fixture
def fake_supabase() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def patch_supabase(monkeypatch: pytest.MonkeyPatch, fake_supabase: FakeSupabase) -> FakeSupabase:
    from app.core import middleware as middleware_module
    from app.core import security as security_module
    from app.routers import analysis as analysis_router
    from app.routers import auth as auth_router
    from app.routers import datasets as datasets_router
    from app.routers import reports as reports_router
    from app.services import ai_swarm_engine as swarm_module

    for module in [
        security_module,
        auth_router,
        datasets_router,
        analysis_router,
        reports_router,
        middleware_module,
        swarm_module,
    ]:
        monkeypatch.setattr(module, "get_supabase_client", lambda: fake_supabase)

    return fake_supabase
