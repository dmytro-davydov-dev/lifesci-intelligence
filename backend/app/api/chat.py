"""Grounded chat endpoint."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.api.errors import ApiError
from app.application.chat import (
    ChatResult,
    ChatService,
    ConversationNotFoundError,
    InvalidDocumentScopeError,
    RequestTimeoutError,
)
from app.domain.providers import ChatError, EmbeddingError, ModelTimeoutError

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_QUESTION_CHARS = 2000


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    mode: Literal["auto", "qa", "compare"] = "auto"

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class CitationOut(BaseModel):
    label: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page: int | None
    section: str | None
    quote: str


class FindingOut(BaseModel):
    topic: str
    assessment: Literal["supported", "potential_gap", "insufficient_evidence"]
    explanation: str
    citation_labels: list[str]


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    status: Literal["answered", "insufficient_evidence", "clarification"]
    citations: list[CitationOut]
    # Present for comparison answers; empty for grounded Q&A.
    findings: list[FindingOut] = []


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, service: Annotated[ChatService, Depends(get_chat_service)]):
    try:
        result: ChatResult = service.ask(
            body.question, body.conversation_id, body.document_ids, body.mode
        )
    except ConversationNotFoundError as exc:
        raise ApiError(404, "conversation_not_found", "Conversation not found.") from exc
    except InvalidDocumentScopeError as exc:
        raise ApiError(422, "invalid_document_scope", str(exc)) from exc
    except (RequestTimeoutError, ModelTimeoutError) as exc:
        raise ApiError(504, "request_timeout", str(exc)) from exc
    except (ChatError, EmbeddingError) as exc:
        raise ApiError(503, "model_unavailable", str(exc)) from exc
    return ChatResponse(
        conversation_id=result.conversation_id,
        answer=result.answer,
        status=result.status,
        citations=[CitationOut(**c.__dict__) for c in result.citations],
        findings=[FindingOut(**f.__dict__) for f in result.findings],
    )
