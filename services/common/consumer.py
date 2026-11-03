import json
import logging
import threading

import pika

from .events import EXCHANGE, rabbitmq_url


class EventConsumer(threading.Thread):
    """Listens to RabbitMQ in the background. Failed messages are retried a few
    times, then moved to a 'dead' queue so they cannot block everything else."""

    def __init__(self, name, routing_keys, handler, max_retries=3, retry_delay_seconds=10):
        super().__init__(daemon=True, name=f"consumer-{name}")
        self.queue = f"{name}.q"
        self.retry_queue = f"{name}.retry.q"
        self.dead_queue = f"{name}.dead.q"
        self.routing_keys = routing_keys
        self.handler = handler
        self.max_retries = max_retries
        self.retry_delay = retry_delay_seconds
        self.logger = logging.getLogger(f"consumer.{name}")
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                self._consume()
            except Exception:
                self.logger.exception("Consumer problem; will reconnect in 10 seconds")
                self._stop_event.wait(10)

    def _declare(self, channel):
        channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
        channel.queue_declare(self.queue, durable=True)
        for key in self.routing_keys:
            channel.queue_bind(self.queue, EXCHANGE, key)
        channel.queue_declare(
            self.retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.retry_delay * 1000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": self.queue,
            },
        )
        channel.queue_declare(self.dead_queue, durable=True)

    def _consume(self):
        params = pika.URLParameters(rabbitmq_url())
        params.socket_timeout = 10
        params.heartbeat = 30
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            self._declare(channel)
            channel.basic_qos(prefetch_count=10)
            channel.confirm_delivery()
            logging.getLogger("consumer").warning("Listening on %s", self.queue)
            for method, props, body in channel.consume(self.queue, inactivity_timeout=1):
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
            result = self.handler(json.loads(body))
            self.logger.warning(
                json.dumps({"event": "processed", "result": result, "attempt": attempt, "message_id": props.message_id})
            )
            channel.basic_ack(method.delivery_tag)
        except Exception:
            self.logger.exception("Could not process the message (attempt %s)", attempt)
            try:
                headers = dict(props.headers or {})
                headers["x-retry-count"] = attempt + 1
                target = self.retry_queue if attempt < self.max_retries else self.dead_queue
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
                if target == self.dead_queue:
                    self.logger.error("Message %s moved to the dead queue", props.message_id)
                channel.basic_ack(method.delivery_tag)
            except Exception:
                self.logger.exception("Could not schedule the retry; putting the message back")
                channel.basic_nack(method.delivery_tag, requeue=True)