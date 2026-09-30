"""Rules module for Skill Atlas."""

from skill_atlas.rules.base import Rule, RuleRegistry
from skill_atlas.rules.discovery import StaleDuplicateRule
from skill_atlas.rules.schema import (
    BrokenLinkReferenceRule,
    InvalidFrontmatterRule,
    InvalidNameFormatRule,
    MissingManifestRule,
    MissingRequiredFieldRule,
    ShortDescriptionRule,
)
from skill_atlas.rules.security import (
    DangerousCommandRule,
    HardcodedSecretRule,
    PromptInjectionRule,
    SensitivePathAccessRule,
    UnsafeNetworkExecutionRule,
)


def create_default_registry() -> RuleRegistry:
    """Create and configure a RuleRegistry with all built-in rules."""
    registry = RuleRegistry()

    # Schema rules (SCH-001 through SCH-006)
    registry.register(MissingManifestRule())
    registry.register(InvalidFrontmatterRule())
    registry.register(MissingRequiredFieldRule())
    registry.register(InvalidNameFormatRule())
    registry.register(ShortDescriptionRule())
    registry.register(BrokenLinkReferenceRule())

    # Security rules (SEC-001 through SEC-005)
    registry.register(HardcodedSecretRule())
    registry.register(DangerousCommandRule())
    registry.register(UnsafeNetworkExecutionRule())
    registry.register(SensitivePathAccessRule())
    registry.register(PromptInjectionRule())

    # Discovery rules (DSC-001)
    registry.register(StaleDuplicateRule())

    return registry


__all__ = [
    "BrokenLinkReferenceRule",
    "DangerousCommandRule",
    "HardcodedSecretRule",
    "InvalidFrontmatterRule",
    "InvalidNameFormatRule",
    "MissingManifestRule",
    "MissingRequiredFieldRule",
    "PromptInjectionRule",
    "Rule",
    "RuleRegistry",
    "SensitivePathAccessRule",
    "ShortDescriptionRule",
    "StaleDuplicateRule",
    "UnsafeNetworkExecutionRule",
    "create_default_registry",
]
