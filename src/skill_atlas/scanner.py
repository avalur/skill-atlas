"""Scanner orchestrator coordinating discovery, evaluation, and reporting."""

from pathlib import Path

from skill_atlas import __version__
from skill_atlas.discovery.local import discover_local_skills
from skill_atlas.discovery.remote import discover_remote_skills, is_remote_target
from skill_atlas.models import ScanResult, ScanSummary, Severity
from skill_atlas.rules import RuleRegistry, create_default_registry


class Scanner:
    """Orchestrates discovery and static analysis of skills."""

    def __init__(
        self,
        rules_category: str = "all",
        ignored_rules: list[str] | None = None,
        fail_on: str = "error",
        registry: RuleRegistry | None = None,
    ) -> None:
        self.rules_category = rules_category.lower()
        self.ignored_rules = ignored_rules or []
        self.fail_on = fail_on.lower().strip()
        self.registry = registry or create_default_registry()

    def scan(self, target: str | Path) -> ScanResult:
        """Scan a target path or Git URL for AI Agent Skills."""
        target_str = str(target)

        # 1. Discover skills
        if is_remote_target(target_str):
            skills = discover_remote_skills(target_str)
        else:
            skills = discover_local_skills(Path(target_str))

        # 2. Evaluate rules on each skill
        error_count = 0
        warn_count = 0
        info_count = 0

        for skill in skills:
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

        # 3. Calculate summary metrics based on fail_on threshold
        total = len(skills)
        passed = sum(1 for s in skills if s.is_passing(self.fail_on))
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
        )

        return ScanResult(
            version=__version__,
            target=target_str,
            summary=summary,
            skills=skills,
        )
