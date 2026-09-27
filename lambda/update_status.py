import json
import logging
import os
import boto3

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

TableName = os.environ["TABLE_NAME"]
table = boto3.resource("dynamodb").Table(TableName)

def lambda_handler(event, context):
    
    for record in event["Records"]:
        msg = json.loads(record["Sns"]["Message"])
        job_id = msg["inferenceId"]
        pred_status = msg["invocationStatus"]
        processed_at = msg["eventTime"]
        if pred_status == "Completed":
            status = "success"
            output_location = msg["responseParameters"]["outputLocation"]
        else:
            status = "failed"
            output_location = ""

        logger.debug(f"job_id: {job_id}")
        logger.debug(f"status: {status}")
        logger.debug(f"processed: {processed_at}")

        update_item_by_id(job_id, status, processed_at, output_location)

    return {
        'statusCode': 200
    }

def update_item_by_id(job_id, status, processed_at, output_location):
        
    response = table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :status, processed_at = :processed_at, output_location = :output_location",
        ExpressionAttributeNames={"#s": "status"}, 
        ExpressionAttributeValues={
            ":status": status,
            ":processed_at": processed_at,
            ":output_location": output_location
        },
        ReturnValues="ALL_NEW",
    )