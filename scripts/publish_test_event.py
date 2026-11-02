import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pika

EXCHANGE = "ioms.events"


def rabbitmq_url():
    for line in Path(".env").read_text().splitlines():
        if line.startswith("RABBITMQ_URL="):
            return line.split("=", 1)[1].strip()
    sys.exit("RABBITMQ_URL is missing in .env")


if len(sys.argv) != 3 or sys.argv[2] not in ("single", "duplicate", "retry", "dead"):
    sys.exit("Usage: python scripts\\publish_test_event.py <user_id> <single|duplicate|retry|dead>")

user_id = int(sys.argv[1])
mode = sys.argv[2]
fail_times = {"single": 0, "duplicate": 0, "retry": 2, "dead": 99}[mode]
event = {
    "event_id": str(uuid.uuid4()),
    "type": "test.notification",
    "occurred_at": datetime.now(timezone.utc).isoformat(),
    "data": {
        "user_id": user_id,
        "title": f"Test: {mode}",
        "message": f"This notification came from the '{mode}' test.",
        "fail_times": fail_times,
    },
}

connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url()))
channel = connection.channel()
channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
channel.confirm_delivery()
copies = 2 if mode == "duplicate" else 1
for _ in range(copies):  # the SAME event id is sent twice in duplicate mode
    channel.basic_publish(
        EXCHANGE,
        "test.notification",
        json.dumps(event).encode("utf-8"),
        pika.BasicProperties(content_type="application/json", delivery_mode=2, message_id=event["event_id"]),
        mandatory=True,
    )
connection.close()
print(f"Sent {copies} message(s) in '{mode}' mode for user {user_id}")