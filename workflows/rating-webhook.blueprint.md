# Rating Webhook Workflow

Purpose: receive Telegram rating button clicks from AutoClick notifications and store them in the classifier service.

## Trigger

Use an n8n `Webhook` node.

- Method: `GET`
- Path: `autoclick/job-rating`
- Response mode: using `Respond to Webhook` node

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

Keep `raw_payload` enabled. It is not used as a model feature, but it is useful for audit/debugging and for confirming that n8n is forwarding the original rating-click query into the classifier database.

## Store Rating

Use an `HTTP Request` node.

- Method: `POST`
- URL: `http://172.18.0.1:8765/ratings` when n8n runs in Docker on the Linux host
- Body content type: JSON
- Body: transformed payload

## Optional Immediate Training

Add a second `HTTP Request` node.

- Method: `POST`
- URL: `http://172.18.0.1:8765/train` when n8n runs in Docker on the Linux host

This endpoint safely returns `trained: false` until enough samples exist.

## Response

Use `Respond to Webhook` after the Store Rating node, or after Optional Immediate Training if training is enabled.

The response mode setting is on the `Webhook` trigger node, not on the `Respond to Webhook` node. Open the first `Webhook` node and set its `Respond` parameter to `Using Respond to Webhook Node`.

- Respond with: Text
- Response code: `200`
- Header name: `Content-Type`
- Header value: `text/html; charset=utf-8`
- Response body:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Rating stored</title>
  <style>
    body {
      margin: 2rem;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <h1>Rating stored</h1>
  <p>Thanks. You can close this tab.</p>
</body>
</html>
```

Do not use `respond immediately` for this workflow. It can make the click open a sparse or blank browser page before the visible confirmation body is generated.

## Troubleshooting the response

After changing the workflow, save and activate the production workflow before testing `/webhook/...`.

Check the production URL with:

```bash
curl -i "https://<n8n-host>/webhook/autoclick/job-rating?rating=5&job_file=test.html"
```

Expected response headers:

```text
HTTP/2 200
content-type: text/html; charset=utf-8
```

Expected response body includes:

```html
<h1>Rating stored</h1>
```

If curl returns `content-type: application/json` with `content-length: 0`, the production workflow is not returning the HTML confirmation. Check these n8n settings:

- The `Webhook` node's `Respond` / `Response Mode` setting is `Using 'Respond to Webhook' Node`.
- The `Respond to Webhook` node is connected on the executed path after `Store Rating` or after `Optional Immediate Training`.
- The `Respond to Webhook` node's `Respond With` setting is `Text`, not `JSON` or `No Data`.
- The HTML confirmation is in the `Response Body`.
- The `Respond to Webhook` node has one response header named `Content-Type` with value `text/html; charset=utf-8`; do not add `charset` as a separate header.
- `No Response Body` is off.
- The workflow was saved and activated after the changes.
