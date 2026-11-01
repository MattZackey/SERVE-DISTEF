import os
import json
import logging
from decimal import Decimal
import boto3
import botocore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]

STATUS_QUEUED = "queued"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

table = boto3.resource("dynamodb").Table(TABLE_NAME)


def _json_default(value):
    """DynamoDB returns numbers as Decimal, which json.dumps can't handle on its own."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_response(status_code: int, body: dict) -> dict:
    """Format a response for API Gateway's Lambda proxy integration."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


def get_job_id(event: dict) -> str | None:
    """Accept the ID as a path parameter (/poll/{job_id}) or a query string (?job_id=...)."""
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    return path_params.get("job_id") or query_params.get("job_id")


def get_job(job_id: str) -> dict | None:
    """Read a job item from DynamoDB. Returns None if it doesn't exist."""
    try:
        result = table.get_item(
            Key={"job_id": job_id},
            ConsistentRead=True,   # so a status update is visible immediately
        )
    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        logger.exception("DynamoDB read failed (%s) table=%s job_id=%s", code, TABLE_NAME, job_id)
        raise
    return result.get("Item")


def lambda_handler(event, context):
    job_id = get_job_id(event)
    if not job_id:
        return build_response(400, {"error": "job_id is required"})

    try:
        job = get_job(job_id)
    except botocore.exceptions.ClientError:
        return build_response(500, {"error": "Could not read job status"})

    if job is None:
        return build_response(404, {"error": f"Job {job_id} not found"})

    status = job.get("status")
    body = {
        "job_id": job_id,
        "status": status,
        "created_at": job.get("created_at"),
    }

    if status == STATUS_FAILED and job.get("failure_reason"):
        body["failure_reason"] = job["failure_reason"]

    return build_response(200, body)
