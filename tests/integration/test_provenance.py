"""Integration tests for skill provenance and update history tracking."""

from pathlib import Path

import httpx

from skill_atlas.git.client import get_directory_last_commit, get_file_provenance
from skill_atlas.git.github import GitHubClient
from tests.conftest import CommitDef, create_fake_github_transport, make_repo


def test_local_provenance_add_and_update(tmp_path: Path):
    """File provenance retains oldest commit while directory update tracks newest commit."""
    repo = make_repo(
        tmp_path / "prov_repo",
        commits=[
            CommitDef(
                message="Initial addition of skill",
                files={".claude/skills/demo/SKILL.md": "---\nname: demo\n---\n"},
                date="2026-01-10T10:00:00Z",
            ),
            CommitDef(
                message="Update helper script in skill",
                files={".claude/skills/demo/scripts/helper.sh": "#!/bin/bash\necho 1\n"},
                date="2026-06-20T14:30:00Z",
            ),
        ],
    )

    first_sha, first_date = get_file_provenance(repo, ".claude/skills/demo/SKILL.md")
    assert first_sha is not None
    assert "2026-01-10" in (first_date or "")

    last_sha, last_date = get_directory_last_commit(repo, ".claude/skills/demo")
    assert last_sha is not None
    assert "2026-06-20" in (last_date or "")
    assert first_sha != last_sha


def test_remote_provenance_with_pagination():
    """Remote GitHub provenance retrieves newest commit from page 1 and oldest from last page."""
    fake_commits = [
        {
            "sha": "newest_commit_sha",
            "commit": {
                "author": {"date": "2026-09-20T10:00:00Z"},
                "committer": {"date": "2026-09-20T10:00:00Z"},
                "message": "Latest update",
            },
        },
        {
            "sha": "middle_commit_sha",
            "commit": {
                "author": {"date": "2026-05-10T10:00:00Z"},
                "committer": {"date": "2026-05-10T10:00:00Z"},
                "message": "Middle update",
            },
        },
        {
            "sha": "oldest_commit_sha",
            "commit": {
                "author": {"date": "2026-01-01T10:00:00Z"},
                "committer": {"date": "2026-01-01T10:00:00Z"},
                "message": "Created skill",
            },
        },
    ]

    transport = create_fake_github_transport(
        files={".claude/skills/demo/SKILL.md": "---\nname: demo\ndescription: A demo.\n---\n"},
        commits_by_path={".claude/skills/demo": fake_commits},
    )

    with httpx.Client(transport=transport) as http_client:
        gh_client = GitHubClient()
        intro_sha, intro_date, upd_sha, upd_date = gh_client.fetch_provenance_and_updated(
            http_client, "owner", "repo", ".claude/skills/demo"
        )

        assert intro_sha == "oldest_commit_sha"
        assert intro_date == "2026-01-01T10:00:00Z"
        assert upd_sha == "newest_commit_sha"
        assert upd_date == "2026-09-20T10:00:00Z"
