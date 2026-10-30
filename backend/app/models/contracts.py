from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.core.config import settings

class Document(BaseModel):
    id: str
    company_id: str | None = None
    filename: str
    format: Literal['pdf', 'txt', 'md']
    policy_family: str | None = None
    version: str | None = None
    effective_date: date | None = None
    status: Literal['current', 'superseded', 'draft']
    superseded_by: str | None = None
    processing_status: str = 'pending'
    chunk_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

class Passage(BaseModel):
    id: str
    document_id: str
    text: str
    section: str | None = None
    page: int | None = Field(default=None, ge=1)
    metadata: dict = Field(default_factory=dict)

class Citation(BaseModel):
    document_id: str
    passage_id: str
    filename: str
    version: str | None = None
    section: str | None = None
    page: int | None = Field(default=None, ge=1)
    quote: str
    document: str = ""
    chunk_id: str = ""

class Answer(BaseModel):
    question: str
    answer: str
    status: Literal['answered', 'partially_answered', 'not_covered']
    citations: list[Citation]
    supported_parts: list[str] = Field(default_factory=list)
    unsupported_parts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class Question(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=2000)
    policy_family: str | None = Field(default=None, max_length=150)
    version: str | None = Field(default=None, max_length=80)
    as_of: date | None = None
    top_k: int = Field(default_factory=lambda: settings.retrieval_top_k, ge=1, le=12)
    mode: Literal['semantic', 'hybrid'] = 'hybrid'

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Question cannot be blank')
        return value.strip()

class BatchRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    questions: list[Question] = Field(min_length=1, max_length=100)

class UploadMetadata(BaseModel):
    model_config=ConfigDict(extra='forbid')
    policy_family: str | None = Field(default=None, max_length=150)
    version: str | None = Field(default=None, max_length=80)
    effective_date: date | None = None
    status: Literal['current', 'superseded', 'draft'] = 'draft'
    superseded_by: str | None = None

class Chunk(BaseModel):
    chunk_id: str
    company_id: str | None = None
    document_id: str
    document_name: str
    policy_family: str | None = None
    version: str | None = None
    version_status: str
    section: str | None = None
    page: int | None = None
    text: str
    is_table: bool = False
    score: float = 0

class Claim(BaseModel):
    text: str = Field(max_length=1500)
    chunk_id: str
    quote: str = Field(min_length=1, max_length=3000)

class Draft(BaseModel):
    claims: list[Claim] = Field(max_length=12)

class Verification(BaseModel):
    supported_claims: list[int] = Field(max_length=12)
    supported_parts: list[str] = Field(max_length=12)
    unsupported_parts: list[str] = Field(max_length=12)
    all_parts_covered: bool
