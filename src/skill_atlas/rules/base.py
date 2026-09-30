"""Base classes and registry for validation and security rules."""

from abc import ABC, abstractmethod

from skill_atlas.models import Finding, Severity, Skill


class Rule(ABC):
    """Abstract base class for all Skill Atlas inspection rules."""

    id: str
    name: str
    severity: Severity
    category: str  # "schema" or "security"
    description: str

    @abstractmethod
    def check(self, skill: Skill) -> list[Finding]:
        """Inspect a skill and return any findings."""


class RuleRegistry:
    """Registry managing rules and their application."""

    def __init__(self) -> None:
        self._rules: list[Rule] = []

    def register(self, rule: Rule) -> None:
        self._rules.append(rule)

    def get_rules(
        self,
        category: str = "all",
        ignored_ids: list[str] | None = None,
    ) -> list[Rule]:
        ignored = set(i.upper() for i in (ignored_ids or []))
        rules = self._rules

        if category != "all":
            rules = [r for r in rules if r.category == category]

        return [r for r in rules if r.id.upper() not in ignored]

    def evaluate(
        self,
        skill: Skill,
        category: str = "all",
        ignored_ids: list[str] | None = None,
    ) -> list[Finding]:
        findings: list[Finding] = []
        active_rules = self.get_rules(category=category, ignored_ids=ignored_ids)

        for rule in active_rules:
            try:
                detected = rule.check(skill)
                for f in detected:
                    skill.add_finding(f)
                    findings.append(f)
            except Exception as err:
                internal_finding = Finding(
                    rule_id=rule.id,
                    severity=Severity.ERROR,
                    message=f"Internal rule error: {err}",
                    file="SKILL.md",
                    suggestion="Check rule implementation or report issue",
                )
                skill.add_finding(internal_finding)
                findings.append(internal_finding)

        return findings
