import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

QUEUE_URL = os.environ.get("QUEUE_URL")
STATE_TABLE = os.environ.get("STATE_TABLE")

SUPPORTED_CUISINES = ["chinese", "italian", "japanese", "mexican", "indian", "thai", "korean"]
SUPPORTED_LOCATIONS = {
    "manhattan", "manhattan ny", "manhattan, ny", "new york", "new york city", "nyc", "ny",
    "new york, ny", "manhattan new york",
}

MAX_PARTY_SIZE = 20
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

sqs = boto3.client("sqs") if QUEUE_URL else None
state_table = boto3.resource("dynamodb").Table(STATE_TABLE) if STATE_TABLE else None

def _now_nyc():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=-4)))

def _slot_value(slots, name):
    slot = (slots or {}).get(name)
    if not slot or not slot.get("value"):
        return None
    value = slot["value"]
    if value.get("interpretedValue"):
        return value["interpretedValue"]
    resolved = value.get("resolvedValues") or []
    if resolved:
        return resolved[-1]
    return value.get("originalValue")

def _set_slot(slots, name, value):
    slots[name] = None if value is None else {
        "shape": "Scalar",
        "value": {"originalValue": value, "interpretedValue": value, "resolvedValues": [value]},
    }

def _msg(text):
    return [{"contentType": "PlainText", "content": text}]

def close(event, text, state="Fulfilled", session_attributes=None):
    intent = event["sessionState"]["intent"]
    intent["state"] = state
    return {
        "sessionState": {
            "sessionAttributes": session_attributes or {},
            "dialogAction": {"type": "Close"},
            "intent": intent,
        },
        "messages": _msg(text),
    }

def elicit_slot(event, slots, slot_name, text, session_attributes):
    intent = event["sessionState"]["intent"]
    intent["slots"] = slots
    intent["state"] = "InProgress"
    return {
        "sessionState": {
            "sessionAttributes": session_attributes,
            "dialogAction": {"type": "ElicitSlot", "slotToElicit": slot_name},
            "intent": intent,
        },
        "messages": _msg(text),
    }

def delegate(event, slots, session_attributes):
    intent = event["sessionState"]["intent"]
    intent["slots"] = slots
    return {
        "sessionState": {
            "sessionAttributes": session_attributes,
            "dialogAction": {"type": "Delegate"},
            "intent": intent,
        },
    }

def validate_location(value):
    if value is None:
        return None, None
    if value.strip().lower().rstrip(".") in SUPPORTED_LOCATIONS:
        return "Manhattan", None
    return None, f"Sorry, I can't fulfill requests for {value}. I only cover Manhattan right now. Please enter a valid location."

def validate_cuisine(value):
    if value is None:
        return None, None
    v = value.strip().lower()
    if v in SUPPORTED_CUISINES:
        return v.title(), None
    options = ", ".join(c.title() for c in SUPPORTED_CUISINES)
    return None, f"Sorry, I don't have suggestions for {value} yet. Try one of: {options}."

def validate_people(value):
    if value is None:
        return None, None
    try:
        n = int(float(value))
    except ValueError:
        return None, "Sorry, how many people are in your party? Please give me a number."
    if n < 1 or n > MAX_PARTY_SIZE:
        return None, f"I can only book for 1 to {MAX_PARTY_SIZE} people. How many people are in your party?"
    return str(n), None

def validate_date(value):
    if value is None:
        return None, None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None, "Sorry, I didn't understand that date. What date would you like to dine?"
    today = _now_nyc().date()
    if d < today:
        return None, "That date is in the past. What date would you like to dine?"
    if d > today + timedelta(days=90):
        return None, "I can only help with dates in the next 90 days. What date would you like to dine?"
    return d.isoformat(), None

def validate_time(value, dining_date):
    if value is None:
        return None, None
    if not TIME_RE.match(value):
        return None, "Sorry, I didn't understand that time. What time would you like to dine? (e.g. 7 pm)"
    if dining_date:
        now = _now_nyc()
        when = datetime.combine(date.fromisoformat(dining_date), datetime.strptime(value, "%H:%M").time())
        if when <= now.replace(tzinfo=None):
            return None, "That time has already passed today. What time would you like to dine?"
    return value, None

def validate_email(value):
    if value is None:
        return None, None
    v = value.strip()
    if EMAIL_RE.match(v):
        return v.lower(), None
    return None, "That doesn't look like a valid email address. What email should I send the suggestions to?"

def _get_last_search(user_id):
    if not state_table:
        return None
    try:
        return state_table.get_item(Key={"userId": user_id}).get("Item")
    except Exception:
        logger.exception("state lookup failed")
        return None

def _format_previous(item):
    recs = item.get("recommendations") or []
    lines = "\n".join(f"{i}. {r}" for i, r in enumerate(recs, 1))
    return lines

def handle_greeting(event):
    return close(event, "Hi there, how can I help?")

def handle_thank_you(event):
    return close(event, "You're welcome! Enjoy your meal.")

def handle_fallback(event):
    return close(
        event,
        "Sorry, I didn't get that. You can say something like \"I need restaurant suggestions\".",
        state="Failed",
    )

def handle_dining(event):
    intent = event["sessionState"]["intent"]
    slots = intent.get("slots") or {}
    attrs = event["sessionState"].get("sessionAttributes") or {}
    source = event.get("invocationSource")

    if source == "FulfillmentCodeHook":
        return fulfill_dining(event, slots, attrs)

    location, err = validate_location(_slot_value(slots, "Location"))
    if err:
        _set_slot(slots, "Location", None)
        return elicit_slot(event, slots, "Location", err, attrs)
    if location:
        _set_slot(slots, "Location", location)

    cuisine, err = validate_cuisine(_slot_value(slots, "Cuisine"))
    if err:
        _set_slot(slots, "Cuisine", None)
        return elicit_slot(event, slots, "Cuisine", err, attrs)
    if cuisine:
        _set_slot(slots, "Cuisine", cuisine)

    if location and cuisine and STATE_TABLE:
        reuse = _slot_value(slots, "UseLastSearch")
        if reuse is None and attrs.get("reuseChecked") != "true":
            attrs["reuseChecked"] = "true"
            last = _get_last_search(event["sessionId"])
            if (last and last.get("recommendations")
                    and last.get("location", "").lower() == location.lower()
                    and last.get("cuisine", "").lower() == cuisine.lower()):
                attrs["lastSearchMatched"] = "true"
                return elicit_slot(
                    event, slots, "UseLastSearch",
                    f"Welcome back! Last time you asked for {cuisine} food in {location}, I suggested:\n"
                    f"{_format_previous(last)}\nWould you like the same recommendations again? (yes/no)",
                    attrs,
                )
        elif reuse and attrs.get("lastSearchMatched") == "true":
            if reuse.lower() in ("yes", "y", "yeah", "sure"):
                last = _get_last_search(event["sessionId"]) or {}
                return close(
                    event,
                    f"Great! Here are your {cuisine} suggestions again:\n{_format_previous(last)}\nEnjoy your meal!",
                    session_attributes={},
                )

    people, err = validate_people(_slot_value(slots, "NumberOfPeople"))
    if err:
        _set_slot(slots, "NumberOfPeople", None)
        return elicit_slot(event, slots, "NumberOfPeople", err, attrs)
    if people:
        _set_slot(slots, "NumberOfPeople", people)

    dining_date, err = validate_date(_slot_value(slots, "DiningDate"))
    if err:
        _set_slot(slots, "DiningDate", None)
        return elicit_slot(event, slots, "DiningDate", err, attrs)

    dining_time, err = validate_time(_slot_value(slots, "DiningTime"), dining_date)
    if err:
        _set_slot(slots, "DiningTime", None)
        return elicit_slot(event, slots, "DiningTime", err, attrs)
    if dining_time:
        _set_slot(slots, "DiningTime", dining_time)

    email, err = validate_email(_slot_value(slots, "Email"))
    if err:
        _set_slot(slots, "Email", None)
        return elicit_slot(event, slots, "Email", err, attrs)

    return delegate(event, slots, attrs)

def fulfill_dining(event, slots, attrs):
    request = {
        "userId": event["sessionId"],
        "location": _slot_value(slots, "Location"),
        "cuisine": _slot_value(slots, "Cuisine"),
        "numberOfPeople": _slot_value(slots, "NumberOfPeople"),
        "diningDate": _slot_value(slots, "DiningDate"),
        "diningTime": _slot_value(slots, "DiningTime"),
        "email": (_slot_value(slots, "Email") or "").strip().lower(),
        "requestedAt": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("dining request: %s", json.dumps(request))

    if not sqs:
        logger.error("QUEUE_URL not configured")
        return close(event, "Sorry, I can't take requests right now. Please try again later.", state="Failed")

    try:
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(request))
    except Exception:
        logger.exception("SQS send failed")
        return close(event, "Sorry, I couldn't submit your request. Please try again.", state="Failed")

    return close(
        event,
        f"You're all set. I've received your request for {request['cuisine']} food in {request['location']} "
        f"for {request['numberOfPeople']} on {request['diningDate']} at {request['diningTime']}. "
        f"Expect my suggestions at {request['email']} shortly! Have a good day.",
        session_attributes={},
    )

HANDLERS = {
    "GreetingIntent": handle_greeting,
    "ThankYouIntent": handle_thank_you,
    "DiningSuggestionsIntent": handle_dining,
    "FallbackIntent": handle_fallback,
}

def lambda_handler(event, context):
    logger.info("event: %s", json.dumps(event))
    intent_name = event["sessionState"]["intent"]["name"]
    handler = HANDLERS.get(intent_name)
    if not handler:
        return close(event, "Sorry, I can't help with that yet.", state="Failed")
    response = handler(event)
    logger.info("response: %s", json.dumps(response))
    return response
