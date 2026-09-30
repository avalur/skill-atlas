"""Static security auditing rules for AI Agent Skills."""

import re
from typing import NamedTuple

from skill_atlas.models import Finding, Severity, Skill
from skill_atlas.rules.base import Rule


class PatternDefinition(NamedTuple):
    description: str
    pattern: re.Pattern
    mask: bool = False


def _get_files_to_scan(skill: Skill) -> dict[str, str]:
    """Retrieve all text files to scan (SKILL.md and companion scripts)."""
    files: dict[str, str] = {}
    if skill.raw_content is not None:
        files["SKILL.md"] = skill.raw_content
    if skill.companion_contents:
        for path, text in skill.companion_contents.items():
            if path != "SKILL.md":
                files[path] = text
    return files


def _scan_files_for_patterns(
    skill: Skill,
    patterns: list[PatternDefinition],
    rule_id: str,
    severity: Severity,
    suggestion: str,
) -> list[Finding]:
    """Scan all skill text files line by line for regex matches and generate findings."""
    findings: list[Finding] = []
    files_to_scan = _get_files_to_scan(skill)

    for filename, content in files_to_scan.items():
        lines = content.splitlines()
        for line_idx, line in enumerate(lines, start=1):
            for pat_def in patterns:
                match = pat_def.pattern.search(line)
                if match:
                    matched_str = match.group(0)
                    if pat_def.mask:
                        display_match = (
                            matched_str[:4] + "..." + matched_str[-4:]
                            if len(matched_str) > 8
                            else "***"
                        )
                    else:
                        display_match = matched_str

                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=severity,
                            message=f"{pat_def.description}: '{display_match}'",
                            file=filename,
                            line=line_idx,
                            suggestion=suggestion,
                        )
                    )
    return findings


class HardcodedSecretRule(Rule):
    """SEC-001: Detected exposed secrets (OpenAI, AWS, GitHub tokens, private keys)."""

    id = "SEC-001"
    name = "Hardcoded Secret Detected"
    severity = Severity.ERROR
    category = "security"
    description = "Exposed secrets, tokens, or private keys detected in skill files"

    _PATTERNS = [
        PatternDefinition(
            "OpenAI/Anthropic API Key",
            re.compile(r"\b(sk-[a-zA-Z0-9_-]{20,}|sk-ant-[a-zA-Z0-9_-]{20,})\b"),
            mask=True,
        ),
        PatternDefinition(
            "AWS Access Key ID",
            re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
            mask=True,
        ),
        PatternDefinition(
            "GitHub Token",
            re.compile(r"\b(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}\b"),
            mask=True,
        ),
        PatternDefinition(
            "Slack Token",
            re.compile(r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,}\b"),
            mask=True,
        ),
        PatternDefinition(
            "Google API Key",
            re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"),
            mask=True,
        ),
        PatternDefinition(
            "Private Key Header",
            re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
            mask=False,
        ),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        return _scan_files_for_patterns(
            skill,
            self._PATTERNS,
            self.id,
            self.severity,
            "Move sensitive tokens and keys to environment variables",
        )


class DangerousCommandRule(Rule):
    """SEC-002: Usage of destructive shell commands."""

    id = "SEC-002"
    name = "Dangerous Shell Command"
    severity = Severity.ERROR
    category = "security"
    description = "Destructive or critical system modification commands detected"

    _PATTERNS = [
        PatternDefinition(
            "Destructive root deletion",
            re.compile(
                r"\b(sudo\s+)?rm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|-r\s+-f|-f\s+-r)\s+(--no-preserve-root\s+)?(/|~|\$HOME)(\*|/\*)?(\s|$|;|&|\|)"
            ),
        ),
        PatternDefinition(
            "Fork bomb pattern",
            re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"),
        ),
        PatternDefinition(
            "Filesystem format command",
            re.compile(r"\bmkfs(\.[a-z0-9]+)?\s+"),
        ),
        PatternDefinition(
            "Direct disk write",
            re.compile(r"\bdd\s+if=.*of=/dev/[sh]d[a-z]"),
        ),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        return _scan_files_for_patterns(
            skill,
            self._PATTERNS,
            self.id,
            self.severity,
            "Remove destructive system commands or replace with safe, non-root alternatives",
        )


class UnsafeNetworkExecutionRule(Rule):
    """SEC-003: Remote script execution without verification."""

    id = "SEC-003"
    name = "Unsafe Network Execution"
    severity = Severity.WARN
    category = "security"
    description = "Unverified pipe to shell from remote download (curl | bash, wget | sh)"

    _PATTERNS = [
        PatternDefinition(
            "Unsafe pipe to shell",
            re.compile(r"\b(curl|wget)\b[^\n|]+\|\s*(sudo\s+)?(ba|z)?sh\b"),
        ),
        PatternDefinition(
            "Unsafe process substitution",
            re.compile(r"\b(ba|z)?sh\s+<\s*\(\s*(curl|wget)\b"),
        ),
        PatternDefinition(
            "Unsafe subshell execution",
            re.compile(r"\b(ba|z)?sh\s+-c\s+[\"']\$\((curl|wget)\b"),
        ),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        return _scan_files_for_patterns(
            skill,
            self._PATTERNS,
            self.id,
            self.severity,
            "Download script, inspect or verify checksum before execution instead of piping directly to shell",
        )


class SensitivePathAccessRule(Rule):
    """SEC-004: Accessing sensitive filesystem paths."""

    id = "SEC-004"
    name = "Sensitive Path Access"
    severity = Severity.WARN
    category = "security"
    description = "Access to sensitive system or credential paths (/etc/shadow, ~/.ssh, ~/.aws)"

    _PATTERNS = [
        PatternDefinition(
            "Sensitive path access",
            re.compile(r"(/etc/shadow|/etc/passwd|~?/\.ssh(/|\b)|~?/\.aws(/|\b)|~?/\.gnupg(/|\b))"),
        ),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        return _scan_files_for_patterns(
            skill,
            self._PATTERNS,
            self.id,
            self.severity,
            "Avoid accessing sensitive user credentials or system authentication paths directly",
        )


class PromptInjectionRule(Rule):
    """SEC-005: Prompt override and safety bypass patterns."""

    id = "SEC-005"
    name = "Prompt Injection Risk"
    severity = Severity.WARN
    category = "security"
    description = "Prompt injection or instruction override patterns detected"

    _PATTERNS = [
        PatternDefinition(
            "Prompt injection pattern",
            re.compile(
                r"(?i)(ignore\s+(all\s+)?previous\s+instructions|disregard\s+(all\s+)?previous\s+instructions|bypass\s+(all\s+)?safety\s+(guidelines|filters|checks))"
            ),
        ),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        return _scan_files_for_patterns(
            skill,
            self._PATTERNS,
            self.id,
            self.severity,
            "Remove adversarial instruction override phrases",
        )
