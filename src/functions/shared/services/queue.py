"""
Azure Storage Queue client wrapper for enqueueing messages.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from azure.storage.queue.aio import QueueClient
from azure.storage.queue import TextBase64EncodePolicy

from shared.schemas.queue_messages import ArticleQueueMessage

logger = logging.getLogger(__name__)


@dataclass
class QueueService:
    connection_string: str
    queue_name: str
    create_queue: bool = True
    _client: QueueClient | None = None

    async def _get_client(self) -> QueueClient:
        if self._client is None:
            self._client = QueueClient.from_connection_string(
                conn_str=self.connection_string,
                queue_name=self.queue_name,
                message_encode_policy=TextBase64EncodePolicy(),
            )
            if self.create_queue:
                try:
                    await self._client.create_queue()
                except Exception as exc:  # queue may already exist
                    from azure.core.exceptions import ResourceExistsError

                    if isinstance(exc, ResourceExistsError):
                        logger.debug("Queue %s already exists; continuing.", self.queue_name)
                    else:
                        raise
        return self._client

    async def send_article_message(self, message: ArticleQueueMessage) -> None:
        client = await self._get_client()
        payload = message.model_dump_json()
        logger.debug("Enqueueing message to %s: %s", self.queue_name, payload)
        await client.send_message(payload)

    async def send_raw(self, obj: Any) -> None:
        client = await self._get_client()
        payload = json.dumps(obj)
        logger.debug("Enqueueing raw message to %s: %s", self.queue_name, payload)
        await client.send_message(payload)

    async def close(self) -> None:
        if self._client:
            await self._client.close()

