from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from pydantic import ValidationError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


DEFAULT_DB_PATH = Path(os.environ.get("AUTOCLICK_CLASSIFIER_DB", "./data/ratings.db"))
DEFAULT_MODEL_PATH = Path(os.environ.get("AUTOCLICK_CLASSIFIER_MODEL", "./data/job_classifier.joblib"))
DEFAULT_MIN_SAMPLES = int(os.environ.get("AUTOCLICK_CLASSIFIER_MIN_SAMPLES", "25"))
DEFAULT_THRESHOLD = float(os.environ.get("AUTOCLICK_CLASSIFIER_NOTIFY_THRESHOLD", "0.55"))
DEFAULT_INTERESTED_RATING = int(os.environ.get("AUTOCLICK_CLASSIFIER_INTERESTED_RATING", "4"))
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    model_path: Path = DEFAULT_MODEL_PATH
    min_samples: int = DEFAULT_MIN_SAMPLES
    notify_threshold: float = DEFAULT_THRESHOLD
    interested_rating: int = DEFAULT_INTERESTED_RATING


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    job_id: str = ""
    job_file: str = ""
    job_title: str = ""
    job_url: str = ""
    posted: str = ""
    country: str = ""
    description: str = ""
    source: str = "n8n"
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ClassifyIn(BaseModel):
    job_id: str = ""
    title: str = ""
    description: str = ""
    country: str = ""
    url: str = ""
    html: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: str) -> str:
    without_tags = TAG_RE.sub(" ", html.unescape(value or ""))
    return SPACE_RE.sub(" ", without_tags).strip()


def build_training_text(row: sqlite3.Row) -> str:
    fields = [
        row["job_title"],
        row["description"],
        row["country"],
        row["posted"],
        row["job_url"],
        row["job_file"],
        row["job_id"],
    ]
    return normalize_text(" ".join(item or "" for item in fields))


def build_classification_text(payload: ClassifyIn) -> str:
    return normalize_text(
        " ".join(
            [
                payload.title,
                payload.description,
                payload.country,
                payload.url,
                payload.job_id,
                payload.html,
            ]
        )
    )


def open_db(settings: Settings) -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            interested INTEGER NOT NULL CHECK (interested IN (0, 1)),
            job_id TEXT NOT NULL,
            job_file TEXT NOT NULL,
            job_title TEXT NOT NULL,
            job_url TEXT NOT NULL,
            posted TEXT NOT NULL,
            country TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT NOT NULL,
            raw_payload TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_ratings_job_id_created_at ON ratings(job_id, created_at)"
    )
    connection.commit()
    return connection


def coerce_rating_payload(values: dict[str, Any]) -> RatingIn:
    clean = {key: value for key, value in values.items() if value is not None}
    raw_payload = dict(clean)
    clean.setdefault("raw_payload", raw_payload)
    return RatingIn.model_validate(clean)


async def request_payload(request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = dict(request.query_params)
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        if isinstance(body, dict):
            payload.update(body)
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        payload.update(dict(form))
    return payload


def insert_rating(settings: Settings, payload: RatingIn) -> dict[str, Any]:
    interested = int(payload.rating >= settings.interested_rating)
    with open_db(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO ratings (
                created_at, rating, interested, job_id, job_file, job_title,
                job_url, posted, country, description, source, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                payload.rating,
                interested,
                payload.job_id,
                payload.job_file,
                payload.job_title,
                payload.job_url,
                payload.posted,
                payload.country,
                payload.description,
                payload.source,
                json.dumps(payload.raw_payload, sort_keys=True),
            ),
        )
        connection.commit()
        rating_id = int(cursor.lastrowid)
    return {"stored": True, "rating_id": rating_id, "interested": bool(interested)}


def load_rating_rows(settings: Settings) -> list[sqlite3.Row]:
    with open_db(settings) as connection:
        return list(connection.execute("SELECT * FROM ratings ORDER BY created_at ASC, id ASC"))


def train_model(settings: Settings) -> dict[str, Any]:
    rows = load_rating_rows(settings)
    labels = [int(row["interested"]) for row in rows]
    class_counts = {"low_interest": labels.count(0), "interested": labels.count(1)}
    if len(rows) < settings.min_samples:
        return {
            "trained": False,
            "reason": "not_enough_samples",
            "sample_count": len(rows),
            "min_samples": settings.min_samples,
            "class_counts": class_counts,
        }
    if len(set(labels)) < 2:
        return {
            "trained": False,
            "reason": "need_both_classes",
            "sample_count": len(rows),
            "min_samples": settings.min_samples,
            "class_counts": class_counts,
        }

    texts = [build_training_text(row) for row in rows]
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=5000)),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )

    accuracy: float | None = None
    if len(rows) >= 40 and min(class_counts.values()) >= 5:
        train_texts, test_texts, train_labels, test_labels = train_test_split(
            texts,
            labels,
            test_size=0.25,
            random_state=42,
            stratify=labels,
        )
        pipeline.fit(train_texts, train_labels)
        predictions = pipeline.predict(test_texts)
        accuracy = float(accuracy_score(test_labels, predictions))
    else:
        pipeline.fit(texts, labels)

    settings.model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": pipeline,
            "trained_at": utc_now(),
            "sample_count": len(rows),
            "class_counts": class_counts,
            "interested_rating": settings.interested_rating,
            "accuracy": accuracy,
        },
        settings.model_path,
    )
    return {
        "trained": True,
        "sample_count": len(rows),
        "class_counts": class_counts,
        "accuracy": accuracy,
        "model_path": str(settings.model_path),
    }


def load_model(settings: Settings) -> dict[str, Any] | None:
    if not settings.model_path.exists():
        return None
    return joblib.load(settings.model_path)


def classify_job(settings: Settings, payload: ClassifyIn) -> dict[str, Any]:
    model_bundle = load_model(settings)
    if model_bundle is None:
        return {
            "model_available": False,
            "interested_probability": None,
            "should_notify": True,
            "threshold": settings.notify_threshold,
            "reason": "no_model",
        }

    text = build_classification_text(payload)
    pipeline: Pipeline = model_bundle["pipeline"]
    interested_probability = float(pipeline.predict_proba([text])[0][1])
    return {
        "model_available": True,
        "interested_probability": interested_probability,
        "should_notify": interested_probability >= settings.notify_threshold,
        "threshold": settings.notify_threshold,
        "reason": "classified",
        "trained_at": model_bundle.get("trained_at"),
        "sample_count": model_bundle.get("sample_count"),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title="AutoClick n8n Job Classifier", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "db_path": str(active_settings.db_path),
            "model_path": str(active_settings.model_path),
        }

    @app.post("/ratings")
    async def ratings(request: Request) -> dict[str, Any]:
        try:
            payload = coerce_rating_payload(await request_payload(request))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        result = insert_rating(active_settings, payload)
        return {**result, "rating": payload.rating, "job_id": payload.job_id}

    @app.post("/train")
    def train() -> dict[str, Any]:
        return train_model(active_settings)

    @app.post("/classify")
    def classify(payload: ClassifyIn) -> dict[str, Any]:
        return classify_job(active_settings, payload)

    @app.get("/metrics")
    def metrics() -> dict[str, Any]:
        rows = load_rating_rows(active_settings)
        labels = [int(row["interested"]) for row in rows]
        model_bundle = load_model(active_settings)
        return {
            "sample_count": len(rows),
            "class_counts": {
                "low_interest": labels.count(0),
                "interested": labels.count(1),
            },
            "model_available": model_bundle is not None,
            "trained_at": None if model_bundle is None else model_bundle.get("trained_at"),
            "accuracy": None if model_bundle is None else model_bundle.get("accuracy"),
            "threshold": active_settings.notify_threshold,
            "min_samples": active_settings.min_samples,
        }

    return app


app = create_app()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AutoClick job classifier API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(
        "autoclick_n8n_classifier.service:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
