"""Skill Map: Heuristic and AI-driven skill clustering and visualization."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from skill_atlas.models import Skill
from skill_atlas.similarity import (
    STOP_WORDS,
    compare_skills,
    tokenize_name,
    tokenize_text,
)


class SkillCluster(BaseModel):
    """A cluster of semantically or functionally related skills."""

    name: str = Field(description="Descriptive cluster category name (2-4 words).")
    reason: str = Field(description="One-sentence explanation of why these skills belong together.")
    skills: list[str] = Field(description="List of skill names in this cluster.")
    keywords: list[str] = Field(
        default_factory=list, description="Dominant shared keywords or tags."
    )

    @property
    def skills_count(self) -> int:
        return len(self.skills)


class SkillMapResult(BaseModel):
    """Complete result of skill map clustering."""

    method: Literal["heuristic", "ai", "jev"] = Field(description="Clustering methodology used.")
    total_skills: int = Field(description="Total number of skills analyzed.")
    clusters: list[SkillCluster] = Field(default_factory=list, description="Formed clusters.")
    unclustered: list[str] = Field(
        default_factory=list, description="Skills not assigned to multi-item clusters."
    )
    replayed: bool = Field(
        default=False, description="Whether result was loaded from a recorded AI response."
    )


def _extract_skill_keywords(skill: Skill) -> list[str]:
    """Extract significant keywords from skill name, tags, and description deterministically."""
    words: set[str] = set()
    # High-signal tokens: name and tags
    words.update(tokenize_name(skill.name))
    for t in skill.tags:
        words.update(tokenize_name(t))
    desc_words = tokenize_text(skill.description)
    words.update(desc_words[:10])
    return sorted(w for w in words if len(w) > 2 and w not in STOP_WORDS)


def group_skills_heuristic(
    skills: list[Skill],
    threshold: float = 0.35,
) -> SkillMapResult:
    """Group skills into clusters using heuristic shared keywords and pairwise similarity.

    1. Without AI: groups skills based on shared vocabulary, tags, and composite similarity.
    2. Names each cluster using dominant shared words or tags.
    3. Provides a concise reason explaining the heuristic linkage.
    """
    if not skills:
        return SkillMapResult(method="heuristic", total_skills=0, clusters=[])

    skill_dict = {s.name: s for s in skills}
    skill_names = sorted(skill_dict.keys())
    n = len(skill_names)

    if n == 1:
        s = skills[0]
        kw = _extract_skill_keywords(s)[:3]
        name = " ".join(k.capitalize() for k in kw) if kw else s.name.capitalize()
        cluster = SkillCluster(
            name=f"{name} Skill",
            reason=f"Single skill with focus on {', '.join(kw) if kw else s.name}.",
            skills=[s.name],
            keywords=kw,
        )
        return SkillMapResult(
            method="heuristic",
            total_skills=1,
            clusters=[cluster],
        )

    # Compute pairwise similarity and keyword overlaps deterministically
    keyword_map: dict[str, list[str]] = {s.name: _extract_skill_keywords(s) for s in skills}

    # Build adjacency graph based on threshold or strong shared keywords
    adj: dict[str, set[str]] = {name: set() for name in skill_names}
    sim_scores: dict[tuple[str, str], float] = {}

    for i in range(n):
        for j in range(i + 1, n):
            name_a, name_b = skill_names[i], skill_names[j]
            s_a, s_b = skill_dict[name_a], skill_dict[name_b]

            sim = compare_skills(s_a, s_b)
            score = sim.score
            sim_scores[(name_a, name_b)] = score
            sim_scores[(name_b, name_a)] = score

            common_kw = set(keyword_map[name_a]) & set(keyword_map[name_b])
            # Connect if score exceeds threshold or if they share >= 2 distinctive keywords
            if score >= threshold or len(common_kw) >= 2:
                adj[name_a].add(name_b)
                adj[name_b].add(name_a)

    # Find connected components via BFS
    visited: set[str] = set()
    raw_clusters: list[list[str]] = []

    for name in skill_names:
        if name not in visited:
            component: list[str] = []
            queue = [name]
            visited.add(name)
            while queue:
                curr = queue.pop(0)
                component.append(curr)
                for neighbor in sorted(adj[curr]):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            raw_clusters.append(sorted(component))

    # Generate Cluster metadata (name, reason, dominant keywords)
    clusters: list[SkillCluster] = []
    unclustered: list[str] = []

    # Sort clusters deterministically: size descending, then by first skill name
    raw_clusters.sort(key=lambda c: (-len(c), c[0] if c else ""))

    for comp in raw_clusters:
        if len(comp) == 1:
            s_name = comp[0]
            unclustered.append(s_name)
            s = skill_dict[s_name]
            kw = keyword_map[s_name][:3]
            title = " ".join(k.capitalize() for k in kw) if kw else s_name.capitalize()
            cluster = SkillCluster(
                name=f"{title} Tools",
                reason=f"Standalone skill focusing on {', '.join(kw) if kw else s.description}.",
                skills=[s_name],
                keywords=kw,
            )
            clusters.append(cluster)
            continue

        # Multiple skills in cluster: find shared and top keywords
        all_comp_kw: list[str] = []
        for s_name in comp:
            all_comp_kw.extend(keyword_map[s_name])

        from collections import Counter

        kw_counts = Counter(all_comp_kw)

        # Sort deterministically: highest count first, then alphabetical by keyword
        sorted_kw = sorted(kw_counts.keys(), key=lambda k: (-kw_counts[k], k))
        top_kw = sorted_kw[:4]

        # Calculate average internal similarity
        pair_scores: list[float] = []
        for i in range(len(comp)):
            for j in range(i + 1, len(comp)):
                pair_scores.append(sim_scores.get((comp[i], comp[j]), 0.0))
        avg_sim = sum(pair_scores) / len(pair_scores) if pair_scores else 0.0

        # Cluster title
        name_words = [k.capitalize() for k in top_kw[:2]]
        if not name_words:
            cluster_name = f"Group of {len(comp)} Skills"
        else:
            cluster_name = f"{' & '.join(name_words)} Capabilities"

        # Cluster reason
        kw_str = ", ".join(top_kw[:3]) if top_kw else "shared functionality"
        reason = (
            f"Heuristically grouped by shared domain keywords ({kw_str}) "
            f"with average similarity {int(avg_sim * 100)}%."
        )

        clusters.append(
            SkillCluster(
                name=cluster_name,
                reason=reason,
                skills=sorted(comp),
                keywords=top_kw[:4],
            )
        )

    return SkillMapResult(
        method="heuristic",
        total_skills=len(skills),
        clusters=clusters,
        unclustered=unclustered,
        replayed=False,
    )


def _clean_claude_json(raw_text: str) -> list[dict]:
    """Parse JSON array output from Claude response, stripping any surrounding markdown."""
    text = raw_text.strip()
    # Strip markdown code blocks if present
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

    data = json.loads(text)
    if isinstance(data, dict) and "clusters" in data:
        data = data["clusters"]
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list of clusters, got {type(data)}")
    return data


def cluster_skills_ai(
    skills: list[Skill],
    replay_file: Path | str | None = None,
    record_file: Path | str | None = None,
    prompt_extra: str | None = None,
    claude_bin: str | None = None,
) -> SkillMapResult:
    """Cluster skills with Claude (`claude -p`), assigning a name and reason each.

    Supports deterministic test replay via `replay_file`. If Claude CLI is unavailable
    and no replay is found, falls back gracefully to heuristic clustering.
    """
    # 1. Check if replay requested or provided
    if replay_file:
        p = Path(replay_file)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                clusters = [SkillCluster(**item) for item in data]
                all_clustered = {sk for c in clusters for sk in c.skills}
                all_names = {s.name for s in skills}
                unclustered = sorted(list(all_names - all_clustered))
                return SkillMapResult(
                    method="ai",
                    total_skills=len(skills),
                    clusters=clusters,
                    unclustered=unclustered,
                    replayed=True,
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # Fall through if replay file failed
                pass

    # 2. Check if claude executable is available
    resolved_claude = claude_bin or shutil.which("claude")
    if not resolved_claude or (
        not shutil.which(resolved_claude) and not Path(resolved_claude).exists()
    ):
        # Fallback to heuristic
        res = group_skills_heuristic(skills)
        for c in res.clusters:
            c.reason += " (Claude CLI unavailable; fell back to heuristic)"
        return res

    # 3. Format prompt for Claude Code
    skills_lines = []
    for s in skills:
        tags_str = ", ".join(s.tags) if s.tags else "none"
        skills_lines.append(f"- {s.name}: {s.description}. Tags: {tags_str}")

    skills_block = "\n".join(skills_lines)
    prompt = (
        "You are clustering a list of AI agent skills into logical categories. "
        "For each cluster provide: 'name' (concise 2-4 word name), 'reason' (1 sentence explanation), "
        "'skills' (array of skill names). Return strictly a JSON array of objects with keys "
        "'name', 'reason', 'skills', without markdown formatting or preamble.\n\n"
        f"Skills:\n{skills_block}"
    )
    if prompt_extra:
        prompt += f"\n{prompt_extra}"

    try:
        proc = subprocess.run(
            [resolved_claude, "-p", prompt],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        )
        raw_output = proc.stdout.strip()
        parsed_items = _clean_claude_json(raw_output)

        if record_file:
            rec_p = Path(record_file)
            rec_p.parent.mkdir(parents=True, exist_ok=True)
            rec_p.write_text(json.dumps(parsed_items, indent=2), encoding="utf-8")

        clusters = [SkillCluster(**item) for item in parsed_items]
        all_clustered = {sk for c in clusters for sk in c.skills}
        all_names = {s.name for s in skills}
        unclustered = sorted(list(all_names - all_clustered))

        return SkillMapResult(
            method="ai",
            total_skills=len(skills),
            clusters=clusters,
            unclustered=unclustered,
            replayed=False,
        )

    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        # Graceful fallback to heuristic
        res = group_skills_heuristic(skills)
        for c in res.clusters:
            c.reason += " (AI clustering call failed; fell back to heuristic)"
        return res


DEFAULT_JEV_CATEGORIES: dict[str, str] = {
    "memory_and_state": "Memory persistence, state management, session history, shared context",
    "code_and_review": "Code assistance, linting, refactoring, review, language tooling",
    "security_and_audit": "Security analysis, secret scanning, credential leaks, network audit, safety",
    "data_and_sync": "Data synchronization, cloud storage, cache management, file handling",
    "general_automation": "General automation, workflow management, standalone helper tools",
}

JEV_CATEGORY_NAMES: dict[str, str] = {
    "memory_and_state": "Agent Memory & State",
    "code_and_review": "Code Quality & Engineering",
    "security_and_audit": "Security & Auditing",
    "data_and_sync": "Data & Storage Sync",
    "general_automation": "General Automation & Tools",
}


def classify_skills_jev(
    skills: list[Skill],
    categories: dict[str, str] | None = None,
    replay_file: Path | str | None = None,
    record_file: Path | str | None = None,
) -> SkillMapResult:
    """Classify and group skills into functional categories using TypeSafe AI's Jev model.

    Uses Jev's Choice API to classify skills deterministically into typed categories.
    Supports deterministic replay for tests and CI via `replay_file`.
    """
    if not skills:
        return SkillMapResult(method="jev", total_skills=0, clusters=[])

    # 1. Check replay file
    if replay_file:
        p = Path(replay_file)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                clusters = [SkillCluster(**item) for item in data]
                all_clustered = {sk for c in clusters for sk in c.skills}
                all_names = {s.name for s in skills}
                unclustered = sorted(list(all_names - all_clustered))
                return SkillMapResult(
                    method="jev",
                    total_skills=len(skills),
                    clusters=clusters,
                    unclustered=unclustered,
                    replayed=True,
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass

    cat_criteria = categories or DEFAULT_JEV_CATEGORIES

    try:
        import os

        from typesafe_sdk import Choice, TypeSafeClient

        api_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not api_key:
            res = group_skills_heuristic(skills)
            for c in res.clusters:
                c.reason += " (TYPESAFE_API_KEY not configured; fell back to heuristic)"
            return SkillMapResult(
                method="jev",
                total_skills=res.total_skills,
                clusters=res.clusters,
                unclustered=res.unclustered,
                replayed=False,
            )

        clusters_map: dict[str, list[str]] = {k: [] for k in cat_criteria}
        with TypeSafeClient() as client:
            for s in skills:
                state_text = (
                    f"Skill: {s.name}\nDescription: {s.description}\nTags: {', '.join(s.tags)}"
                )
                resp = client.system_one(
                    state=state_text,
                    questions={
                        "category": Choice(
                            instructions="Which category best describes this AI agent skill?",
                            criteria=cat_criteria,
                        )
                    },
                )
                picked = resp.answers["category"].choice
                if picked in clusters_map:
                    clusters_map[picked].append(s.name)
                else:
                    clusters_map.setdefault(picked, []).append(s.name)

        clusters: list[SkillCluster] = []
        for cat_key, member_skills in clusters_map.items():
            if not member_skills:
                continue
            cat_title = JEV_CATEGORY_NAMES.get(cat_key, cat_key.replace("_", " ").title())
            reason = f"Classified by TypeSafe Jev: {cat_criteria.get(cat_key, '')}."
            clusters.append(
                SkillCluster(
                    name=cat_title,
                    reason=reason,
                    skills=sorted(member_skills),
                    keywords=[k for k in cat_key.split("_") if k not in STOP_WORDS],
                )
            )

        if record_file:
            rec_p = Path(record_file)
            rec_p.parent.mkdir(parents=True, exist_ok=True)
            rec_p.write_text(
                json.dumps([c.model_dump() for c in clusters], indent=2), encoding="utf-8"
            )

        all_clustered = {sk for c in clusters for sk in c.skills}
        all_names = {s.name for s in skills}
        unclustered = sorted(list(all_names - all_clustered))

        return SkillMapResult(
            method="jev",
            total_skills=len(skills),
            clusters=clusters,
            unclustered=unclustered,
            replayed=False,
        )

    except (OSError, ValueError, TypeError, RuntimeError, ImportError):
        res = group_skills_heuristic(skills)
        for c in res.clusters:
            c.reason += " (Jev classification unavailable; fell back to heuristic)"
        return SkillMapResult(
            method="jev",
            total_skills=res.total_skills,
            clusters=res.clusters,
            unclustered=res.unclustered,
            replayed=False,
        )
