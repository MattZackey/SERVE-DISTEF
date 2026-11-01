import os
import json
import base64
import logging
from decimal import Decimal

import boto3
import botocore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

table = boto3.resource("dynamodb").Table(TABLE_NAME)
s3 = boto3.client("s3")


def _json_default(value):
    """DynamoDB returns numbers as Decimal, which json.dumps can't handle on its own."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_response(status_code: int, body: dict) -> dict:
    """Format a response for API Gateway's Lambda proxy integration."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, default=_json_default),
    }


def get_job_id(event: dict) -> str | None:
    """Accept the ID as a path parameter (/fetch/{job_id}) or a query string (?job_id=...)."""
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    return path_params.get("job_id") or query_params.get("job_id")


def get_job(job_id: str) -> dict | None:
    """Read a job item from DynamoDB. Returns None if it doesn't exist."""
    try:
        result = table.get_item(Key={"job_id": job_id}, ConsistentRead=True)
    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        logger.exception("DynamoDB read failed (%s) table=%s job_id=%s", code, TABLE_NAME, job_id)
        raise
    return result.get("Item")


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split 's3://bucket/path/to/file.out' into ('bucket', 'path/to/file.out')."""
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    return bucket, key


def load_result(output_location: str) -> dict:
    """Read the SageMaker output from S3"""
    
    bucket, key = parse_s3_uri(output_location)

    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw = obj["Body"].read()
    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        logger.exception("S3 read failed (%s) location=%s", code, output_location)
        raise

    try:
        ef = json.loads(raw)["ejection_fraction"]
        return {
            "ejection_fraction": ef["ejection_fraction"],
            "quantiles": ef["quantiles"],
        }
    except (ValueError, KeyError, TypeError) as e:
        logger.exception("Unexpected output format at %s", output_location)
        raise ValueError(f"Unexpected output format at {output_location}") from e


def lambda_handler(event, context):
    job_id = get_job_id(event)
    if not job_id:
        return build_response(400, {"error": "job_id is required"})

    try:
        job = get_job(job_id)
    except botocore.exceptions.ClientError:
        return build_response(500, {"error": "Could not read job"})

    if job is None:
        return build_response(404, {"error": f"Job {job_id} not found"})

    status = job.get("status")

    if status == STATUS_FAILED:
        body = {"job_id": job_id, "status": status, "error": "Job failed, there is no result to fetch"}
        if job.get("failure_reason"):
            body["failure_reason"] = job["failure_reason"]
        return build_response(409, body)

    if status != STATUS_SUCCESS:
        return build_response(409, {
            "job_id": job_id,
            "status": status,
            "error": "Result not ready yet, keep polling",
        })

    output_location = job.get("output_location")
    if not output_location:
        logger.error("Job %s is marked %s but has no output_location", job_id, status)
        return build_response(500, {"error": "Result location missing for this job"})

    try:
        result = load_result(output_location)
    except botocore.exceptions.ClientError:
        return build_response(500, {"error": "Could not read result"})

    return build_response(200, {"job_id": job_id, "status": status, **result})
