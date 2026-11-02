from pathlib import Path

import pika


def load_env():
    values = {}
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


env = load_env()

# RabbitMQ: send one message to a queue and read it back
url = env.get("RABBITMQ_URL", "")
if not url:
    print("FAIL  RABBITMQ_URL is missing in the .env file")
else:
    try:
        params = pika.URLParameters(url)
        params.socket_timeout = 10
        params.connection_attempts = 2
        params.retry_delay = 2
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare("infra_check", durable=True)
        channel.basic_publish(
            "", "infra_check", b"hello", properties=pika.BasicProperties(delivery_mode=2)
        )
        _, _, body = channel.basic_get("infra_check", auto_ack=True)
        channel.queue_delete("infra_check")
        connection.close()
        print("PASS  RabbitMQ works" if body == b"hello" else "FAIL  RabbitMQ gave a wrong message")
    except Exception as exc:
        print(f"FAIL  RabbitMQ: {type(exc).__name__}: {exc}")

# Redis is optional for now
redis_url = env.get("REDIS_URL", "")
if not redis_url:
    print("SKIP  Redis (REDIS_URL is not set yet, we do this later)")
else:
    try:
        import redis

        client = redis.from_url(redis_url, socket_connect_timeout=5)
        client.set("infra_check", "ok", ex=30)
        print("PASS  Redis works" if client.get("infra_check") == b"ok" else "FAIL  Redis gave a wrong value")
    except Exception as exc:
        print(f"FAIL  Redis: {type(exc).__name__}: {exc}")