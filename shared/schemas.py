from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal
import uuid


class DictMixin:
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class JobContext(DictMixin):
    job_id: str
    grade: Literal["Year 6"] = "Year 6"
    constraints: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)

    @staticmethod
    def new(grade: Literal["Year 6"] = "Year 6") -> "JobContext":
        return JobContext(job_id=str(uuid.uuid4()), grade=grade)


@dataclass
class Passage(DictMixin):
    id: str
    text: str
    source_url: Optional[str] = None


@dataclass
class Evidence(DictMixin):
    ocr_text: Optional[str] = None
    passages: List[Passage] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class Choice(DictMixin):
    id: str
    text: str


@dataclass
class Item(DictMixin):
    id: str
    subject: Literal["math", "thinking", "english"]
    prompt: str
    choices: List[Choice]
    answer: str
    solution: str
    evidence_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)