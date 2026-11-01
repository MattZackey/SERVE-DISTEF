"""Render the API Gateway template and create or overwrite the echo-predict REST API"""

import configparser
import json
import logging
import re
from pathlib import Path

import boto3

logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "infra" / "config.ini"

cfg = configparser.ConfigParser()
if not cfg.read(CONFIG_PATH):
    raise SystemExit(f"infra/config.ini not found at {CONFIG_PATH}")
try:
    aws = cfg["aws"]
except KeyError:
    raise SystemExit(f"No [aws] section in {CONFIG_PATH}")

REQUIRED = {"REGION": "region", "ACCOUNT_ID": "account_id"}

values = {}
missing = []
for placeholder, key in REQUIRED.items():
    value = aws.get(key, "").strip()
    if value:
        values[placeholder] = value
    else:
        missing.append(key)
if missing:
    raise SystemExit(f"Missing in infra/config.ini [aws]: {', '.join(missing)}")

session = boto3.Session(
    profile_name = aws.get("profile", "default"),
    region_name = values["REGION"],
)

# Plain string replacement: str.format() would choke on the JSON's own braces
template_path = ROOT / aws.get("template", "infra/gateway/gateway.json")
body = template_path.read_text()
for key, value in values.items():
    body = body.replace("{" + key + "}", value)

leftover = set(re.findall(r"\{[A-Z_]+\}", body))
if leftover:
    raise SystemExit(f"Unfilled placeholders in template: {', '.join(sorted(leftover))}")
spec = json.loads(body)  # fail early if the result isn't valid JSON
api_name = spec.get("info", {}).get("title")
if not api_name:
    raise SystemExit("Template has no info.title, so the API can't be matched by name")

# Keep a copy of exactly what was imported, for debugging
rendered_dir = ROOT / "rendered_policy"
rendered_dir.mkdir(exist_ok = True)
rendered_path = rendered_dir / template_path.name
rendered_path.write_text(body)
logger.info("rendered template to %s", rendered_path)

apigw = session.client("apigateway")

# Look for an existing API with the same name
existing = [
    item
    for page in apigw.get_paginator("get_rest_apis").paginate()
    for item in page["items"]
    if item["name"] == api_name
]
if len(existing) > 1:
    ids = ", ".join(a["id"] for a in existing)
    raise SystemExit(f"Several APIs are named '{api_name}' ({ids}). Delete the extras first.")

if existing:
    api_id = existing[0]["id"]
    apigw.put_rest_api(
        restApiId = api_id,
        mode = "overwrite",
        body = body.encode(),
    )
    action = "updated"
else:
    api_id = apigw.import_rest_api(
        body = body.encode(),
    )["id"]
    action = "created"

stage = aws.get("stage", "dev")
apigw.create_deployment(
    restApiId = api_id,
    stageName = stage,
)

logger.info("%s API %s (%s) and deployed to '%s'", action, api_id, api_name, stage)
logger.info("https://%s.execute-api.%s.amazonaws.com/%s", api_id, values["REGION"], stage)
