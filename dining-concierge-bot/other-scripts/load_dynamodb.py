import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

import config

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(config.DYNAMO_TABLE)

    with open(os.path.join(HERE, config.DATA_FILE)) as f:
        records = json.load(f, parse_float=Decimal)

    with table.batch_writer(overwrite_by_pkeys=["BusinessID"]) as batch:
        for r in records:
            r["insertedAtTimestamp"] = datetime.now(timezone.utc).isoformat()
            batch.put_item(Item=r)
    print(f"Wrote {len(records)} items to {config.DYNAMO_TABLE}")

if __name__ == "__main__":
    main()