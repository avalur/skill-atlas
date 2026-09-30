"""Data models for Skill Atlas."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    file: str | None = None
    line: int | None = None
    suggestion: str | None = None


class Skill(BaseModel):
    name: str
    description: str = ""
    repo_name: str | None = None
    repo_url: str | None = None
    commit: str | None = None
    commit_date: str | None = None
    path: str
    version: str | None = None
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    valid: bool = True
    findings: list[Finding] = Field(default_factory=list)

    # Runtime analysis helpers (excluded from final serialization if desired)
    raw_content: str | None = Field(default=None, repr=False)
    frontmatter: dict[str, Any] = Field(default_factory=dict, repr=False)
    markdown_body: str = Field(default="", repr=False)
    referenced_files: list[str] = Field(default_factory=list, repr=False)
    available_files: list[str] = Field(default_factory=list, repr=False)
    repo_files: list[str] = Field(default_factory=list, repr=False)
    base_dir: str | None = Field(default=None, repr=False)
    repo_root_dir: str | None = Field(default=None, repr=False)
    parse_error: str | None = Field(default=None, repr=False)

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)
        if finding.severity == Severity.ERROR:
            self.valid = False


class ScanSummary(BaseModel):
    total_skills: int = 0
    passed: int = 0
    failed: int = 0
    findings_count: dict[str, int] = Field(
        default_factory=lambda: {"error": 0, "warn": 0, "info": 0}
    )


class ScanResult(BaseModel):
    version: str = "0.1.0"
    target: str
    summary: ScanSummary
    skills: list[Skill]
