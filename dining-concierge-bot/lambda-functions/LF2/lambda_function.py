import base64
import json
import logging
import os
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

QUEUE_URL = os.environ["QUEUE_URL"]
OS_ENDPOINT = os.environ.get("OS_ENDPOINT", "").rstrip("/")
OS_USERNAME = os.environ.get("OS_USERNAME", "")
OS_PASSWORD = os.environ.get("OS_PASSWORD", "")
OS_INDEX = os.environ.get("OS_INDEX", "restaurants")
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
DYNAMO_TABLE = os.environ.get("DYNAMO_TABLE", "yelp-restaurants")
STATE_TABLE = os.environ.get("STATE_TABLE")
NUM_SUGGESTIONS = int(os.environ.get("NUM_SUGGESTIONS", "3"))
MAX_MESSAGES_PER_RUN = 10

sqs = boto3.client("sqs")
ses = boto3.client("ses")
dynamodb = boto3.resource("dynamodb")
restaurants_table = dynamodb.Table(DYNAMO_TABLE)
state_table = dynamodb.Table(STATE_TABLE) if STATE_TABLE else None

def _os_request(method, path, body=None):
    auth = base64.b64encode(f"{OS_USERNAME}:{OS_PASSWORD}".encode()).decode()
    req = urllib.request.Request(
        OS_ENDPOINT + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def random_restaurant_ids(cuisine, n):
    query = {
        "size": n,
        "_source": ["RestaurantID"],
        "query": {
            "function_score": {
                "query": {"term": {"Cuisine": cuisine.lower()}},
                "random_score": {},
                "boost_mode": "replace",
            }
        },
    }
    result = _os_request("POST", f"/{OS_INDEX}/_search", query)
    return [hit["_source"]["RestaurantID"] for hit in result["hits"]["hits"]]

def restaurant_details(ids):
    if not ids:
        return []
    resp = dynamodb.batch_get_item(
        RequestItems={DYNAMO_TABLE: {"Keys": [{"BusinessID": i} for i in ids]}}
    )
    by_id = {item["BusinessID"]: item for item in resp["Responses"].get(DYNAMO_TABLE, [])}
    return [by_id[i] for i in ids if i in by_id]

def _describe(r):
    rating = r.get("Rating")
    reviews = r.get("NumberOfReviews")
    extra = f" ({rating}★, {reviews} reviews)" if rating is not None and reviews is not None else ""
    return f"{r.get('Name', 'Unknown')}, located at {r.get('Address', 'address unavailable')}{extra}"

def _pretty_time(hhmm):
    try:
        h, m = map(int, hhmm.split(":"))
    except (ValueError, AttributeError):
        return hhmm
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{suffix}" if m else f"{h12}{suffix}"

def build_email(req, lines):
    people = req.get("numberOfPeople")
    people_txt = f"{people} {'person' if str(people) == '1' else 'people'}"
    header = (
        f"Hello! Here are my {req['cuisine']} restaurant suggestions for {people_txt}, "
        f"for {req.get('diningDate')} at {_pretty_time(req.get('diningTime'))}:"
    )
    if lines:
        body = "\n".join(f"    {i}. {line}" for i, line in enumerate(lines, 1))
        footer = "Enjoy your meal!"
    else:
        body = "    Sorry, I couldn't find any restaurants for that cuisine right now."
        footer = "Please try again later."
    return f"Your {req['cuisine']} restaurant suggestions", f"{header}\n\n{body}\n\n{footer}"


def send_email(to_addr, subject, text):
    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={"ToAddresses": [to_addr]},
        Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": text}}},
    )

def save_state(req, lines):
    if not state_table or not req.get("userId"):
        return
    try:
        state_table.put_item(Item={
            "userId": req["userId"],
            "location": req.get("location") or "",
            "cuisine": req.get("cuisine") or "",
            "email": req.get("email") or "",
            "numberOfPeople": str(req.get("numberOfPeople") or ""),
            "diningDate": req.get("diningDate") or "",
            "diningTime": req.get("diningTime") or "",
            "recommendations": lines,
            "updatedAt": req.get("requestedAt") or "",
        })
    except Exception:
        logger.exception("failed to save state")

def process(req):
    ids = random_restaurant_ids(req["cuisine"], NUM_SUGGESTIONS)
    restaurants = restaurant_details(ids)
    lines = [_describe(r) for r in restaurants]
    subject, text = build_email(req, lines)
    send_email(req["email"], subject, text)
    save_state(req, lines)
    logger.info("sent %d suggestions to %s", len(lines), req["email"])


def lambda_handler(event, context):
    resp = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=MAX_MESSAGES_PER_RUN,
        WaitTimeSeconds=1,
    )
    messages = resp.get("Messages", [])
    processed = failed = 0

    for msg in messages:
        try:
            req = json.loads(msg["Body"])
            process(req)
        except Exception:
            logger.exception("failed to process message %s", msg.get("MessageId"))
            failed += 1
            continue
        sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
        processed += 1

    result = {"received": len(messages), "processed": processed, "failed": failed}
    logger.info(json.dumps(result))
    return result
