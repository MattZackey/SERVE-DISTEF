import os
import json
import uuid
import boto3
import botocore.exceptions
import logging
import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    
    TableName = os.environ["TABLE_NAME"]
    table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    now = datetime.now(timezone.utc)
    user_id = event.get("user_id")

    item = {
        "job_id": str(uuid.uuid4()),
        "user_id": user_id,
        "status": "queued",
        "created_at": now.isoformat(),
        "created_at_epoch": int(now.timestamp()),
        "expires_at": int(now.timestamp()) + (30 * 24 * 3600),
    }

    try:
        response = table.put_item(Item=item)
        return {"statusCode": 200}
    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        logger.exception("DynamoDB write failed (%s) table=%s item=%s", code, TableName, item)
        raise