# Replaying dead-lettered messages

Tags: dlq, dead letter, replay, retry, failed messages, stuck orders, pending payment

## When to replay
Only after the consumer that failed is healthy again. Replaying into a broken consumer sends the message straight back to the DLQ.

## Steps
1. List dead messages with `list_dlq_messages` and group them by consumer.
2. Confirm the consumer is healthy with `get_service_status`.
3. Request `replay_dlq_message` for each message. Each request needs approval from SRE or Admin.
4. Check the order trace with `get_order_trace` to confirm the order moved forward.
