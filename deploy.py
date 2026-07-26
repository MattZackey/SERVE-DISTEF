"""Provision and invoke a SageMaker Async Inference endpoint"""

import os
import time
import configparser
import boto3
import datetime

_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(os.path.dirname(__file__), "config.ini"))
aws_cfg = _cfg["aws"]

REGION      = aws_cfg["region"]
ACCOUNT_ID  = aws_cfg["account_id"]
BUCKET      = aws_cfg["bucket"]
ECR_IMAGE   = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/{aws_cfg['ecr_repo']}"
MODEL_PREFIX = aws_cfg["model_data_prefix"].rstrip("/") + "/"
MODEL_DATA   = f"s3://{BUCKET}/{MODEL_PREFIX}"
ROLE_ARN    = f"arn:aws:iam::{ACCOUNT_ID}:role/{aws_cfg['role_name']}"
MODEL_NAME  = aws_cfg["model_name"]
CONFIG_NAME = aws_cfg["config_name"]
MAX_CONURRENT = aws_cfg["max_concurrent"]
ENDPOINT    = aws_cfg["endpoint"]
INSTANCE    = aws_cfg["instance"]
ENABLE_SNS  = aws_cfg.getboolean("enable_sns", fallback=True)

sm      = boto3.client("sagemaker", region_name=REGION)
sns     = boto3.client("sns", region_name=REGION)
s3      = boto3.client("s3", region_name=REGION)
runtime = boto3.client("sagemaker-runtime", region_name=REGION)


# def create_topics():
#     success = sns.create_topic(Name="echo-async-success")["TopicArn"]
#     error = sns.create_topic(Name="echo-async-error")["TopicArn"]
#     print("success topic:", success)
#     print("error topic:  ", error)
#     return success, error


def create_model():
    sm.create_model(
        ModelName=MODEL_NAME,
        ExecutionRoleArn=ROLE_ARN,
        PrimaryContainer={
            "Image": ECR_IMAGE,
            "ModelDataSource": {
                "S3DataSource": {
                    "S3Uri": MODEL_DATA,
                    "S3DataType": "S3Prefix",
                    "CompressionType": "None",
                },
            },
            "Environment": {"MODEL_DIR": "/opt/ml/model"},
        },
    )
    print("created model", MODEL_NAME)


def create_endpoint_config(success_arn=None, error_arn=None):
    output_config = {
        "S3OutputPath": f"s3://{BUCKET}/echo-serve/preds-success/",
        "S3FailurePath": f"s3://{BUCKET}/echo-serve/preds-fail/",
    }
    
    # if ENABLE_SNS:
    #     output_config["NotificationConfig"] = {
    #         "SuccessTopic": success_arn,
    #         "ErrorTopic": error_arn,
    #     }
    
    sm.create_endpoint_config(
        EndpointConfigName=CONFIG_NAME,
        ProductionVariants=[{
            "VariantName": "AllTraffic",
            "ModelName": MODEL_NAME,
            "InstanceType": INSTANCE,
            "InitialInstanceCount": 1,
        }],
        AsyncInferenceConfig={
            "OutputConfig": output_config,
            "ClientConfig": {"MaxConcurrentInvocationsPerInstance": MAX_CONURRENT},
        },
    )
    print("created endpoint config", CONFIG_NAME)


def create_endpoint():
    sm.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=CONFIG_NAME)
    print("creating endpoint", ENDPOINT, "...")
    sm.get_waiter("endpoint_in_service").wait(EndpointName=ENDPOINT)
    print("endpoint InService")


# def provision():
#     if ENABLE_SNS:
#         success, error = create_topics()
#     else:
#         success, error = None, None
#         print("SNS disabled; skipping topic creation")
#     create_model()
#     create_endpoint_config(success, error)
#     create_endpoint()

datetime.datetime()

import uuid
from datetime import datetime, timezone

def make_key(ext=".avi"):
    now = datetime.now(timezone.utc)
    return f"echo-serve/input/{now:%Y/%m/%d}/{uuid.uuid4()}{ext}"

make_key()

def invoke(video_path="test/0X1A0A263B22CCD966.avi"):
    key = make_key()
    s3.upload_file(video_path, BUCKET, key)
    resp = runtime.invoke_endpoint_async(
        EndpointName=ENDPOINT,
        InputLocation=f"s3://{BUCKET}/{key}",
        ContentType="application/octet-stream",
    )
    out = resp["OutputLocation"]
    print("output will appear at:", out)
    return out


# def fetch_result(output_location, attempts=60, delay=5):
#     """Poll the async OutputLocation in S3 until the result JSON is written."""
#     assert output_location.startswith("s3://")
#     bucket, key = output_location[5:].split("/", 1)
#     for _ in range(attempts):
#         try:
#             return s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
#         except s3.exceptions.NoSuchKey:
#             time.sleep(delay)
#     raise TimeoutError("result not ready")


# def teardown():
#     sm.delete_endpoint(EndpointName=ENDPOINT)
#     sm.delete_endpoint_config(EndpointConfigName=CONFIG_NAME)
#     sm.delete_model(ModelName=MODEL_NAME)


# if __name__ == "__main__":
#     provision()
#     location = invoke()
#     print(fetch_result(location))
