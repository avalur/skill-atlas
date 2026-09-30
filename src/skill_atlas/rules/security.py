"""Static security auditing rules for AI Agent Skills."""

import re

from skill_atlas.models import Finding, Severity, Skill
from skill_atlas.rules.base import Rule


def _scan_lines_for_patterns(
    content: str,
    patterns: list[tuple[str, re.Pattern]],
    filename: str,
    rule_id: str,
    severity: Severity,
    suggestion: str,
) -> list[Finding]:
    """Scan content line by line for regex matches and generate findings with line numbers."""
    findings: list[Finding] = []
    lines = content.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        for desc, pattern in patterns:
            match = pattern.search(line)
            if match:
                matched_str = match.group(0)
                # Obfuscate secret if secret rule
                if "Secret" in desc or "Token" in desc or "Key" in desc:
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
                        message=f"{desc}: '{display_match}'",
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
        ("OpenAI API Key", re.compile(r"\bsk-[a-zA-Z0-9_-]{20,}\b")),
        ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("GitHub Personal Token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b")),
        ("Private Key Header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
        ("Slack Token", re.compile(r"\bxox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,}\b")),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        findings: list[Finding] = []
        if skill.raw_content:
            findings.extend(
                _scan_lines_for_patterns(
                    skill.raw_content,
                    self._PATTERNS,
                    "SKILL.md",
                    self.id,
                    self.severity,
                    "Move sensitive tokens and keys to environment variables",
                )
            )
        return findings


class DangerousCommandRule(Rule):
    """SEC-002: Usage of destructive shell commands."""

    id = "SEC-002"
    name = "Dangerous Shell Command"
    severity = Severity.ERROR
    category = "security"
    description = "Destructive or critical system modification commands detected"

    _PATTERNS = [
        (
            "Destructive root deletion",
            re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+([/~]|\$HOME)(?:\s|$|;)"),
        ),
        ("Fork bomb pattern", re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:")),
        ("Filesystem format command", re.compile(r"\bmkfs(\.[a-z0-9]+)?\s+")),
        ("Direct disk write", re.compile(r"\bdd\s+if=.*of=/dev/[sh]d[a-z]")),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        findings: list[Finding] = []
        if skill.raw_content:
            findings.extend(
                _scan_lines_for_patterns(
                    skill.raw_content,
                    self._PATTERNS,
                    "SKILL.md",
                    self.id,
                    self.severity,
                    "Remove destructive system commands or replace with safe, non-root alternatives",
                )
            )
        return findings


class UnsafeNetworkExecutionRule(Rule):
    """SEC-003: Remote script execution without verification."""

    id = "SEC-003"
    name = "Unsafe Network Execution"
    severity = Severity.WARN
    category = "security"
    description = "Unverified pipe to shell from remote download (curl | bash, wget | sh)"

    _PATTERNS = [
        ("Unsafe pipe to shell", re.compile(r"(curl|wget)\s+[^|\n]+\|\s*(ba|z)?sh")),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        findings: list[Finding] = []
        if skill.raw_content:
            findings.extend(
                _scan_lines_for_patterns(
                    skill.raw_content,
                    self._PATTERNS,
                    "SKILL.md",
                    self.id,
                    self.severity,
                    "Download script, inspect or verify checksum before execution instead of piping directly to shell",
                )
            )
        return findings


class SensitivePathAccessRule(Rule):
    """SEC-004: Accessing sensitive filesystem paths."""

    id = "SEC-004"
    name = "Sensitive Path Access"
    severity = Severity.WARN
    category = "security"
    description = "Access to sensitive system or credential paths (/etc/shadow, ~/.ssh, ~/.aws)"

    _PATTERNS = [
        (
            "Sensitive path access",
            re.compile(r"(/etc/shadow|/etc/passwd|~?/\.ssh/|~?/\.aws/|~?/\.gnupg/)"),
        ),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        findings: list[Finding] = []
        if skill.raw_content:
            findings.extend(
                _scan_lines_for_patterns(
                    skill.raw_content,
                    self._PATTERNS,
                    "SKILL.md",
                    self.id,
                    self.severity,
                    "Avoid accessing sensitive user credentials or system authentication paths directly",
                )
            )
        return findings


class PromptInjectionRule(Rule):
    """SEC-005: Prompt override and safety bypass patterns."""

    id = "SEC-005"
    name = "Prompt Injection Risk"
    severity = Severity.WARN
    category = "security"
    description = "Prompt injection or instruction override patterns detected"

    _PATTERNS = [
        (
            "Prompt injection pattern",
            re.compile(
                r"(?i)(ignore\s+(all\s+)?previous\s+instructions|disregard\s+(all\s+)?previous\s+instructions|bypass\s+(all\s+)?safety\s+(guidelines|filters|checks))"
            ),
        ),
    ]

    def check(self, skill: Skill) -> list[Finding]:
        findings: list[Finding] = []
        if skill.raw_content:
            findings.extend(
                _scan_lines_for_patterns(
                    skill.raw_content,
                    self._PATTERNS,
                    "SKILL.md",
                    self.id,
                    self.severity,
                    "Remove adversarial instruction override phrases",
                )
            )
        return findings
