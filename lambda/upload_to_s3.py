import base64
import json
import os
import uuid
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

BUCKET = os.environ["BUCKET_NAME"]
FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads").strip("/")

AVI_CONTENT_TYPE = "video/x-msvideo"


def lambda_handler(event, context):
    body = event.get("body")
    if not body:
        return _response(400, {"error": "Request body is empty"})

    if not event.get("isBase64Encoded"):
        # Binary uploads must arrive base64-encoded; plain text means Binary Media Types
        # isn't configured on the API, and the file would be corrupted.
        return _response(400, {"error": "Expected binary body; check API Gateway binary media types"})

    data = base64.b64decode(body)

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    content_type = headers.get("content-type", "").split(";")[0].strip().lower()
    original_name = headers.get("x-file-name", "")

    if original_name and not original_name.lower().endswith(".avi"):
        return _response(415, {"error": "Only .avi files are allowed"})

    if content_type != AVI_CONTENT_TYPE:
        return _response(415, {"error": f"Content-Type must be {AVI_CONTENT_TYPE}"})

    if not _is_avi(data):
        return _response(415, {"error": "File is not a valid AVI video"})

    file_id = str(uuid.uuid4())
    key = f"{FOLDER}/{file_id}.avi"

    # Record who uploaded it (IAM auth puts the verified caller here)
    identity = (event.get("requestContext") or {}).get("identity") or {}
    uploaded_by = identity.get("userArn") or identity.get("user") or "unknown"

    try:
        s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=data,
            ContentType=AVI_CONTENT_TYPE,
            Metadata={
                "original-name": quote(original_name),  # S3 metadata must be ASCII
                "uploaded-by": quote(uploaded_by),
            },
        )
    except ClientError as e:
        print(f"S3 upload failed for {key}: {e}")
        return _response(500, {"error": "Upload failed"})

    return _response(201, {
        "id": file_id,
        "bucket": BUCKET,
        "key": key,
        "size": len(data),
    })


def _is_avi(data):
    """AVI files are RIFF containers: bytes 0-3 are 'RIFF', bytes 8-11 are 'AVI '."""
    return len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"AVI "


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }