import json
import logging
import threading

import pika
from sqlalchemy.exc import IntegrityError

from services.common.events import EXCHANGE

from .config import settings
from .database import SessionLocal
from .models import Notification, ProcessedEvent

logger = logging.getLogger("notifications")

QUEUE = "notifications.q"
RETRY_QUEUE = "notifications.retry.q"  # waits a few seconds, then goes back to QUEUE
DEAD_QUEUE = "notifications.dead.q"  # messages that failed too many times


def money(value) -> str:
    return f"INR {float(value):.2f}"


def build_notifications(event_type: str, data: dict, attempt: int) -> list:
    """Turn one event into zero or more notifications."""
    if event_type.startswith("test.") and settings.ENABLE_TEST_EVENTS:
        if attempt < int(data.get("fail_times", 0)):
            raise RuntimeError("Simulated failure for testing")
        return [
            {
                "user_id": data.get("user_id"),
                "audience": "user",
                "title": data.get("title", "Test notification"),
                "message": data.get("message", "This is a test"),
                "data": {},
            }
        ]

    user_id = data.get("user_id")
    number = data.get("order_number", "")
    order_data = {"order_id": data.get("order_id"), "order_number": number}

    if event_type == "order.created":
        return [{
            "user_id": user_id, "audience": "user", "data": order_data,
            "title": "Order placed",
            "message": f"Your order {number} was placed. Total {money(data['total_amount'])}. Please complete the payment.",
        }]
    if event_type == "order.confirmed":
        return [{
            "user_id": user_id, "audience": "user", "data": order_data,
            "title": "Order confirmed",
            "message": f"Payment received. Your order {number} is confirmed.",
        }]
    if event_type == "order.payment_failed":
        return [{
            "user_id": user_id, "audience": "user", "data": order_data,
            "title": "Payment failed",
            "message": f"The payment for order {number} did not go through. You can try again.",
        }]
    if event_type == "order.shipped":
        return [{
            "user_id": user_id, "audience": "user", "data": order_data,
            "title": "Order shipped",
            "message": f"Your order {number} is on its way.",
        }]
    if event_type == "order.delivered":
        return [{
            "user_id": user_id, "audience": "user", "data": order_data,
            "title": "Order delivered",
            "message": f"Your order {number} was delivered. You can now review the products.",
        }]
    if event_type == "order.cancelled":
        return [{
            "user_id": user_id, "audience": "user", "data": order_data,
            "title": "Order cancelled",
            "message": f"Your order {number} was cancelled. Reason: {data.get('reason', 'not given')}.",
        }]
    if event_type == "inventory.low_stock":
        left = data["quantity_available"]
        product = data["product_id"]
        if left <= 0:
            message = f"Product {product} is out of stock."
            title = "Out of stock"
        else:
            message = f"Product {product} is running low: {left} left (alert level {data['low_stock_threshold']})."
            title = "Low stock alert"
        return [{
            "user_id": None, "audience": "admin", "title": title, "message": message,
            "data": {"product_id": product, "quantity_available": left},
        }]
    return []  # an event we do not make notifications for


def process(body: bytes, attempt: int) -> str:
    """Handle one message. Returns 'created', 'ignored' or 'duplicate'."""
    envelope = json.loads(body)
    event_id = envelope["event_id"]
    event_type = envelope["type"]
    data = envelope.get("data", {})

    db = SessionLocal()
    try:
        if db.get(ProcessedEvent, event_id):
            return "duplicate"  # already handled, so do nothing
        items = build_notifications(event_type, data, attempt)
        for n in items:
            db.add(
                Notification(
                    user_id=n["user_id"],
                    audience=n["audience"],
                    event_type=event_type,
                    title=n["title"][:150],
                    message=n["message"][:500],
                    data=json.dumps(n["data"]),
                    event_id=event_id,
                )
            )
        db.add(ProcessedEvent(event_id=event_id, event_type=event_type))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return "duplicate"  # another copy was saved at the same moment
        return "created" if items else "ignored"
    finally:
        db.close()


class NotificationConsumer(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="notification-consumer")
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                self._consume()
            except Exception:
                logger.exception("Consumer problem; will reconnect in 10 seconds")
                self._stop_event.wait(10)

    @staticmethod
    def _declare(channel):
        channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        channel.queue_declare(QUEUE, durable=True)
        channel.queue_bind(QUEUE, EXCHANGE, "#")  # we receive every event type
        channel.queue_declare(
            RETRY_QUEUE,
            durable=True,
            arguments={
                "x-message-ttl": settings.RETRY_DELAY_SECONDS * 1000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": QUEUE,
            },
        )
        channel.queue_declare(DEAD_QUEUE, durable=True)

    def _consume(self):
        params = pika.URLParameters(settings.RABBITMQ_URL)
        params.socket_timeout = 10
        params.heartbeat = 30
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            self._declare(channel)
            channel.basic_qos(prefetch_count=10)
            channel.confirm_delivery()
            logger.warning("Notification consumer is listening")
            for method, props, body in channel.consume(QUEUE, inactivity_timeout=1):
                if self._stop_event.is_set():
                    break
                if method is None:
                    continue
                self._handle(channel, method, props, body)
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def _handle(self, channel, method, props, body):
        attempt = int((props.headers or {}).get("x-retry-count", 0))
        try:
            result = process(body, attempt)
            logger.warning(json.dumps({"event": "processed", "result": result, "attempt": attempt, "message_id": props.message_id}))
            channel.basic_ack(method.delivery_tag)
        except Exception:
            logger.exception("Could not process the message (attempt %s)", attempt)
            try:
                self._retry_or_bury(channel, body, props, attempt)
                channel.basic_ack(method.delivery_tag)
            except Exception:
                logger.exception("Could not schedule the retry; putting the message back")
                channel.basic_nack(method.delivery_tag, requeue=True)

    @staticmethod
    def _retry_or_bury(channel, body, props, attempt):
        headers = dict(props.headers or {})
        headers["x-retry-count"] = attempt + 1
        target = RETRY_QUEUE if attempt < settings.MAX_RETRIES else DEAD_QUEUE
        channel.basic_publish(
            "",
            target,
            body,
            pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
                message_id=props.message_id,
                headers=headers,
            ),
        )
        if target == DEAD_QUEUE:
            logger.error("Message %s moved to the dead queue after %s tries", props.message_id, attempt + 1)