"""Discovery module for local and remote skills."""

from skill_atlas.discovery.local import discover_local_skills
from skill_atlas.discovery.remote import discover_remote_skills, is_remote_target

__all__ = [
    "discover_local_skills",
    "discover_remote_skills",
    "is_remote_target",
]
