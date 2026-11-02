import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pika
from pika.exceptions import UnroutableError
from sqlalchemy import Column, DateTime, Integer, String, Text

logger = logging.getLogger("events")
EXCHANGE = "ioms.events"


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def rabbitmq_url() -> str:
    """Read RABBITMQ_URL from the environment or from the .env file."""
    url = os.environ.get("RABBITMQ_URL", "")
    if url:
        return url
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("RABBITMQ_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def create_outbox_model(base):
    """Every service that sends events gets its own 'outbox_events' table."""

    class OutboxEvent(base):
        __tablename__ = "outbox_events"

        id = Column(Integer, primary_key=True)
        event_id = Column(String(36), unique=True, nullable=False)
        routing_key = Column(String(100), nullable=False)
        payload = Column(Text, nullable=False)  # the whole event, as JSON
        created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
        published_at = Column(DateTime, nullable=True, index=True)
        attempts = Column(Integer, nullable=False, default=0)

    return OutboxEvent


def emit(db, outbox_model, routing_key: str, data: dict):
    """Save an event in the outbox. Call this BEFORE db.commit(), so the event
    and the business change are saved together or not at all."""
    event_id = str(uuid.uuid4())
    envelope = {
        "event_id": event_id,
        "type": routing_key,
        "occurred_at": utcnow().isoformat(),
        "data": data,
    }
    db.add(
        outbox_model(
            event_id=event_id,
            routing_key=routing_key,
            payload=json.dumps(envelope),
        )
    )


class OutboxPublisher(threading.Thread):
    """Sends saved events to RabbitMQ in the background, oldest first."""

    def __init__(self, session_factory, outbox_model, service_name: str, interval: float = 3.0):
        super().__init__(daemon=True, name=f"outbox-{service_name}")
        self.session_factory = session_factory
        self.model = outbox_model
        self.interval = interval
        self.url = rabbitmq_url()
        self._stop_event = threading.Event()
        self._connection = None
        self._channel = None

    def stop(self):
        self._stop_event.set()

    def _connect(self):
        params = pika.URLParameters(self.url)
        params.socket_timeout = 10
        params.heartbeat = 30
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        self._channel.confirm_delivery()  # wait until the broker confirms each message

    def _close(self):
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._channel = None

    def _publish_pending(self):
        db = self.session_factory()
        try:
            rows = (
                db.query(self.model)
                .filter(self.model.published_at.is_(None))
                .order_by(self.model.id)
                .limit(50)
                .all()
            )
            if not rows:
                return
            if self._channel is None or self._connection is None or self._connection.is_closed:
                self._connect()
            for row in rows:
                row.attempts += 1
                try:
                    self._channel.basic_publish(
                        EXCHANGE,
                        row.routing_key,
                        row.payload.encode("utf-8"),
                        pika.BasicProperties(
                            content_type="application/json",
                            delivery_mode=2,  # keep the message on disk
                            message_id=row.event_id,
                            type=row.routing_key,
                        ),
                        mandatory=True,
                    )
                    row.published_at = utcnow()
                except UnroutableError:
                    pass  # nobody is listening yet, so keep the event and try again later
                db.commit()
        finally:
            db.close()

    def run(self):
        if not self.url:
            logger.warning("RABBITMQ_URL is not set: events will wait in the outbox")
        while not self._stop_event.is_set():
            delay = self.interval
            if not self.url:
                delay = 30
            else:
                try:
                    self._publish_pending()
                    if self._connection is not None and self._connection.is_open:
                        self._connection.process_data_events()  # keeps the connection alive
                except Exception:
                    logger.exception("Outbox publisher problem; will reconnect")
                    self._close()
                    delay = 10
            self._stop_event.wait(delay)
        self._close()


def start_outbox_publisher(session_factory, outbox_model, service_name: str) -> OutboxPublisher:
    publisher = OutboxPublisher(session_factory, outbox_model, service_name)
    publisher.start()
    return publisher