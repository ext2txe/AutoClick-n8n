# Classify Job Workflow

Purpose: provide a callable classification step for AutoClick or another feed processor.

## Trigger

Use an n8n `Webhook` node.

- Method: `POST`
- Path: `autoclick/classify-job`
- Response mode: use `Respond to Webhook`

Expected JSON body:

```json
{
  "job_id": "012345678901234",
  "title": "Build an n8n workflow",
  "description": "Need help wiring Telegram webhooks into n8n...",
  "country": "United Kingdom",
  "url": "https://www.upwork.com/jobs/~012345678901234"
}
```

## Classify

Use an `HTTP Request` node.

- Method: `POST`
- URL: `http://127.0.0.1:8765/classify`
- Body content type: JSON
- Body: webhook JSON body

## Response

Return the classifier response directly:

```json
{
  "model_available": true,
  "interested_probability": 0.82,
  "should_notify": true,
  "threshold": 0.55,
  "reason": "classified"
}
```

When `model_available` is `false`, the service returns `should_notify: true` so the existing notification behavior remains unchanged until training is ready.

