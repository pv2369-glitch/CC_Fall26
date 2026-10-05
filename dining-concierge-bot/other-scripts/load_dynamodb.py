import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

import config

HERE = os.path.dirname(os.path.abspath(__file__))


def _clean(value):
    if isinstance(value, dict):
        cleaned = {k: _clean(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [_clean(v) for v in value if v not in (None, "")]
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default=None)
    args = ap.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(config.DYNAMO_TABLE)
    try:
        table.load()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "AccessDeniedException":
            hint = "Your CLI user lacks DynamoDB permissions - attach infra/iam/local-cli-user-policy.json (docs/SETUP_STAGES.md, Stage 5)."
        elif code == "ResourceNotFoundException":
            hint = "Table not found - create it first (docs/SETUP_STAGES.md, Stage 5) and check the region is us-east-1."
        else:
            hint = "See docs/SETUP_STAGES.md, Stage 5."
        sys.exit(f"Can't access table {config.DYNAMO_TABLE!r}: {e}\n{hint}")

    with open(os.path.join(HERE, config.DATA_FILE)) as f:
        records = json.load(f, parse_float=Decimal)

    with table.batch_writer(overwrite_by_pkeys=["BusinessID"]) as batch:
        for i, r in enumerate(records, 1):
            item = _clean(r)
            item["insertedAtTimestamp"] = datetime.now(timezone.utc).isoformat()
            batch.put_item(Item=item)
            if i % 200 == 0:
                print(f"  {i}/{len(records)}")
    print(f"Wrote {len(records)} items to {config.DYNAMO_TABLE}")


if __name__ == "__main__":
    main()
