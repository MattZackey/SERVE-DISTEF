"""provision or teardown sagemaker async inference endpoint"""

import os
import argparse
import configparser
import boto3
from botocore.exceptions import ClientError, ParamValidationError

_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(os.path.dirname(__file__), "config.ini"))
aws_cfg = _cfg["aws"]

REGION       = aws_cfg["region"]
ACCOUNT_ID   = aws_cfg["account_id"]
BUCKET       = aws_cfg["bucket"]
ECR_IMAGE    = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/{aws_cfg['ecr_repo']}"
MODEL_PREFIX = aws_cfg["model_data_prefix"].rstrip("/") + "/"
MODEL_DATA   = f"s3://{BUCKET}/{MODEL_PREFIX}"
ROLE_ARN     = aws_cfg["role_name"]
MODEL_NAME   = aws_cfg["model_name"]
CONFIG_NAME  = aws_cfg["config_name"]
MAX_CONCURRENT = aws_cfg.getint("max_concurrent")
ENDPOINT     = aws_cfg["endpoint"]
INSTANCE     = aws_cfg["instance"]

sm      = boto3.client("sagemaker", region_name=REGION)
# sns     = boto3.client("sns", region_name=REGION)
s3      = boto3.client("s3", region_name=REGION)
runtime = boto3.client("sagemaker-runtime", region_name=REGION)

def create_model():
    
    try:
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
        
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "already exists" in str(e):
            print(f"model {MODEL_NAME} already exists, skipping")
        elif code == "ResourceNotFound":
            print(f"role or ECR image not found: {e}")
            raise
        else:
            print(f"failed to create model: {e}")
            raise
        
    except ParamValidationError as e:
        print(f"bad parameters for create_model: {e}")
        raise
    

def create_endpoint_config():
    output_config = {
        "S3OutputPath": f"s3://{BUCKET}/echo-serve/preds-success/",
        "S3FailurePath": f"s3://{BUCKET}/echo-serve/preds-fail/",
    }
    # if ENABLE_SNS:
    #     output_config["NotificationConfig"] = {
    #         "SuccessTopic": success_arn,
    #         "ErrorTopic": error_arn,
    #     }
    
    try:
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
                "ClientConfig": {"MaxConcurrentInvocationsPerInstance": MAX_CONCURRENT},
            },
        )
        print("created endpoint config", CONFIG_NAME)
        
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "already exists" in str(e):
            print(f"endpoint config {CONFIG_NAME} already exists, skipping")
        else:
            print(f"failed to create endpoint config: {e}")
            raise
    
def create_endpoint():
    
    try:
        sm.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=CONFIG_NAME)
        print("creating endpoint", ENDPOINT, "...")
        
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "already exists" in str(e):
            print(f"endpoint {ENDPOINT} already exists, skipping")
        else:
            print(f"failed to create endpoint: {e}")
            raise
        
def teardown():
    sm.delete_endpoint(EndpointName=ENDPOINT)
    sm.delete_endpoint_config(EndpointConfigName=CONFIG_NAME)
    sm.delete_model(ModelName=MODEL_NAME)
 
if __name__ == '__main__':   
    
    parser = argparse.ArgumentParser(description='provision or teardown sagemaker async inference endpoint')
    
    parser.add_argument("--action", type = str, choices=["deploy", "teardown"], required=True)
    
    args = parser.parse_args()
    
    if args.action == "deploy":
    
        create_model()
        create_endpoint_config()
        create_endpoint()
    
        sm.get_waiter("endpoint_in_service").wait(EndpointName=ENDPOINT)
        print("endpoint InService")
    
    elif args.action == "teardown":
        teardown()