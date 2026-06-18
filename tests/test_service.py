from autoclick_n8n_classifier.service import (
    ClassifyIn,
    RatingIn,
    Settings,
    backfill_ratings_from_jobs,
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


def test_rating_endpoint_returns_422_for_missing_rating(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    response = client.post("/ratings", json={"source": "telegram"})

    assert response.status_code == 422
    assert load_rating_rows(settings) == []


def test_rating_endpoint_accepts_stringified_raw_payload(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/ratings",
        json={
            "rating": 5,
            "job_id": "n8n-stringified-raw",
            "source": "telegram",
            "raw_payload": "[object Object]",
        },
    )

    assert response.status_code == 200
    assert response.json()["stored"] is True


def test_rating_uses_stored_job_html_when_rating_payload_is_thin(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    job_response = client.post(
        "/jobs",
        json={
            "job_id": "html-job-1",
            "job_file": "html-job-1.html",
            "job_title": "Thin title",
            "job_html": "<article><h1>Zapier migration</h1><p>Build Python n8n API automation.</p></article>",
        },
    )
    rating_response = client.post(
        "/ratings",
        json={
            "rating": 5,
            "job_id": "html-job-1",
            "source": "telegram",
        },
    )

    rows = load_rating_rows(settings)

    assert job_response.status_code == 200
    assert rating_response.status_code == 200
    assert "Build Python n8n API automation" in build_training_text(rows[0])
    assert rows[0]["job_title"] == "Thin title"


def test_metrics_reports_payload_coverage(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    job_response = client.post(
        "/jobs",
        json={
            "job_id": "coverage-job-1",
            "job_file": "coverage-job-1.html",
            "job_html": "<article><p>Python automation with n8n.</p></article>",
            "raw_payload": {"source_event": "capture"},
        },
    )
    rating_response = client.post(
        "/ratings",
        json={
            "rating": 5,
            "job_id": "coverage-job-1",
            "raw_payload": {"source_event": "rating-click"},
        },
    )
    metrics_response = client.get("/metrics")

    assert job_response.status_code == 200
    assert rating_response.status_code == 200
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert metrics["payload_stats"]["jobs"]["with_html"] == 1
    assert metrics["payload_stats"]["jobs"]["with_raw_payload"] == 1
    assert metrics["payload_stats"]["ratings"]["with_text"] == 1
    assert metrics["payload_stats"]["ratings"]["with_raw_payload"] == 1


def test_backfill_existing_rating_from_stored_job_html(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    rating_response = client.post(
        "/ratings",
        json={
            "rating": 5,
            "job_file": "historical-job.html",
            "source": "telegram",
        },
    )
    job_response = client.post(
        "/jobs",
        json={
            "job_file": "historical-job.html",
            "job_title": "Historical automation job",
            "job_html": "<article><p>Need a Python n8n workflow imported from old HTML.</p></article>",
        },
    )

    result = backfill_ratings_from_jobs(settings)
    rows = load_rating_rows(settings)

    assert rating_response.status_code == 200
    assert job_response.status_code == 200
    assert result["checked"] == 1
    assert result["matched"] == 1
    assert result["updated"] == 1
    assert "Python n8n workflow imported from old HTML" in build_training_text(rows[0])


def test_backfill_endpoint_reports_payload_stats(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    client.post("/ratings", json={"rating": 5, "job_file": "endpoint-backfill.html"})
    client.post(
        "/jobs",
        json={
            "job_file": "endpoint-backfill.html",
            "job_html": "<article><p>Endpoint backfill text.</p></article>",
        },
    )

    response = client.post("/backfill-ratings")

    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert response.json()["payload_stats"]["ratings"]["with_text"] == 1


def test_review_queue_rates_imported_job(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    client.post(
        "/jobs",
        json={
            "job_id": "022065160614482733821",
            "job_file": "064038_022065160614482733821.html",
            "job_title": "Review queue automation job",
            "country": "United Kingdom",
            "job_html": "<article><p>Need n8n workflow support.</p></article>",
            "raw_payload": {
                "source_date": "20260612",
                "source_bucket": "prospects",
                "source_relative_path": "20260612/prospects/064038_022065160614482733821.html",
            },
        },
    )

    queue_response = client.get("/review/jobs")
    job = queue_response.json()["jobs"][0]
    rating_response = client.post(f"/review/jobs/{job['id']}/rating", json={"rating": 2})
    updated_queue_response = client.get("/review/jobs")
    rows = load_rating_rows(settings)

    assert queue_response.status_code == 200
    assert job["source_date"] == "20260612"
    assert job["source_bucket"] == "prospects"
    assert rating_response.status_code == 200
    assert rating_response.json()["rating_id"] == rows[0]["id"]
    assert updated_queue_response.json()["unrated_jobs"] == 0
    assert rows[0]["rating"] == 2
    assert rows[0]["job_text"] == "Need n8n workflow support."


def test_review_page_loads(tmp_path):
    settings = Settings(
        db_path=tmp_path / "ratings.db",
        model_path=tmp_path / "model.joblib",
    )
    client = TestClient(create_app(settings))

    response = client.get("/review")

    assert response.status_code == 200
    assert "Job Review" in response.text
