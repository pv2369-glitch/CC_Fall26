import base64
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime

import boto3

rekognition = boto3.client("rekognition")
s3 = boto3.client("s3")

INDEX = os.environ.get("OS_INDEX", "photos")
MAX_LABELS = int(os.environ.get("MAX_LABELS", "50"))
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "70"))


def os_request(method, path, body):
    url = os.environ["OS_ENDPOINT"].rstrip("/") + path
    creds = f'{os.environ["OS_USERNAME"]}:{os.environ["OS_PASSWORD"]}'
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic " + base64.b64encode(creds.encode()).decode(),
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def parse_custom_labels(metadata):
    raw = (metadata or {}).get("customlabels", "")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def detect_labels(bucket, key):
    resp = rekognition.detect_labels(
        Image={"S3Object": {"Bucket": bucket, "Name": key}},
        MaxLabels=MAX_LABELS,
        MinConfidence=MIN_CONFIDENCE,
    )
    return [l["Name"].lower() for l in resp.get("Labels", [])]


def build_document(bucket, key, created, rek_labels, custom_labels):
    labels = []
    for l in rek_labels + custom_labels:
        if l not in labels:
            labels.append(l)
    return {
        "objectKey": key,
        "bucket": bucket,
        "createdTimestamp": created,
        "labels": labels,
    }


def lambda_handler(event, context):
    print("This is a canon event!!!!")
    indexed = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        head = s3.head_object(Bucket=bucket, Key=key)
        custom = parse_custom_labels(head.get("Metadata"))
        rek = detect_labels(bucket, key)
        created = (record.get("eventTime") or datetime.utcnow().isoformat())[:19]
        doc = build_document(bucket, key, created, rek, custom)
        print("Indexing:", json.dumps(doc))
        doc_id = urllib.parse.quote(f"{bucket}/{key}", safe="")
        os_request("PUT", f"/{INDEX}/_doc/{doc_id}?refresh=true", doc)
        indexed.append(doc)
    return {"indexed": len(indexed)}
