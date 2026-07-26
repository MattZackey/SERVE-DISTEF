"""provision or teardown sagemaker async inference endpoint"""

import os
import argparse
import configparser
import logging
import boto3
from botocore.exceptions import ClientError, ParamValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_cfg = configparser.ConfigParser()
_cfg.read("config.ini")
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
        logger.info("created model %s", MODEL_NAME)

    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "already exists" in str(e):
            logger.warning("model %s already exists, skipping", MODEL_NAME)
        elif code == "ResourceNotFound":
            logger.error("role or ECR image not found: %s", e)
            raise
        else:
            logger.error("failed to create model: %s", e)
            raise

    except ParamValidationError as e:
        logger.error("bad parameters for create_model: %s", e)
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
        logger.info("created endpoint config %s", CONFIG_NAME)

    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "already exists" in str(e):
            logger.warning("endpoint config %s already exists, skipping", CONFIG_NAME)
        else:
            logger.error("failed to create endpoint config: %s", e)
            raise
    
def create_endpoint():
    
    try:
        sm.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=CONFIG_NAME)
        logger.info("creating endpoint %s ...", ENDPOINT)

    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "already exists" in str(e):
            logger.warning("endpoint %s already exists, skipping", ENDPOINT)
        else:
            logger.error("failed to create endpoint: %s", e)
            raise
        
def teardown():

    try:
        sm.delete_endpoint(EndpointName=ENDPOINT)
        logger.info("deleted endpoint %s", ENDPOINT)

    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "not find" in str(e):
            logger.warning("endpoint %s not found, skipping", ENDPOINT)
        else:
            logger.error("failed to delete endpoint: %s", e)
            raise

    try:
        sm.delete_endpoint_config(EndpointConfigName=CONFIG_NAME)
        logger.info("deleted endpoint config %s", CONFIG_NAME)

    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "not find" in str(e):
            logger.warning("endpoint config %s not found, skipping", CONFIG_NAME)
        else:
            logger.error("failed to delete endpoint config: %s", e)
            raise

    try:
        sm.delete_model(ModelName=MODEL_NAME)
        logger.info("deleted model %s", MODEL_NAME)

    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ValidationException" and "not find" in str(e):
            logger.warning("model %s not found, skipping", MODEL_NAME)
        else:
            logger.error("failed to delete model: %s", e)
            raise
 
if __name__ == '__main__':   
    
    parser = argparse.ArgumentParser(description='provision or teardown sagemaker async inference endpoint')
    
    parser.add_argument("--action", type = str, choices=["deploy", "teardown"], required=True)
    
    args = parser.parse_args()
    
    if args.action == "deploy":
    
        create_model()
        create_endpoint_config()
        create_endpoint()
    
        sm.get_waiter("endpoint_in_service").wait(EndpointName=ENDPOINT)
        logger.info("endpoint inservice")

    elif args.action == "teardown":
        teardown()

        logger.info("endpoint removed")