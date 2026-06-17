# Rating Webhook Workflow

Purpose: receive Telegram rating button clicks from AutoClick notifications and store them in the classifier service.

## Trigger

Use an n8n `Webhook` node.

- Method: `GET`
- Path: `autoclick/job-rating`
- Response mode: respond immediately

Expected query parameters from AutoClick:

- `rating`
- `job_file`
- `job_id`
- `job_title`
- `job_url`
- `posted`
- `country`

The current AutoClick code can send either a compact payload (`rating`, `job_file`, `job_id`) or the richer notification payload (`rating`, `job_file`, `job_title`, `job_url`, `posted`, `country`). The classifier accepts both.

For best classification, store the full job HTML first with the `store-captured-job` workflow. Then this rating workflow only needs `rating` plus `job_id` or `job_file`; the classifier will attach the rating to the stored HTML/text.

## Transform

Use a `Set` or `Code` node to produce:

```json
{
  "rating": "={{ Number($json.query.rating) }}",
  "job_id": "={{ $json.query.job_id || '' }}",
  "job_file": "={{ $json.query.job_file || '' }}",
  "job_title": "={{ $json.query.job_title || '' }}",
  "job_url": "={{ $json.query.job_url || '' }}",
  "posted": "={{ $json.query.posted || '' }}",
  "country": "={{ $json.query.country || '' }}",
  "source": "telegram",
  "raw_payload": "={{ $json.query }}"
}
```

## Store Rating

Use an `HTTP Request` node.

- Method: `POST`
- URL: `http://127.0.0.1:8765/ratings`
- Body content type: JSON
- Body: transformed payload

## Optional Immediate Training

Add a second `HTTP Request` node.

- Method: `POST`
- URL: `http://127.0.0.1:8765/train`

This endpoint safely returns `trained: false` until enough samples exist.

## Response

Use `Respond to Webhook`.

```json
{
  "ok": true,
  "message": "Rating stored. Thanks."
}
```
