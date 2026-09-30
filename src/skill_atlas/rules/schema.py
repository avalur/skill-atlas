"""Schema and structural validation rules for AI Agent Skills."""

import posixpath
import re
from pathlib import Path

from skill_atlas.models import Finding, Severity, Skill
from skill_atlas.rules.base import Rule


class MissingManifestRule(Rule):
    """SCH-001: The SKILL.md file is missing in the discovered skill directory."""

    id = "SCH-001"
    name = "Missing Manifest"
    severity = Severity.ERROR
    category = "schema"
    description = "The SKILL.md file is missing in the discovered skill directory"

    def check(self, skill: Skill) -> list[Finding]:
        if skill.raw_content is None:
            return [
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message="SKILL.md manifest is missing or could not be loaded",
                    file=f"{skill.path}/SKILL.md",
                    suggestion="Create a valid SKILL.md file with YAML frontmatter in the skill directory",
                )
            ]
        return []


class InvalidFrontmatterRule(Rule):
    """SCH-002: YAML frontmatter is corrupted or cannot be parsed."""

    id = "SCH-002"
    name = "Invalid Frontmatter"
    severity = Severity.ERROR
    category = "schema"
    description = "YAML frontmatter is corrupted or cannot be parsed"

    def check(self, skill: Skill) -> list[Finding]:
        if skill.parse_error:
            return [
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"Invalid YAML frontmatter: {skill.parse_error}",
                    file="SKILL.md",
                    suggestion="Ensure YAML frontmatter is properly enclosed in '---' and contains valid YAML syntax",
                )
            ]
        return []


class MissingRequiredFieldRule(Rule):
    """SCH-003: Missing required frontmatter field (name or description)."""

    id = "SCH-003"
    name = "Missing Required Field"
    severity = Severity.ERROR
    category = "schema"
    description = "Missing required frontmatter field ('name' or 'description')"

    def check(self, skill: Skill) -> list[Finding]:
        findings: list[Finding] = []
        name = skill.frontmatter.get("name")
        if not name or not str(name).strip():
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message="Missing required field 'name' in frontmatter",
                    file="SKILL.md",
                    suggestion="Add a unique 'name' field to the YAML frontmatter",
                )
            )

        description = skill.frontmatter.get("description")
        if not description or not str(description).strip():
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message="Missing required field 'description' in frontmatter",
                    file="SKILL.md",
                    suggestion="Add a clear 'description' field explaining the skill's purpose to YAML frontmatter",
                )
            )
        return findings


class InvalidNameFormatRule(Rule):
    """SCH-004: Skill name contains invalid characters."""

    id = "SCH-004"
    name = "Invalid Name Format"
    severity = Severity.WARN
    category = "schema"
    description = "Skill name contains invalid characters (recommended: '^[a-z0-9_-]+$')"

    _PATTERN = re.compile(r"^[a-z0-9_-]+$")

    def check(self, skill: Skill) -> list[Finding]:
        if skill.name and not self._PATTERN.match(skill.name):
            return [
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"Skill name '{skill.name}' does not match recommended pattern '^[a-z0-9_-]+$'",
                    file="SKILL.md",
                    suggestion="Rename skill to use only lowercase alphanumeric characters, hyphens, and underscores",
                )
            ]
        return []


class ShortDescriptionRule(Rule):
    """SCH-005: Description is under 20 characters."""

    id = "SCH-005"
    name = "Short Description"
    severity = Severity.WARN
    category = "schema"
    description = "Description length is under 20 characters (insufficient for agent routing)"

    def check(self, skill: Skill) -> list[Finding]:
        # Only check if description is present; SCH-003 catches missing description
        if skill.description and len(skill.description.strip()) < 20:
            return [
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=(
                        f"Skill description is too short ({len(skill.description.strip())} characters). "
                        "Minimum recommended is 20 characters."
                    ),
                    file="SKILL.md",
                    suggestion="Expand the description to help AI agents accurately route tasks to this skill",
                )
            ]
        return []


class BrokenLinkReferenceRule(Rule):
    """SCH-006: SKILL.md references local files or scripts that do not exist on disk."""

    id = "SCH-006"
    name = "Broken Link Reference"
    severity = Severity.ERROR
    category = "schema"
    description = "SKILL.md references local files or scripts that do not exist on disk"

    def check(self, skill: Skill) -> list[Finding]:
        findings: list[Finding] = []
        if not skill.referenced_files:
            return findings

        # Build lookup set for companion files in skill directory
        available_set: set[str] = set()
        for f in skill.available_files:
            clean = f.lstrip("./")
            available_set.add(clean)
            parts = clean.split("/")
            for i in range(1, len(parts)):
                available_set.add("/".join(parts[:i]))

        # Build lookup set for all repository files (if inside Git repository)
        repo_files_set: set[str] = set()
        for f in skill.repo_files:
            clean = f.lstrip("./")
            repo_files_set.add(clean)
            parts = clean.split("/")
            for i in range(1, len(parts)):
                repo_files_set.add("/".join(parts[:i]))

        base_disk = Path(skill.base_dir).resolve() if skill.base_dir else None
        repo_disk = Path(skill.repo_root_dir).resolve() if skill.repo_root_dir else None

        for ref in skill.referenced_files:
            clean_ref = ref.strip()
            if not clean_ref:
                continue

            found = False

            # 1. Root-relative link: /path/to/file (relative to repository root)
            if clean_ref.startswith("/"):
                norm_root_path = posixpath.normpath(clean_ref.lstrip("/"))
                if norm_root_path in repo_files_set:
                    found = True
                elif repo_disk:
                    target_disk = (repo_disk / norm_root_path).resolve()
                    if target_disk.is_relative_to(repo_disk) and target_disk.exists():
                        found = True

            # 2. Local skill file (e.g. scripts/run.sh, ./scripts/run.sh)
            if not found:
                norm_local = posixpath.normpath(clean_ref.lstrip("./"))
                if norm_local in available_set:
                    found = True
                elif base_disk:
                    target_disk = (base_disk / clean_ref).resolve()
                    if target_disk.exists():
                        if repo_disk:
                            if target_disk.is_relative_to(repo_disk):
                                found = True
                        else:
                            found = True

            # 3. Path relative to skill location within repository (e.g. ../../../compiler/...)
            if not found:
                skill_base = posixpath.normpath(skill.path.strip("/"))
                if skill_base == "." or not skill_base:
                    resolved_repo_path = posixpath.normpath(clean_ref)
                else:
                    resolved_repo_path = posixpath.normpath(posixpath.join(skill_base, clean_ref))

                if not resolved_repo_path.startswith(".."):
                    resolved_repo_path = resolved_repo_path.lstrip("./")
                    if resolved_repo_path in repo_files_set:
                        found = True
                    elif repo_disk:
                        target_disk = (repo_disk / resolved_repo_path).resolve()
                        if target_disk.is_relative_to(repo_disk) and target_disk.exists():
                            found = True

            if not found:
                findings.append(
                    Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=f"Referenced file or script '{ref}' not found in skill or repository",
                        file="SKILL.md",
                        suggestion=f"Ensure '{ref}' exists in the skill directory or repository, or remove broken link",
                    )
                )

        return findings
