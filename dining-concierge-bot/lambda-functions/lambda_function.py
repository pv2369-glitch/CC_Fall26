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