from autoclick_n8n_classifier.service import (
    ClassifyIn,
    RatingIn,
    Settings,
    build_classification_text,
    build_training_text,
    insert_rating,
    load_rating_rows,
    train_model,
    create_app,
)
from fastapi.testclient import TestClient


def test_store_rating_and_build_training_text(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
        min_samples=2,
        interested_rating=4,
    )
    result = insert_rating(
        settings,
        RatingIn(
            rating=5,
            job_id="123",
            job_file="job.html",
            job_title="Python automation workflow",
            country="United Kingdom",
        ),
    )

    rows = load_rating_rows(settings)

    assert result["stored"] is True
    assert result["interested"] is True
    assert len(rows) == 1
    assert "Python automation workflow" in build_training_text(rows[0])


def test_training_waits_for_both_classes(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
        min_samples=2,
        interested_rating=4,
    )
    insert_rating(settings, RatingIn(rating=4, job_title="Python"))
    insert_rating(settings, RatingIn(rating=5, job_title="FastAPI"))

    result = train_model(settings)

    assert result["trained"] is False
    assert result["reason"] == "need_both_classes"


def test_build_classification_text_strips_html():
    text = build_classification_text(
        ClassifyIn(
            title="Build workflow",
            html="<p>Need <strong>n8n</strong> and Python</p>",
        )
    )

    assert text == "Build workflow Need n8n and Python"


def test_rating_webhook_accepts_query_payload(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/ratings",
        params={
            "rating": "1",
            "job_id": "123",
            "job_file": "job.html",
            "job_title": "Cold calling assistant",
        },
    )

    assert response.status_code == 200
    assert response.json()["stored"] is True
    rows = load_rating_rows(settings)
    assert rows[0]["rating"] == 1
    assert rows[0]["interested"] == 0
