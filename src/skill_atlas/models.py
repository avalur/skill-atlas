"""Data models for Skill Atlas."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from skill_atlas import __version__


class Severity(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    file: str = "SKILL.md"
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

    # Runtime analysis helpers (excluded from serialization)
    raw_content: str | None = Field(default=None, repr=False, exclude=True)
    frontmatter: dict[str, Any] = Field(default_factory=dict, repr=False, exclude=True)
    markdown_body: str = Field(default="", repr=False, exclude=True)
    referenced_files: list[str] = Field(default_factory=list, repr=False, exclude=True)
    available_files: list[str] = Field(default_factory=list, repr=False, exclude=True)
    companion_contents: dict[str, str] = Field(default_factory=dict, repr=False, exclude=True)
    repo_files: list[str] = Field(default_factory=list, repr=False, exclude=True)
    base_dir: str | None = Field(default=None, repr=False, exclude=True)
    repo_root_dir: str | None = Field(default=None, repr=False, exclude=True)
    parse_error: str | None = Field(default=None, repr=False, exclude=True)

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)
        if finding.severity == Severity.ERROR:
            self.valid = False

    def is_passing(self, fail_on: str = "error") -> bool:
        """Check whether the skill passes the given fail-on severity threshold."""
        threshold = fail_on.lower().strip()
        if threshold == "warn":
            return not any(f.severity in (Severity.ERROR, Severity.WARN) for f in self.findings)
        return not any(f.severity == Severity.ERROR for f in self.findings)


class ScanSummary(BaseModel):
    total_skills: int = 0
    passed: int = 0
    failed: int = 0
    findings_count: dict[str, int] = Field(
        default_factory=lambda: {"error": 0, "warn": 0, "info": 0}
    )


class ScanResult(BaseModel):
    version: str = Field(default=__version__)
    target: str
    summary: ScanSummary
    skills: list[Skill]

    def has_failures(self, fail_on: str = "error") -> bool:
        """Check if any skill failed the threshold or if there are blocking findings."""
        return any(not s.is_passing(fail_on) for s in self.skills)

    def exit_code(self, fail_on: str = "error") -> int:
        """Return the standard CLI exit code based on findings."""
        return 1 if self.has_failures(fail_on) else 0
