# Known limitations

## `/poll` returns 404 straight after upload

### What happens

`POST /upload` returns the job ID as soon as the video is saved to S3. The DynamoDB job record is written later, by `RecordPredictVideo`, when the S3 event triggers it. If the client calls `GET /poll` in that gap, `PollPredict` finds no item and returns `404 Job <id> not found`. A few seconds later the same call returns `200` with `status = queued`.

The client cannot tell this short-lived 404 apart from a job ID that doesn't exist.

### Why it matters

- Clients have to treat an early 404 as "not ready yet" and retry. That hides real errors, such as a mistyped job ID.
- If `RecordPredictVideo` fails (DynamoDB error, endpoint invoke error, or the S3 event retries running out), the record is never written. The job then returns 404 forever, with no `failed` status to explain why.

### Fix

1. **Write the job record in `UploadVideo`** *(preferred)*. Put the DynamoDB item (`status = queued`) before returning `201`, and have `RecordPredictVideo` update it instead of creating it. This closes the gap completely, and a failed invoke can set `status = failed`. It needs `TABLE_NAME` on `UploadVideo` and a DynamoDB write permission in its IAM policy.

## Autoscaling alarm name is shared across endpoints

### What happens

`infra/deploy_endpoint.py` creates the scale-from-zero CloudWatch alarm with the fixed name `HasBacklogWithoutCapacity-Alarm` (`ALARM_NAME`). CloudWatch alarm names must be unique within an account and region. The scaling policy names don't have this problem, because they only need to be unique within a single endpoint variant.

### Why it matters

This is harmless while there is one endpoint. If a second endpoint is deployed in the same account and region:

- Deploying it overwrites the first endpoint's alarm, so the alarm now watches only the new endpoint. The first endpoint can no longer scale up from zero instances.
- Tearing down either endpoint deletes the shared alarm, which breaks scale-from-zero for the endpoint still running.

### Fix

1. **Add the endpoint name to the alarm name.** For example, `ALARM_NAME = f"{ENDPOINT}-HasBacklogWithoutCapacity-Alarm"`. Before switching, tear down the existing autoscaling setup (or delete the old alarm by hand), because teardown will look for the new name and leave the old alarm behind.
