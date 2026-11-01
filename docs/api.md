# API reference

## API Gateway

**Base URL:** `https://<api-id>.execute-api.<region>.amazonaws.com/<stage>`.

**Authentication:** every route uses IAM auth. Requests must be signed with **SigV4**. Unsigned or wrongly signed requests are rejected by API Gateway with `403` before any Lambda runs.

All responses are JSON (`Content-Type: application/json`). Errors have the shape `{"error": "<message>"}`.

**Job lifecycle:** `POST /upload` → poll `GET /poll` until `status` is `success` or `failed` → `GET /fetch` for the result.

| Status | Meaning |
|---|---|
| `queued` | Job recorded in DynamoDB and sent to the SageMaker async endpoint |
| `success` | Prediction written to S3. Call `/fetch` |
| `failed` | Inference failed. `failure_reason` may be included |

## `POST /upload`

Upload one echo video. The request body is the **raw `.avi` file bytes**, not multipart form data or JSON.

**Headers**

| Header | Notes |
|---|---|
| `Content-Type` | Must be `video/x-msvideo`|

**`201 Created`**

```json
{
  "id": "3f2b8c1e-9d4a-4e7b-a1c2-5f6e7d8c9b0a"
}
```

## `GET /poll?job_id=<id>`

Return the current status of a job. Reads DynamoDB with strong consistency, so a status change is visible right away.

```json
{
  "job_id": "3f2b8c1e-9d4a-4e7b-a1c2-5f6e7d8c9b0a",
  "status": "queued",
  "created_at": "2026-11-01T07:45:08.574570+00:00"
}
```
or 
```json
{
  "job_id": "3f2b8c1e-9d4a-4e7b-a1c2-5f6e7d8c9b0a",
  "status": "success",
  "created_at": "2026-11-01T07:45:08.574570+00:00"
}
```
or 
```json
{
  "job_id": "3f2b8c1e-9d4a-4e7b-a1c2-5f6e7d8c9b0a",
  "status": "failed",
  "created_at": "2026-11-01T07:45:08.574570+00:00"
}
```

## `GET /fetch?job_id=<id>`

Return the prediction for a finished job.


```json
{
  "job_id": "3f2b8c1e-9d4a-4e7b-a1c2-5f6e7d8c9b0a",
  "status": "success",
  "ejection_fraction": 65.23590087890625,
  "quantiles": [58.1862678527832, 73.97683715820312]
}
```
`ejection_fraction` is the point estimate in percent. `quantiles` is the lower and upper bound of the 90% prediction interval.

Example of calling each endpoint can be found in [`examples/example_calls.ipynb`](../examples/example_calls.ipynb)
