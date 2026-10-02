"""Python analysis API — no OpenTelemetry initialization in application code."""

from __future__ import annotations

import os
from typing import Any

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

APP = FastAPI(title="python-analysis", version="0.1.0")

DB_DSN = os.getenv(
    "DB_DSN",
    "postgresql://poc_app:poc_app@toxiproxy:5432/poc",
)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://toxiproxy-llm:8080")
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "35"))
DB_STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "5000"))
ALLOWED_SCENARIOS = {"normal", "slow-db", "retry-success", "retry-exhaust", "stream"}


class AnalyzeRequest(BaseModel):
    request_id: str
    item_id: str
    name: str
    category: str
    scenario: str = "normal"


class AnalyzeResponse(BaseModel):
    result: str
    model: str | None = None
    status: str


@APP.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@APP.get("/readyz")
def readyz() -> dict[str, str]:
    with _connect_db() as conn:
        conn.execute("SELECT 1")
    return {"status": "ready"}


@APP.post("/analyze", response_model=AnalyzeResponse)
def analyze(body: AnalyzeRequest) -> AnalyzeResponse:
    if body.scenario not in ALLOWED_SCENARIOS:
        raise HTTPException(status_code=400, detail="scenario not allowlisted")

    context = _load_context(body.item_id, body.scenario)
    payload = {
        "request_id": body.request_id,
        "item_id": body.item_id,
        "name": body.name,
        "category": body.category,
        "context": context,
        "scenario": body.scenario,
    }

    try:
        with httpx.Client(base_url=LLM_BASE_URL, timeout=LLM_REQUEST_TIMEOUT) as client:
            resp = client.post("/generate", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"llm dependency unavailable: {exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"llm dependency error: {resp.status_code}")

    data: dict[str, Any] = resp.json()
    return AnalyzeResponse(
        result=data.get("result", ""),
        model=data.get("model"),
        status=data.get("status", "ok"),
    )


def _load_context(item_id: str, scenario: str) -> str:
    with _connect_db() as conn:
        if scenario == "slow-db":
            conn.execute("SELECT pg_sleep(0.5)")
        row = conn.execute(
            "SELECT context_text FROM item_context WHERE item_id = %s",
            (item_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown item context")
    return str(row[0])


def _connect_db() -> psycopg.Connection[Any]:
    return psycopg.connect(
        DB_DSN,
        connect_timeout=2,
        options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}",
    )
