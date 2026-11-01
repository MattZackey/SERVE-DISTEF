"""provision or teardown sagemaker async inference endpoint"""

import argparse
import configparser
import logging
import boto3
from botocore.exceptions import ClientError, ParamValidationError, WaiterError
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Load in config from infra/, wherever the script is run from
CONFIG_PATH = Path(__file__).resolve().parent / "config.ini"
_cfg = configparser.ConfigParser()
if not _cfg.read(CONFIG_PATH):
    raise SystemExit(f"could not read config file at {CONFIG_PATH}")
try:
    aws_cfg = _cfg["aws"]
    scaling_cfg = _cfg["autoscaling"]
except KeyError as e:
    raise SystemExit(f"no {e} section in {CONFIG_PATH}")

try:
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
    VARIANT_NAME = aws_cfg["variant_name"]
    ENABLE_SNS = aws_cfg.getboolean("enable_sns")
except KeyError as e:
    raise SystemExit(f"missing key {e} in aws section")
except ValueError as e:
    raise SystemExit(f"bad value in aws section {e}")

SCALING_KEYS = [
    "min_capacity",
    "max_capacity",
    "target_backlog_per_instance",
    "scale_in_cooldown",
    "scale_out_cooldown",
    "step_cooldown",
    "alarm_evaluation_periods",
    "alarm_datapoints_to_alarm",
    "alarm_threshold",
    "alarm_period",
]
missing = [key for key in SCALING_KEYS if key not in scaling_cfg]
if missing:
    raise SystemExit(f"missing in autoscaling section: {', '.join(missing)}")

try:
    MIN_CAPACITY = scaling_cfg.getint("min_capacity")
    MAX_CAPACITY = scaling_cfg.getint("max_capacity")
    TARGET_BACKLOG = scaling_cfg.getfloat("target_backlog_per_instance")
    SCALE_IN_COOLDOWN = scaling_cfg.getint("scale_in_cooldown")
    SCALE_OUT_COOLDOWN = scaling_cfg.getint("scale_out_cooldown")
    STEP_COOLDOWN = scaling_cfg.getint("step_cooldown")
    ALARM_EVAL_PERIODS = scaling_cfg.getint("alarm_evaluation_periods")
    ALARM_DATAPOINTS = scaling_cfg.getint("alarm_datapoints_to_alarm")
    ALARM_THRESHOLD = scaling_cfg.getfloat("alarm_threshold")
    ALARM_PERIOD = scaling_cfg.getint("alarm_period")
except ValueError as e:
    raise SystemExit(f"bad value in autoscaling section {e}")

sm = boto3.client("sagemaker", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
runtime = boto3.client("sagemaker-runtime", region_name=REGION)
client = boto3.client("application-autoscaling", region_name = REGION)
cw_client = boto3.client("cloudwatch", region_name = REGION)
resource_id = ("endpoint/" + ENDPOINT + "/variant/" + VARIANT_NAME)


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
    
    if ENABLE_SNS:
        output_config["NotificationConfig"] = {
            "SuccessTopic": f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:EchoPredSuccess",
            "ErrorTopic": f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:EchoPredFail",
        }
    
    try:
        sm.create_endpoint_config(
            EndpointConfigName=CONFIG_NAME,
            ProductionVariants=[{
                "VariantName": VARIANT_NAME,
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
        sm.get_waiter("endpoint_deleted").wait(
            EndpointName=ENDPOINT,
            WaiterConfig={"Delay": 15, "MaxAttempts": 40},   # ~10 min
        )
        logger.info("endpoint %s fully deleted", ENDPOINT)
    except WaiterError as e:
        logger.error("timed out waiting for endpoint %s to delete: %s", ENDPOINT, e)
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
 

def add_scaling(): 
    
    try:
        # Configure Autoscaling on asynchronous endpoint
        client.register_scalable_target(
            ServiceNamespace = "sagemaker",
            ResourceId = resource_id,
            ScalableDimension = "sagemaker:variant:DesiredInstanceCount",
            MinCapacity = MIN_CAPACITY,
            MaxCapacity = MAX_CAPACITY,
        )

        # Track queued requests per instance while at least one instance is running
        client.put_scaling_policy(
            PolicyName = "Invocations-ScalingPolicy",
            ServiceNamespace = "sagemaker",
            ResourceId = resource_id,
            ScalableDimension = "sagemaker:variant:DesiredInstanceCount",
            PolicyType = "TargetTrackingScaling",
            TargetTrackingScalingPolicyConfiguration = {
                "TargetValue": TARGET_BACKLOG,
                "CustomizedMetricSpecification": {
                    "MetricName": "ApproximateBacklogSizePerInstance",
                    "Namespace": "AWS/SageMaker",
                    "Dimensions": [{"Name": "EndpointName", "Value": ENDPOINT}],
                    "Statistic": "Average",
                },
                "ScaleInCooldown": SCALE_IN_COOLDOWN,
                "ScaleOutCooldown": SCALE_OUT_COOLDOWN,
            },
        )

        # Scale instances back up from zero
        response = client.put_scaling_policy(
            PolicyName = "HasBacklogWithoutCapacity-ScalingPolicy",
            ServiceNamespace = "sagemaker",
            ResourceId = resource_id,
            ScalableDimension = "sagemaker:variant:DesiredInstanceCount",
            PolicyType = "StepScaling",
            StepScalingPolicyConfiguration = {
                "AdjustmentType": "ChangeInCapacity",
                "MetricAggregationType": "Average",
                "Cooldown": STEP_COOLDOWN,
                "StepAdjustments": [
                    {"MetricIntervalLowerBound": 0, "ScalingAdjustment": 1},
                ],
            },
        )
        step_scaling_policy_arn = response["PolicyARN"]

        # Add metric to cloud watch
        cw_client.put_metric_alarm(
            AlarmName = "HasBacklogWithoutCapacity-Alarm",
            MetricName = "HasBacklogWithoutCapacity",
            Namespace = "AWS/SageMaker",
            Statistic = "Average",
            EvaluationPeriods = ALARM_EVAL_PERIODS,
            DatapointsToAlarm = ALARM_DATAPOINTS,
            Threshold = ALARM_THRESHOLD,
            ComparisonOperator = "GreaterThanOrEqualToThreshold",
            TreatMissingData = "missing",
            Dimensions = [{"Name": "EndpointName", "Value": ENDPOINT}],
            Period = ALARM_PERIOD,
            AlarmActions = [step_scaling_policy_arn],
        )
    
    except client.exceptions.ObjectNotFoundException:
        logger.error(f"Resource not found — does the endpoint/variant {resource_id} exist?")
        raise
    
    except ClientError as e:
        logger.error(f"Failed to configure autoscaling: {e}")
        raise

    
def delete_scaling():
    
    # Delete step-scaling policy
    try:
        client.delete_scaling_policy(
            PolicyName = "HasBacklogWithoutCapacity-ScalingPolicy",
            ServiceNamespace = "sagemaker",
            ResourceId = resource_id,
            ScalableDimension = "sagemaker:variant:DesiredInstanceCount",
        )
    except client.exceptions.ObjectNotFoundException:
        logger.info("Step-scaling policy not found, skipping.")
    except ClientError as ce:
        logger.error(f"Failed to delete step-scaling policy: {ce}")
        raise


    # Delete target-tracking policy
    try:
        client.delete_scaling_policy(
            PolicyName = "Invocations-ScalingPolicy",
            ServiceNamespace = "sagemaker",
            ResourceId = resource_id,
            ScalableDimension = "sagemaker:variant:DesiredInstanceCount",
        )
    except client.exceptions.ObjectNotFoundException:
        logger.info("Target-tracking policy not found, skipping.")
    except ClientError as ce:
        logger.error(f"Failed to delete target-tracking policy: {ce}")
        raise

    # Delete the CloudWatch alarm
    try:
        cw_client.delete_alarms(
            AlarmNames = ["HasBacklogWithoutCapacity-Alarm"],
        )
    except ClientError as ce:
        logger.error(f"Failed to delete CloudWatch alarm: {ce}")
        raise

    # Deregister the scalable target (removes autoscaling entirely)
    try:
        client.deregister_scalable_target(
            ServiceNamespace = "sagemaker",
            ResourceId = resource_id,
            ScalableDimension = "sagemaker:variant:DesiredInstanceCount",
        )
    except client.exceptions.ObjectNotFoundException:
        logger.info("Scalable target not found, skipping.")
    except ClientError as ce:
        logger.error(f"Failed to deregister scalable target: {ce}")
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
        
        add_scaling()
        
        logger.info("endpoint inservice")

    elif args.action == "teardown":
        
        delete_scaling()
        teardown()

        logger.info("endpoint removed")