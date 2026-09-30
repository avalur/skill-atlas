"""Data models for Skill Atlas."""

import re
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from skill_atlas import __version__


class Severity(StrEnum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


class SkillOrigin(StrEnum):
    AGENT_CONFIG = "agent-config"
    PRODUCT = "product"
    TEST_DATA = "test-data"
    STANDALONE = "standalone"


def classify_origin(path: str) -> SkillOrigin:
    """Classify the origin of a skill based on its filesystem path.

    Matches path segments in order:
    1. test data: test, tests, testData, testdata, fixtures, src/test/, src/*Test/, test-resources
    2. agent config: .claude, .agents, .junie, .cursor, .codex, .github/skills
    3. product: src/main/resources, resources/, plugins/*/, languages/*/
    4. standalone: everything else
    """
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.split("/")

    # 1. Test data check
    for part in parts:
        lower_part = part.lower()
        if lower_part in {"test", "tests", "testdata", "fixtures", "test-resources"}:
            return SkillOrigin.TEST_DATA

    if re.search(r"(^|/)(src/[^/]*test[^/]*|testData|test-data)(/|$)", normalized, re.IGNORECASE):
        return SkillOrigin.TEST_DATA

    # 2. Agent config check
    for part in parts:
        if part in {".claude", ".agents", ".junie", ".cursor", ".codex"}:
            return SkillOrigin.AGENT_CONFIG
    if ".github/skills" in normalized or normalized.startswith(".github/skills"):
        return SkillOrigin.AGENT_CONFIG

    # 3. Product check
    if re.search(
        r"(^|/)(src/main/resources|resources|plugins/[^/]+|languages/[^/]+)(/|$)", normalized
    ):
        return SkillOrigin.PRODUCT

    # 4. Standalone fallback
    return SkillOrigin.STANDALONE


class DuplicateRef(BaseModel):
    path: str
    updated_commit: str | None = None
    updated_date: str | None = None
    identical: bool = True
    origin: SkillOrigin | None = None


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
    updated_commit: str | None = None
    updated_date: str | None = None
    updated_source: str = "git"  # "git" or "mtime"
    origin: SkillOrigin = SkillOrigin.STANDALONE
    duplicates: list[DuplicateRef] = Field(default_factory=list)
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
    content_hash: str | None = Field(default=None, repr=False, exclude=True)

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)
        if finding.severity == Severity.ERROR:
            self.valid = False

    def is_passing(self, fail_on: str = "error", include_test_data: bool = False) -> bool:
        """Check whether the skill passes the given fail-on severity threshold."""
        if self.origin == SkillOrigin.TEST_DATA and not include_test_data:
            return True
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
    by_origin: dict[str, int] = Field(
        default_factory=lambda: {
            "agent-config": 0,
            "product": 0,
            "standalone": 0,
            "test-data": 0,
        }
    )


class ScanResult(BaseModel):
    version: str = Field(default=__version__)
    target: str
    summary: ScanSummary
    skills: list[Skill]

    def has_failures(self, fail_on: str = "error", include_test_data: bool = False) -> bool:
        """Check if any skill failed the threshold or if there are blocking findings."""
        return any(not s.is_passing(fail_on, include_test_data) for s in self.skills)

    def exit_code(self, fail_on: str = "error", include_test_data: bool = False) -> int:
        """Return the standard CLI exit code based on findings."""
        return 1 if self.has_failures(fail_on, include_test_data) else 0


class Stage(StrEnum):
    VALIDATE = "validate"
    FETCH = "fetch"
    DISCOVER = "discover"
    DOWNLOAD = "download"
    PROVENANCE = "provenance"
    DEDUPE = "dedupe"
    RULES = "rules"
    REPORT = "report"
    DONE = "done"
    ERROR = "error"


class ProgressEvent(BaseModel):
    stage: Stage
    message: str
    current: int | None = None
    total: int | None = None
    skill_path: str | None = None
    rate_limit_remaining: int | None = None
    elapsed_ms: int = 0


ProgressCallback = Callable[[ProgressEvent], None]
