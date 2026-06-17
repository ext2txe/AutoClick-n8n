# Classifier Training Workflow

Purpose: retrain the classifier on a schedule after ratings have accumulated.

## Trigger

Use an n8n `Schedule Trigger` node.

Suggested cadence:

- every 6 hours while collecting early labels
- daily once the model is stable

## Train

Use an `HTTP Request` node.

- Method: `POST`
- URL: `http://127.0.0.1:8765/train`

## Inspect Metrics

Use an `HTTP Request` node.

- Method: `GET`
- URL: `http://127.0.0.1:8765/metrics`

## Notification

Optionally notify yourself when:

- `trained` changes to `true`
- `sample_count` crosses a confidence milestone
- `accuracy` is present and drops below an acceptable threshold

