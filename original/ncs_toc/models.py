"""파싱과 판정 사이의 공통 경계. 기존 한국어 JSON 필드는 유지한다."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    path: Path
    format: str
    sections: list[list[str]]
    banners: list[tuple[int, int, str]] = field(default_factory=list)
    tables: dict[int, list[tuple[int, str, list[str]]]] = field(default_factory=dict)


@dataclass
class CheckContext:
    module_code: str
    toc: dict[str, Any]
    overview: dict[str, Any] | None
    plan: dict[str, Any] | None
    body: dict[str, Any]
    presence: dict[str, Any]
    eval_tables: list[tuple[int, str, list[str]]]


@dataclass
class InspectionResult:
    module_code: str
    checklist: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    context: CheckContext
