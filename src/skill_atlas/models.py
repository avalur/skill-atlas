"""Data models for Skill Atlas."""

from __future__ import annotations

import datetime
import hashlib
import re
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from skill_atlas import __version__

BINARY_EXTENSIONS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".bmp",
    ".tiff",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".jar",
    ".war",
    ".ear",
    ".class",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".dat",
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".flv",
    ".webm",
}


def parse_utc_timestamp(dt_str: str | None) -> datetime.datetime:
    """Parse ISO 8601 date string and convert to timezone-aware UTC datetime."""
    if not dt_str:
        return datetime.datetime.min.replace(tzinfo=datetime.UTC)
    try:
        cleaned = dt_str.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.UTC)
        return dt.astimezone(datetime.UTC)
    except (ValueError, TypeError):
        return datetime.datetime.min.replace(tzinfo=datetime.UTC)


def calculate_content_hash(companion_contents: dict[str, str]) -> str:
    """Calculate a deterministic sha256 hash of all text contents in the skill."""
    hasher = hashlib.sha256()
    for rel_p in sorted(companion_contents.keys()):
        hasher.update(rel_p.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(companion_contents[rel_p].encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


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

    if re.search(
        r"(^|/)(src/[^/]*test[^/]*|testData|test-data|integration-tests?)(/|$)",
        normalized,
        re.IGNORECASE,
    ):
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


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    file: str = "SKILL.md"
    line: int | None = None
    suggestion: str | None = None


class DuplicateRef(BaseModel):
    path: str
    updated_commit: str | None = None
    updated_date: str | None = None
    identical: bool = True
    origin: SkillOrigin | None = None
    findings: list[Finding] = Field(default_factory=list)


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
    passing: bool | None = None
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
    duplicate_skills: list[Any] = Field(default_factory=list, repr=False, exclude=True)

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


def matches_query(skill: Skill, query: str) -> bool:
    """Check if a skill matches a case-insensitive search query.

    Matches query substring against skill name, description, path,
    repo_name, and declared tags.
    """
    q = query.strip().lower()
    if not q:
        return True
    tokens = [
        (skill.name or "").lower(),
        (skill.description or "").lower(),
        (skill.path or "").lower(),
        (skill.repo_name or "").lower(),
        *(str(t).lower() for t in (skill.tags or []) if t),
    ]
    return any(q in token for token in tokens)


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
    target: str = ""
    targets: list[str] = Field(default_factory=list)
    query: str | None = None
    summary: ScanSummary
    skills: list[Skill]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_targets(self) -> Self:
        if self.targets and not self.target:
            self.target = self.targets[0]
        elif self.target and not self.targets:
            self.targets = [self.target]
        return self

    def has_failures(self, fail_on: str = "error", include_test_data: bool = False) -> bool:
        """Check if any skill failed the threshold or if there are blocking findings."""
        if any(not s.is_passing(fail_on, include_test_data) for s in self.skills):
            return True
        if fail_on.lower().strip() == "warn" and bool(self.warnings):
            return True
        return False

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
    target_index: int | None = None
    target_total: int | None = None
    target_name: str | None = None


ProgressCallback = Callable[[ProgressEvent], None]
