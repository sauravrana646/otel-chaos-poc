"""LLM service with per-request mock/OpenRouter selection and no OTel initialization."""

from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel

APP = FastAPI(title="python-llm", version="0.1.0")

DB_DSN = os.getenv(
    "DB_DSN",
    "postgresql://poc_app:poc_app@toxiproxy:5432/poc",
)
MOCK_BASE_URL = os.getenv("PROVIDER_BASE_URL", "http://llm-mock:8080/v1")
OPENROUTER_SECRET_DIR = Path(os.getenv("OPENROUTER_SECRET_DIR", "/var/run/secrets/openrouter"))
BACKOFF_MS = (100, 200)
DB_STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "5000"))


class GenerateRequest(BaseModel):
    request_id: str
    item_id: str
    name: str
    category: str
    context: str
    scenario: str = "normal"
    provider: str = "mock"


class GenerateResponse(BaseModel):
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


@APP.post("/generate", response_model=GenerateResponse)
def generate(body: GenerateRequest) -> GenerateResponse:
    existing = _read_existing(body.request_id)
    if existing is not None:
        return GenerateResponse(result=existing["result"], model=existing["model"], status="ok")

    api_key, base_url, provider_model, max_attempts, attempt_timeout = _provider_config(body.provider)
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        timeout=attempt_timeout,
    )

    prompt = (
        f"Recommend next action for item {body.item_id} ({body.name}/{body.category}). "
        f"Context: {body.context}. scenario={body.scenario}"
    )

    last_error: Exception | None = None
    completion_text = ""
    model_name = provider_model

    for attempt in range(1, max_attempts + 1):
        try:
            extra_headers = {"X-Request-Id": body.request_id, "X-POC-Scenario": body.scenario}
            streaming = body.scenario == "stream"
            resp = client.chat.completions.create(
                model=provider_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=128,
                extra_headers=extra_headers,
                stream=streaming,
            )
            if streaming:
                parts: list[str] = []
                for chunk in resp:
                    model_name = chunk.model or model_name
                    if chunk.choices and chunk.choices[0].delta.content:
                        parts.append(chunk.choices[0].delta.content)
                completion_text = "".join(parts).strip()
            else:
                completion_text = resp.choices[0].message.content or ""
                model_name = resp.model or provider_model
            last_error = None
            break
        except (APIStatusError, APIConnectionError) as exc:
            last_error = exc
            retryable = _retryable(exc)
            if not retryable or attempt >= max_attempts:
                break
            delay = BACKOFF_MS[min(attempt - 1, len(BACKOFF_MS) - 1)] / 1000.0
            delay += random.uniform(0, 0.05)
            time.sleep(delay)

    if last_error is not None:
        raise HTTPException(status_code=502, detail=f"provider failed after retries: {last_error}")

    _persist(body.request_id, body.item_id, completion_text, model_name)
    return GenerateResponse(result=completion_text, model=model_name, status="ok")


def _provider_config(provider: str) -> tuple[str, str, str, int, float]:
    if provider == "mock":
        return "mock-key", MOCK_BASE_URL, "mock-gpt", 3, 2.0
    if provider != "openrouter":
        raise HTTPException(status_code=400, detail="provider not allowlisted")
    key_path = OPENROUTER_SECRET_DIR / "api-key"
    model_path = OPENROUTER_SECRET_DIR / "model"
    if not key_path.is_file() or not model_path.is_file():
        raise HTTPException(status_code=503, detail="OpenRouter credentials are not configured")
    return (
        key_path.read_text().strip(),
        "https://openrouter.ai/api/v1",
        model_path.read_text().strip(),
        3,
        10.0,
    )


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, APIConnectionError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {429, 503}
    return False


def _read_existing(request_id: str) -> dict[str, Any] | None:
    with _connect_db() as conn:
        row = conn.execute(
            "SELECT result_text, model_name FROM recommendations WHERE request_id = %s",
            (request_id,),
        ).fetchone()
    if row is None:
        return None
    return {"result": row[0], "model": row[1]}


def _persist(request_id: str, item_id: str, result: str, model: str) -> None:
    with _connect_db() as conn:
        conn.execute(
            """
            INSERT INTO recommendations (request_id, item_id, result_text, model_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (request_id) DO NOTHING
            """,
            (request_id, item_id, result, model),
        )
        conn.commit()


def _connect_db() -> psycopg.Connection[Any]:
    """Bound both connection establishment and statements for fault scenarios."""
    return psycopg.connect(
        DB_DSN,
        connect_timeout=2,
        options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}",
    )
