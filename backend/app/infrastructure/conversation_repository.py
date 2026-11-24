"""Persistence for conversations and messages."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def exists(self, conversation_id: uuid.UUID) -> bool:
        return self.session.get(Conversation, conversation_id) is not None

    def create(self) -> Conversation:
        conversation = Conversation()
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def recent_messages(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        if limit <= 0:
            return []
        rows = self.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.seq.desc())
            .limit(limit)
        )
        messages = list(reversed(list(rows)))
        while messages and messages[0].role != "user":
            messages.pop(0)  # an odd limit must not start history mid-turn
        return messages

    def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id, role=role, content=content, citations=citations or []
        )
        self.session.add(message)
        self.session.flush()
        return message
