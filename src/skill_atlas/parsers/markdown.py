"""Markdown and YAML frontmatter parser for SKILL.md files."""

import re
import urllib.parse
from typing import Any

import frontmatter


def extract_referenced_files(markdown_body: str) -> list[str]:
    """Extract local file paths referenced in Markdown links, ignoring code blocks."""
    # Strip fenced code blocks
    cleaned = re.sub(r"(?s)```.*?```", "", markdown_body)
    # Strip inline code blocks
    cleaned = re.sub(r"`[^`\n]+`", "", cleaned)

    # Matches markdown links: [link text](target_path)
    link_pattern = re.compile(r"\[.*?\]\((.*?)\)")
    matches = link_pattern.findall(cleaned)
    local_paths: list[str] = []

    for target in matches:
        target = target.strip().strip("<>")
        # Remove quotes or titles in markdown links e.g. (path "title")
        if " " in target:
            target = target.split(" ", 1)[0].strip()

        # Remove anchor #section
        if "#" in target:
            target = target.split("#", 1)[0].strip()

        # Remove query parameters ?key=value
        if "?" in target:
            target = target.split("?", 1)[0].strip()

        # Unquote URL-encoded characters (e.g. %20 -> space)
        target = urllib.parse.unquote(target)

        # Exclude web URLs, mailto, empty targets, data/file URIs
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:", "ftp://", "file:", "data:", "//")):
            continue

        local_paths.append(target)

    return local_paths


def parse_skill_markdown(content: str, fallback_name: str = "") -> dict[str, Any]:
    """Parse SKILL.md content, extracting metadata, body, and referenced links."""
    metadata: dict[str, Any] = {}
    body = ""
    parse_error: str | None = None
    has_frontmatter = False

    # Check for YAML frontmatter presence
    stripped = content.strip()
    if stripped.startswith("---"):
        has_frontmatter = True
        try:
            post = frontmatter.loads(content)
            metadata = dict(post.metadata) if isinstance(post.metadata, dict) else {}
            body = post.content
        except Exception as err:  # noqa: BLE001
            parse_error = f"YAML frontmatter parsing failed: {err}"
            # Extract raw body after potential frontmatter closing
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2]
            else:
                body = content
    else:
        body = content

    # Extract primary fields with fallback
    raw_name = metadata.get("name")
    if raw_name is not None and str(raw_name).strip():
        name = str(raw_name).strip()
    else:
        name = fallback_name

    raw_description = metadata.get("description", "")
    description = str(raw_description).strip() if raw_description is not None else ""

    version = str(metadata.get("version")) if metadata.get("version") is not None else None
    author = str(metadata.get("author")) if metadata.get("author") is not None else None

    raw_tags = metadata.get("tags")
    tags: list[str] = []
    if isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    referenced_files = extract_referenced_files(body)

    return {
        "name": name,
        "description": description,
        "version": version,
        "author": author,
        "tags": tags,
        "frontmatter": metadata,
        "markdown_body": body,
        "referenced_files": referenced_files,
        "has_frontmatter": has_frontmatter,
        "parse_error": parse_error,
    }
