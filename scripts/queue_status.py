import sys
from pathlib import Path

import pika

QUEUES = ["notifications.q", "notifications.retry.q", "notifications.dead.q"]


def rabbitmq_url():
    for line in Path(".env").read_text().splitlines():
        if line.startswith("RABBITMQ_URL="):
            return line.split("=", 1)[1].strip()
    sys.exit("RABBITMQ_URL is missing in .env")


connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url()))
for name in QUEUES:
    try:
        channel = connection.channel()
        info = channel.queue_declare(name, passive=True)
        print(f"{name:26} {info.method.message_count} message(s)")
        channel.close()
    except pika.exceptions.ChannelClosedByBroker:
        print(f"{name:26} does not exist yet")
connection.close()