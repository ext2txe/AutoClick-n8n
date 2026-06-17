# Store Captured Job Workflow

Purpose: submit the saved job HTML to the classifier service before the user rating arrives.

The classifier should learn from the full `job.html`, not only the short Telegram notification fields. The rating webhook can stay lightweight if each captured job is stored first.

## Trigger

Use either:

- an n8n `Webhook` called by AutoClick or the feed processor
- a filesystem/SSH/SFTP step that reads the saved job file
- a Google Drive step if the job HTML is uploaded there first

Suggested webhook:

- Method: `POST`
- Path: `autoclick/store-job`

Expected JSON body:

```json
{
  "job_id": "012345678901234",
  "job_file": "20260616103000_012345678901234.html",
  "job_title": "Build an n8n workflow",
  "job_url": "https://www.upwork.com/jobs/~012345678901234",
  "posted": "10 minutes ago",
  "country": "United Kingdom",
  "job_html": "<html>...</html>",
  "source": "autoclick"
}
```

## Store Job

Use an `HTTP Request` node.

- Method: `POST`
- URL: `http://172.17.0.1:8765/jobs` when n8n runs in Docker on the Linux host
- Body content type: JSON
- Body: webhook JSON body

The service stores both the raw HTML and normalized plain text. Later ratings can refer to the same `job_id` or `job_file`.

## Response

Return:

```json
{
  "ok": true,
  "message": "Job stored"
}
```

