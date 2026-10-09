import base64
import json
import os
import urllib.request

import config

HERE = os.path.dirname(os.path.abspath(__file__))
ENDPOINT = os.environ["OS_ENDPOINT"].rstrip("/")
AUTH = base64.b64encode(f"{os.environ['OS_USERNAME']}:{os.environ['OS_PASSWORD']}".encode()).decode()

INDEX_BODY = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "_meta": {"type": config.OS_TYPE},
        "properties": {
            "RestaurantID": {"type": "keyword"},
            "Cuisine": {"type": "keyword"},
            "type": {"type": "keyword"},
        },
    },
}

def request(method, path, data, content_type="application/json"):
    req = urllib.request.Request(
        ENDPOINT + path, data=data.encode(), method=method,
        headers={"Authorization": f"Basic {AUTH}", "Content-Type": content_type},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def main():
    request("PUT", f"/{config.OS_INDEX}", json.dumps(INDEX_BODY))

    with open(os.path.join(HERE, config.DATA_FILE)) as f:
        records = json.load(f)

    lines = []
    for r in records:
        lines.append(json.dumps({"index": {"_index": config.OS_INDEX, "_id": r["BusinessID"]}}))
        lines.append(json.dumps({"RestaurantID": r["BusinessID"], "Cuisine": r["Cuisine"], "type": config.OS_TYPE}))
    request("POST", "/_bulk?refresh=true", "\n".join(lines) + "\n", "application/x-ndjson")
    print(f"Loaded {len(records)} restaurants into {config.OS_INDEX}")

if __name__ == "__main__":
    main()