import os
import logging
from datetime import datetime, timezone
from urllib.parse import unquote_plus
import boto3
import botocore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
ENDPOINT_NAME = os.environ["ENDPOINT_NAME"]
CONTENT_TYPE = os.environ.get("CONTENT_TYPE", "application/json")

table = boto3.resource("dynamodb").Table(TABLE_NAME)
sagemaker_runtime = boto3.client("sagemaker-runtime")


def create_job_record(job_id: str, user_id: str) -> dict:
    """Write a new 'queued' job item to DynamoDB and return the item."""
    now = datetime.now(timezone.utc)
    item = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "queued",
        "created_at": now.isoformat(),
        "created_at_epoch": int(now.timestamp()),
        "expires_at": int(now.timestamp()) + (30 * 24 * 3600),
    }

    try:
        table.put_item(Item=item)
    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        logger.exception("DynamoDB write failed (%s) table=%s item=%s", code, TABLE_NAME, item)
        raise

    return item


def start_inference(job_id: str, bucket: str, key: str) -> dict:
    """Invoke the SageMaker async endpoint on the uploaded S3 object, using job_id as the InferenceId."""
    input_location = f"s3://{bucket}/{key}"

    try:
        response = sagemaker_runtime.invoke_endpoint_async(
            EndpointName=ENDPOINT_NAME,
            InputLocation=input_location,
            ContentType=CONTENT_TYPE,
            InferenceId=job_id, 
            InvocationTimeoutSeconds=60,
        )
    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        logger.exception(
            "SageMaker async invoke failed (%s) endpoint=%s job_id=%s input=%s",
            code, ENDPOINT_NAME, job_id, input_location,
        )
        raise

    logger.info("Invoked async endpoint for %s", input_location)
    logger.info("OutputLocation: %s", response["OutputLocation"])
    logger.info("InferenceId: %s", response.get("InferenceId"))

    return response


def lambda_handler(event, context):
    records = event.get("Records", [])
    failures = []

    for record in records:
        bucket = record["s3"]["bucket"]["name"]
        s3_key = unquote_plus(record["s3"]["object"]["key"])
        file_name = os.path.basename(s3_key)      # drop any folder prefix
        job_id = os.path.splitext(file_name)[0]   # drop .avi
        user_id = "1"

        try:
            create_job_record(job_id, user_id)    # if this fails, inference is skipped for this file
            start_inference(job_id, bucket, s3_key)
        except botocore.exceptions.ClientError:
            failures.append(job_id)               # already logged inside the failing function
            continue

    if failures:
        # Fail the invocation so Lambda's async retries kick in
        raise RuntimeError(f"Failed to process jobs: {failures}")

    return {"statusCode": 200, "processed": len(records)}