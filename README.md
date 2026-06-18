# AutoClick n8n Job Rating Classifier

This project supplements `D:\src\AutoClick` with the rating and second-stage classifier workflow for job feed monitoring.

AutoClick already does the first pass:

1. Extract jobs from the feed.
2. Reject obvious keyword matches.
3. Notify for jobs that do not match rejection keywords.
4. Add Telegram rating buttons when `TelegramRatingWebhookUrl` is configured.

This project handles the next loop:

1. Receive a user rating from n8n.
2. Store the rating and attach it to the full saved job HTML/text.
3. Submit the rating to a classifier service.
4. Train when enough labelled jobs exist.
5. Expose a `/classify` endpoint for the feed processor to suppress low-interest jobs.

## Local Setup

Linux:

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install -e .[dev]
cp .env.example .env
./.venv/bin/autoclick-classifier --host 127.0.0.1 --port 8765
```

Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
Copy-Item .env.example .env
autoclick-classifier --host 127.0.0.1 --port 8765
```

The service stores data under `./data` by default.

## Linux systemd service

On the Linux host, start the 24/7 service with:

```bash
bash ./scripts/startup.sh
```

The startup script creates `.venv` if needed, installs the project, creates `.env` from `.env.example` if missing, registers `/etc/systemd/system/autoclick-classifier.service`, starts it immediately, and enables it for boot. The service uses `Restart=always`, so it keeps running after terminal logout and is restarted by `systemd` if the Python process exits.

To stop it:

```bash
bash ./scripts/shutdown.sh
```

Common commands:

```bash
sudo systemctl status autoclick-classifier
sudo journalctl -u autoclick-classifier -f
sudo systemctl restart autoclick-classifier
curl http://127.0.0.1:8765/health
```

Confirm the service is running 24/7:

```bash
systemctl is-active autoclick-classifier
systemctl is-enabled autoclick-classifier
curl http://127.0.0.1:8765/health
sudo systemctl cat autoclick-classifier
```

Expected checks:

```text
active
enabled
```

The unit definition should include `Restart=always` and `WantedBy=multi-user.target`.

Optional installer settings can be supplied as environment variables:

```bash
sudo env HOST=0.0.0.0 PORT=8765 SERVICE_USER=autoclick bash ./scripts/install-systemd-service.sh
```

To remove the service:

```bash
sudo bash ./scripts/uninstall-systemd-service.sh
```

## API Contract

### Store a rating

`POST /ratings`

```json
{
  "rating": 5,
  "job_id": "012345678901234",
  "job_file": "20260616103000_012345678901234.html",
  "job_title": "Build an n8n workflow",
  "job_url": "https://www.upwork.com/jobs/~012345678901234",
  "posted": "10 minutes ago",
  "country": "United Kingdom",
  "job_html": "<article>...</article>",
  "job_text": "Optional pre-extracted plain text from the job HTML.",
  "source": "telegram",
  "raw_payload": {
    "rating": "5",
    "job_file": "20260616103000_012345678901234.html"
  }
}
```

The endpoint also accepts query-string webhook payloads from n8n. Unknown fields are retained in `raw_payload`.

If `job_html` or `job_text` is omitted, the service looks for a previously stored job with the same `job_id` or `job_file` and trains from that stored content.

### Store a captured job

`POST /jobs`

Use this when the feed processor captures a job, before or around the time it sends the notification. This is the preferred path because the classifier should learn from the full saved `job.html`, not just the short Telegram notification fields.

```json
{
  "job_id": "012345678901234",
  "job_file": "20260616103000_012345678901234.html",
  "job_title": "Build an n8n workflow",
  "job_url": "https://www.upwork.com/jobs/~012345678901234",
  "posted": "10 minutes ago",
  "country": "United Kingdom",
  "job_html": "<html>...</html>",
  "source": "autoclick",
  "raw_payload": {
    "job_id": "012345678901234",
    "job_file": "20260616103000_012345678901234.html"
  }
}
```

The service extracts normalized plain text from `job_html` and stores it as `job_text`. A later `/ratings` call can be tiny:

```json
{
  "rating": 5,
  "job_id": "012345678901234",
  "source": "telegram"
}
```

### Train the classifier

`POST /train`

Training is skipped until there are at least `AUTOCLICK_CLASSIFIER_MIN_SAMPLES` ratings and at least one low-interest and one interested example.

Ratings greater than or equal to `AUTOCLICK_CLASSIFIER_INTERESTED_RATING` are treated as interested. The default is `4`.

### Classify a job

`POST /classify`

```json
{
  "job_id": "012345678901234",
  "title": "Build an n8n workflow",
  "description": "Need help wiring Telegram webhooks into n8n...",
  "job_text": "Optional extracted plain text from the saved job HTML.",
  "html": "<html>Optional saved job HTML.</html>",
  "country": "United Kingdom",
  "url": "https://www.upwork.com/jobs/~012345678901234"
}
```

Response:

```json
{
  "model_available": true,
  "interested_probability": 0.82,
  "should_notify": true,
  "threshold": 0.55,
  "reason": "classified"
}
```

## n8n Workflows

Workflow blueprints live in `workflows/`:

- `rating-webhook.blueprint.md`
- `classifier-training.blueprint.md`
- `classify-job.blueprint.md`

Configure AutoClick with the production n8n rating webhook URL:

```text
TelegramRatingButtonsEnabled=1
TelegramRatingWebhookUrl=https://<n8n-host>/webhook/autoclick/job-rating
```

The webhook should forward the collected payload to:

```text
http://127.0.0.1:8765/ratings
```

Then call:

```text
http://127.0.0.1:8765/train
```

For the HTML-aware classifier, add a feed-side workflow or processor call that sends every captured prospect to:

```text
http://127.0.0.1:8765/jobs
```

with the saved `job_html`. The rating webhook can then submit just the user rating and job id.

## Confidence Gate

Use `/metrics` to decide when the model is ready to join the feed processor:

- `model_available` must be `true`
- `sample_count` should be comfortably above the minimum
- both classes must have enough examples
- test classifications should agree with your judgement before enabling suppression

Use the payload coverage fields in `/metrics` to confirm n8n is sending the expected data:

```bash
curl -s http://127.0.0.1:8765/metrics | python3 -m json.tool
```

Check:

- `payload_stats.ratings.with_raw_payload` increases after rating clicks
- `payload_stats.jobs.with_html` and `payload_stats.jobs.with_text` increase after captured jobs are stored
- `payload_stats.ratings.with_text` increases when ratings are attached to stored job HTML/text
- `model_training_data_stats` is populated after the next `/train` call and shows the coverage used by the saved model
