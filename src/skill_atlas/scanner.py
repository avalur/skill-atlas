"""Scanner orchestrator coordinating discovery, evaluation, and reporting."""

import os
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
    Finding,
    ProgressCallback,
    ProgressEvent,
    ScanResult,
    ScanSummary,
    Severity,
    Skill,
    SkillOrigin,
    Stage,
    matches_query,
    parse_utc_timestamp,
)
from skill_atlas.rules import RuleRegistry, create_default_registry


def is_duplicate_candidate(s1: Skill, s2: Skill) -> bool:
    """Check if two skills represent duplicate copies of the same skill.

    Only mirror copies involving agent-config directories (.claude, .agents, .junie, etc.)
    are considered duplicates. Distinct product or standalone skills in different locations
    are kept separate. Skills across different repositories are never duplicates.
    """
    if s1.name != s2.name:
        return False
    # Cross-repository isolation: skills from different repositories are distinct entities
    if (s1.repo_name or "") != (s2.repo_name or ""):
        return False
    if (s1.repo_url or "") != (s2.repo_url or ""):
        return False
    if (
        s1.repo_root_dir is not None
        and s2.repo_root_dir is not None
        and s1.repo_root_dir != s2.repo_root_dir
    ):
        return False
    if (s1.origin == SkillOrigin.TEST_DATA) != (s2.origin == SkillOrigin.TEST_DATA):
        return False

    # Product skills in different directories (e.g. plugins) are distinct components
    if s1.origin == SkillOrigin.PRODUCT or s2.origin == SkillOrigin.PRODUCT:
        return False

    # Duplicates are mirror copies involving agent-config (e.g. .claude/skills/foo vs .agents/skills/foo)
    if s1.origin == SkillOrigin.AGENT_CONFIG or s2.origin == SkillOrigin.AGENT_CONFIG:
        return True

    return False


def deduplicate_skills(
    raw_skills: list[Skill], emit_fn: Callable[..., None] | None = None
) -> list[Skill]:
    """Group duplicate skills by name and configuration roots, picking the newest copy.

    Test-data skills are kept isolated and never merged with non-test skills.
    Distinct product skills (e.g. across plugins) and separate standalone skills remain independent.
    """
    clusters: list[list[Skill]] = []
    for s in raw_skills:
        matched = False
        for c in clusters:
            if is_duplicate_candidate(s, c[0]):
                c.append(s)
                matched = True
                break
        if not matched:
            clusters.append([s])

    deduped: list[Skill] = []
    num_with_duplicates = 0

    for members in clusters:
        if len(members) == 1:
            deduped.append(members[0])
            continue

        num_with_duplicates += 1
        # Sort members: lexicographical path first, then stable sort by newest UTC datetime
        members.sort(key=lambda s: s.path)
        members.sort(key=lambda s: parse_utc_timestamp(s.updated_date), reverse=True)

        primary = members[0]
        primary.duplicate_skills = members[1:]
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

    deduped.sort(key=lambda s: (s.repo_name or "", s.path))
    return deduped


def normalize_targets(
    targets: str | Path | list[str | Path] | tuple[str | Path, ...] | None = None,
    target: str | Path | list[str | Path] | tuple[str | Path, ...] | None = None,
) -> list[str]:
    """Normalize and deduplicate target paths or URLs, preserving declaration order."""
    raw_list: list[str | Path] = []
    if target is not None:
        if isinstance(target, (list, tuple)):
            raw_list.extend(target)
        else:
            raw_list.append(target)
    if targets is not None:
        if isinstance(targets, (list, tuple)):
            raw_list.extend(targets)
        else:
            raw_list.append(targets)

    if not raw_list:
        return ["."]

    normalized: list[str] = []
    seen: set[str] = set()

    for item in raw_list:
        s = str(item).strip()
        if not s:
            continue
        if is_remote_target(s):
            norm = s.rstrip("/")
            key = norm
        else:
            if s == ".":
                norm = "."
                key = "."
            else:
                norm = s.rstrip("/\\")
                if not norm:
                    norm = "/"
                try:
                    key = os.path.normpath(norm)
                except (ValueError, TypeError):
                    key = norm
        if key not in seen:
            seen.add(key)
            normalized.append(norm)

    return normalized if normalized else ["."]


def parse_targets_file(path: str | Path) -> list[str]:
    """Parse a targets file containing one target path or Git URL per line.

    Ignores empty lines, leading/trailing whitespace, and comments (lines starting with '#'
    or trailing inline comments preceded by ' #'). Raises FileNotFoundError if the file
    does not exist, and ValueError if no valid targets are found.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Targets file not found: '{path}'.")
    content = p.read_text(encoding="utf-8")
    targets: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if " #" in line:
            line = line.split(" #", 1)[0].strip()
        if line:
            targets.append(line)
    if not targets:
        raise ValueError(f"Targets file '{path}' contains no valid targets.")
    return targets


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
        targets: str | Path | list[str | Path] | tuple[str | Path, ...] | None = None,
        ref: str | None = None,
        *,
        target: str | Path | list[str | Path] | tuple[str | Path, ...] | None = None,
        query: str | None = None,
        include_test_data: bool | None = None,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        http_client: httpx.Client | None = None,
        gh_client: GitHubClient | None = None,
        discovery_only: bool = False,
    ) -> ScanResult:
        """Scan one or more target paths or Git URLs for AI Agent Skills."""
        normalized_targets = normalize_targets(targets=targets, target=target)
        t0 = time.time()
        effective_include_test_data = (
            self.include_test_data if include_test_data is None else include_test_data
        )
        has_remote = any(is_remote_target(t) for t in normalized_targets)
        effective_gh_client = gh_client or (GitHubClient() if has_remote else None)
        scan_warnings: list[str] = []

        def emit(
            stage: Stage,
            message: str,
            current: int | None = None,
            total: int | None = None,
            skill_path: str | None = None,
            target_index: int | None = None,
            target_total: int | None = None,
            target_name: str | None = None,
        ) -> None:
            if on_progress:
                rate_remaining = (
                    effective_gh_client.rate_limit_remaining if effective_gh_client else None
                )
                event = ProgressEvent(
                    stage=stage,
                    message=message,
                    current=current,
                    total=total,
                    skill_path=skill_path,
                    rate_limit_remaining=rate_remaining,
                    elapsed_ms=int((time.time() - t0) * 1000),
                    target_index=target_index,
                    target_total=target_total,
                    target_name=target_name,
                )
                on_progress(event)

        def check_cancel() -> None:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Scan cancelled by user")

        def make_target_progress(idx: int, name: str, prefix: str) -> ProgressCallback:
            def _progress(event: ProgressEvent) -> None:
                if event.target_index is None:
                    event.target_index = idx
                    event.target_total = total_targets
                    event.target_name = name
                    if total_targets > 1 and not event.message.startswith(prefix):
                        event.message = f"{prefix}{event.message}"
                if on_progress:
                    on_progress(event)

            return _progress

        def make_target_emit(idx: int, name: str, prefix: str) -> Callable[[Stage, str], None]:
            def _emit_fn(stage: Stage, msg: str) -> None:
                emit(
                    stage,
                    f"{prefix}{msg}",
                    target_index=idx,
                    target_total=total_targets,
                    target_name=name,
                )

            return _emit_fn

        try:
            # 1. Discover skills across all targets
            total_targets = len(normalized_targets)
            all_discovered_skills: list[Skill] = []

            for target_idx, target_str in enumerate(normalized_targets, start=1):
                check_cancel()
                target_prefix = f"[{target_idx}/{total_targets}] " if total_targets > 1 else ""

                if is_remote_target(target_str):
                    target_progress = make_target_progress(target_idx, target_str, target_prefix)
                    raw_skills = discover_remote_skills(
                        url=target_str,
                        ref=ref,
                        gh_client=effective_gh_client,
                        http_client=http_client,
                        on_progress=target_progress if on_progress else None,
                        cancel_event=cancel_event,
                        discovery_only=discovery_only,
                        warnings=scan_warnings,
                    )
                else:
                    emit(
                        Stage.VALIDATE,
                        f"{target_prefix}Validating local path {target_str}...",
                        target_index=target_idx,
                        target_total=total_targets,
                        target_name=target_str,
                    )
                    emit(
                        Stage.DISCOVER,
                        f"{target_prefix}Searching for skills in {target_str}...",
                        target_index=target_idx,
                        target_total=total_targets,
                        target_name=target_str,
                    )
                    raw_skills = discover_local_skills(Path(target_str))

                check_cancel()

                # Deduplicate within this target boundary (cross-repository isolation)
                target_emit_fn = make_target_emit(target_idx, target_str, target_prefix)
                deduped_target_skills = deduplicate_skills(raw_skills, emit_fn=target_emit_fn)
                all_discovered_skills.extend(deduped_target_skills)

            # 2. Audit-scope filtering by query before rule evaluation
            clean_query = query.strip() if (query and query.strip()) else None
            if clean_query:
                skills = [s for s in all_discovered_skills if matches_query(s, clean_query)]
            else:
                skills = all_discovered_skills

            # Deterministic sorting across repositories: repo_name ascending, then path ascending
            skills.sort(key=lambda s: (s.repo_name or "", s.path))

            # 3. Evaluate rules on each unique displayed skill (and audit all duplicates)
            error_count = 0
            warn_count = 0
            info_count = 0

            if discovery_only:
                for skill in skills:
                    skill.passing = True
            else:
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

                    # Audit all duplicate copies as well (C2 fix)
                    for other in getattr(skill, "duplicate_skills", []):
                        check_cancel()
                        self.registry.evaluate(
                            other,
                            category=self.rules_category,
                            ignored_ids=self.ignored_rules,
                        )
                        # Record findings on the DuplicateRef
                        for d_ref in skill.duplicates:
                            if d_ref.path == other.path:
                                d_ref.findings = list(other.findings)
                                break
                        # Propagate duplicate findings to the shown skill with explicit copy path
                        for f in other.findings:
                            loc = (
                                f"{other.path}/{f.file}"
                                if not f.file.startswith(other.path)
                                else f.file
                            )
                            skill.add_finding(
                                Finding(
                                    rule_id=f.rule_id,
                                    severity=f.severity,
                                    message=f"[In duplicate copy '{other.path}'] {f.message}",
                                    file=loc,
                                    line=f.line,
                                    suggestion=f.suggestion,
                                )
                            )
                        other.companion_contents.clear()

                    # Free companion contents from memory
                    skill.companion_contents.clear()

                    # Count findings
                    for f in skill.findings:
                        if f.severity == Severity.ERROR:
                            error_count += 1
                        elif f.severity == Severity.WARN:
                            warn_count += 1
                        elif f.severity == Severity.INFO:
                            info_count += 1

                    skill.passing = skill.is_passing(
                        self.fail_on, include_test_data=effective_include_test_data
                    )

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

            primary_target = normalized_targets[0] if normalized_targets else ""

            return ScanResult(
                version=__version__,
                target=primary_target,
                targets=normalized_targets,
                query=clean_query,
                summary=summary,
                skills=skills,
                warnings=scan_warnings,
            )
        except Exception as err:
            emit(Stage.ERROR, str(err))
            raise
