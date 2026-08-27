import json
import boto3
import os
import urllib.parse

sagemaker_runtime = boto3.client("sagemaker-runtime")
CONTENT_TYPE = os.environ.get("CONTENT_TYPE", "application/json")
ENDPOINT_NAME = "serving-echo-async"

def lambda_handler(event, context):
    
    for record in event['Records']:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        input_location = f"s3://{bucket}/{key}"
        
        response = sagemaker_runtime.invoke_endpoint_async(
            EndpointName=ENDPOINT_NAME,
            InputLocation=input_location,
            ContentType=CONTENT_TYPE,
            InvocationTimeoutSeconds=60,
        )

        print(f"Invoked async endpoint for {input_location}")
        print(f"OutputLocation: {response['OutputLocation']}")
        print(f"InferenceId: {response.get('InferenceId')}")

    return {'statusCode': 200}