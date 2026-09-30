"""Discovery and layout validation rules for AI Agent Skills."""

from skill_atlas.models import Finding, Severity, Skill
from skill_atlas.rules.base import Rule


class StaleDuplicateRule(Rule):
    """DSC-001: Duplicate copies of skill differ in content."""

    id = "DSC-001"
    name = "Stale Duplicate"
    severity = Severity.WARN
    category = "discovery"
    description = (
        "Duplicate copies of the skill differ; showing the newest copy while older copy is stale"
    )

    def check(self, skill: Skill) -> list[Finding]:
        if not skill.duplicates:
            return []

        stale_copies = [d for d in skill.duplicates if not d.identical]
        if not stale_copies:
            return []

        total_copies = len(skill.duplicates) + 1
        stale_desc = []
        for d in stale_copies:
            date_info = f" ({d.updated_date})" if d.updated_date else ""
            stale_desc.append(f"{d.path}{date_info}")

        shown_date_info = f" (updated {skill.updated_date})" if skill.updated_date else ""
        msg = (
            f"{total_copies} copies of '{skill.name}' differ; "
            f"showing {skill.path}{shown_date_info}, "
            f"{', '.join(stale_desc)} is older or differs"
        )

        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message=msg,
                file="SKILL.md",
                suggestion="Sync or remove the stale copy of the skill",
            )
        ]
