"""Scanner orchestrator coordinating discovery, evaluation, and reporting."""

import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from skill_atlas import __version__
from skill_atlas.discovery.local import discover_local_skills
from skill_atlas.discovery.remote import discover_remote_skills, is_remote_target
from skill_atlas.git.github import GitHubClient
from skill_atlas.models import (
    DuplicateRef,
    ProgressCallback,
    ProgressEvent,
    ScanResult,
    ScanSummary,
    Severity,
    Skill,
    SkillOrigin,
    Stage,
)
from skill_atlas.rules import RuleRegistry, create_default_registry


def deduplicate_skills(
    raw_skills: list[Skill], emit_fn: Callable[..., None] | None = None
) -> list[Skill]:
    """Group duplicate skills by name, picking the newest copy.

    Test-data skills are kept isolated and never merged with non-test skills.
    """
    groups: dict[tuple[bool, str], list[Skill]] = {}
    for s in raw_skills:
        key = (s.origin == SkillOrigin.TEST_DATA, s.name)
        groups.setdefault(key, []).append(s)

    deduped: list[Skill] = []
    num_with_duplicates = 0

    for _key, members in groups.items():
        if len(members) == 1:
            deduped.append(members[0])
            continue

        num_with_duplicates += 1
        # Sort members: lexicographical path first, then stable sort by newest updated_date
        members.sort(key=lambda s: s.path)
        members.sort(key=lambda s: s.updated_date or "", reverse=True)

        primary = members[0]
        duplicates_list: list[DuplicateRef] = []

        for other in members[1:]:
            identical = (
                primary.content_hash is not None
                and other.content_hash is not None
                and primary.content_hash == other.content_hash
            )
            duplicates_list.append(
                DuplicateRef(
                    path=other.path,
                    updated_commit=other.updated_commit,
                    updated_date=other.updated_date,
                    identical=identical,
                    origin=other.origin,
                )
            )

        primary.duplicates = duplicates_list
        deduped.append(primary)

    if emit_fn and num_with_duplicates > 0:
        emit_fn(
            Stage.DEDUPE,
            f"{num_with_duplicates} skill(s) have duplicates; showing the newest copy",
        )

    deduped.sort(key=lambda s: s.path)
    return deduped


class Scanner:
    """Orchestrates discovery and static analysis of skills."""

    def __init__(
        self,
        rules_category: str = "all",
        ignored_rules: list[str] | None = None,
        fail_on: str = "error",
        include_test_data: bool = False,
        registry: RuleRegistry | None = None,
    ) -> None:
        self.rules_category = rules_category.lower()
        self.ignored_rules = ignored_rules or []
        self.fail_on = fail_on.lower().strip()
        self.include_test_data = include_test_data
        self.registry = registry or create_default_registry()

    def scan(
        self,
        target: str | Path,
        ref: str | None = None,
        include_test_data: bool | None = None,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        http_client: httpx.Client | None = None,
        gh_client: GitHubClient | None = None,
    ) -> ScanResult:
        """Scan a target path or Git URL for AI Agent Skills."""
        target_str = str(target)
        t0 = time.time()
        effective_include_test_data = (
            self.include_test_data if include_test_data is None else include_test_data
        )

        def emit(
            stage: Stage,
            message: str,
            current: int | None = None,
            total: int | None = None,
            skill_path: str | None = None,
        ) -> None:
            if on_progress:
                rate_remaining = gh_client.rate_limit_remaining if gh_client else None
                event = ProgressEvent(
                    stage=stage,
                    message=message,
                    current=current,
                    total=total,
                    skill_path=skill_path,
                    rate_limit_remaining=rate_remaining,
                    elapsed_ms=int((time.time() - t0) * 1000),
                )
                on_progress(event)

        def check_cancel() -> None:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Scan cancelled by user")

        try:
            # 1. Discover skills
            check_cancel()
            if is_remote_target(target_str):
                raw_skills = discover_remote_skills(
                    url=target_str,
                    ref=ref,
                    gh_client=gh_client,
                    http_client=http_client,
                    on_progress=on_progress,
                    cancel_event=cancel_event,
                )
            else:
                emit(Stage.VALIDATE, f"Validating local path {target_str}...")
                emit(Stage.DISCOVER, f"Searching for skills in {target_str}...")
                raw_skills = discover_local_skills(Path(target_str))

            check_cancel()

            # 2. Deduplicate duplicate skills
            skills = deduplicate_skills(raw_skills, emit_fn=emit)

            # 3. Evaluate rules on each unique displayed skill
            error_count = 0
            warn_count = 0
            info_count = 0

            for idx, skill in enumerate(skills, start=1):
                check_cancel()
                emit(
                    Stage.RULES,
                    f"Running rules on {skill.path} ({idx}/{len(skills)})",
                    current=idx,
                    total=len(skills),
                    skill_path=skill.path,
                )

                self.registry.evaluate(
                    skill,
                    category=self.rules_category,
                    ignored_ids=self.ignored_rules,
                )

                # Count findings
                for f in skill.findings:
                    if f.severity == Severity.ERROR:
                        error_count += 1
                    elif f.severity == Severity.WARN:
                        warn_count += 1
                    elif f.severity == Severity.INFO:
                        info_count += 1

            # 4. Calculate summary metrics by origin and pass/fail status
            check_cancel()
            emit(Stage.REPORT, "Building final report...")

            by_origin: dict[str, int] = {
                "agent-config": 0,
                "product": 0,
                "standalone": 0,
                "test-data": 0,
            }
            for s in skills:
                by_origin[s.origin.value] = by_origin.get(s.origin.value, 0) + 1

            total = len(skills)
            passed = sum(
                1
                for s in skills
                if s.is_passing(self.fail_on, include_test_data=effective_include_test_data)
            )
            failed = total - passed

            summary = ScanSummary(
                total_skills=total,
                passed=passed,
                failed=failed,
                findings_count={
                    "error": error_count,
                    "warn": warn_count,
                    "info": info_count,
                },
                by_origin=by_origin,
            )

            emit(
                Stage.DONE,
                f"Done: {total} skill(s), {failed} failed, {error_count + warn_count + info_count} finding(s)",
            )

            return ScanResult(
                version=__version__,
                target=target_str,
                summary=summary,
                skills=skills,
            )
        except Exception as err:
            emit(Stage.ERROR, str(err))
            raise
