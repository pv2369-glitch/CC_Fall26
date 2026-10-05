import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BOT_ID = os.environ.get("BOT_ID")
BOT_ALIAS_ID = os.environ.get("BOT_ALIAS_ID", "TESTALIASID")
LOCALE_ID = os.environ.get("LOCALE_ID", "en_US")

BOILERPLATE = "I'm still under development. Please come back later."
ERROR_REPLY = "Sorry, something went wrong on my end. Please try again."

_SESSION_ID_RE = re.compile(r"^[0-9a-zA-Z._:-]{2,100}$")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
}

lex = boto3.client("lexv2-runtime") if BOT_ID else None

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _bot_message(text, msg_id):
    return {
        "type": "unstructured",
        "unstructured": {"id": msg_id, "text": text, "timestamp": _now_iso()},
    }

def _extract_user_message(body):
    messages = (body or {}).get("messages") or []
    for msg in reversed(messages):
        unstructured = (msg or {}).get("unstructured") or {}
        text = (unstructured.get("text") or "").strip()
        if text:
            return text, unstructured.get("id")
    return "", None


def _session_id(client_id):
    if client_id and _SESSION_ID_RE.match(client_id):
        return client_id
    return "anon-" + uuid.uuid4().hex


def _ask_lex(text, session_id):
    resp = lex.recognize_text(
        botId=BOT_ID,
        botAliasId=BOT_ALIAS_ID,
        localeId=LOCALE_ID,
        sessionId=session_id,
        text=text,
    )
    replies = [m["content"] for m in resp.get("messages", []) if m.get("content")]
    return replies or ["Sorry, I didn't catch that. Could you rephrase?"]


def lambda_handler(event, context):
    logger.info("event: %s", json.dumps(event))

    is_proxy = isinstance(event, dict) and "httpMethod" in event
    if is_proxy:
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            body = {}
    else:
        body = event

    text, client_id = _extract_user_message(body)
    session_id = _session_id(client_id)

    if not text:
        replies = ["Please type a message."]
    elif not BOT_ID:
        replies = [BOILERPLATE]
    else:
        try:
            replies = _ask_lex(text, session_id)
        except Exception:
            logger.exception("Lex call failed")
            replies = [ERROR_REPLY]

    response = {"messages": [_bot_message(r, session_id) for r in replies]}

    if is_proxy:
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps(response)}
    return response
