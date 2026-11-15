import base64
import json
import os
import urllib.parse
import urllib.request
import uuid

import boto3

lex = boto3.client("lexv2-runtime")
INDEX = os.environ.get("OS_INDEX", "photos")
SLOT_NAMES = ["KeywordOne", "KeywordTwo"]

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
    "Content-Type": "application/json",
}

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

def respond(status, body):
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body)}

def get_keywords(q):
    resp = lex.recognize_text(
        botId=os.environ["BOT_ID"],
        botAliasId=os.environ["BOT_ALIAS_ID"],
        localeId=os.environ.get("LOCALE_ID", "en_US"),
        sessionId=str(uuid.uuid4()),
        text=q,
    )
    interpretations = resp.get("interpretations", [])
    if not interpretations:
        return []
    slots = interpretations[0].get("intent", {}).get("slots") or {}
    out = []
    for name in SLOT_NAMES:
        slot = slots.get(name)
        value = ((slot or {}).get("value") or {})
        word = value.get("interpretedValue") or value.get("originalValue")
        if word:
            out.append(word.strip().lower())
    return out

def variants(word):
    v = {word}
    if word.endswith("ies") and len(word) > 3:
        v.add(word[:-3] + "y")
    elif word.endswith("es") and len(word) > 3:
        v.add(word[:-2])
    if word.endswith("s") and len(word) > 2:
        v.add(word[:-1])
    else:
        v.add(word + "s")
    return sorted(v)

def build_query(keywords):
    should = []
    for k in keywords:
        for v in variants(k):
            should.append({"match": {"labels": v}})
    return {"query": {"bool": {"should": should, "minimum_should_match": 1}}, "size": 100}

def photo_url(bucket, key):
    return f"https://{bucket}.s3.amazonaws.com/{urllib.parse.quote(key)}"

def lambda_handler(event, context):
    q = ((event.get("queryStringParameters") or {}).get("q") or "").strip()
    if not q:
        return respond(200, {"results": []})
    try:
        keywords = get_keywords(q)
        print("q=%r keywords=%r" % (q, keywords))
        if not keywords:
            return respond(200, {"results": []})
        hits = os_request("POST", f"/{INDEX}/_search", build_query(keywords))["hits"]["hits"]
        results = [
            {"url": photo_url(h["_source"]["bucket"], h["_source"]["objectKey"]),
             "labels": h["_source"].get("labels", [])}
            for h in hits
        ]
        return respond(200, {"results": results})
    except Exception as exc:
        print("ERROR:", repr(exc))
        return respond(500, {"code": 500, "message": "Search failed"})