"""Heuristic similarity computation for AI Agent Skills (no AI/LLM)."""

from __future__ import annotations

import difflib
import math
import re
from collections import Counter

from pydantic import BaseModel, Field

from skill_atlas.models import Skill

# Common English stop words to filter out for better text keyword overlap
STOP_WORDS: set[str] = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "just",
    "ll",
    "m",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "o",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "re",
    "s",
    "same",
    "shan't",
    "she",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "t",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "ve",
    "very",
    "was",
    "wasn't",
    "we",
    "were",
    "weren't",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
    "skill",
    "agent",
    "action",
    "tool",
    "help",
    "helps",
    "use",
    "used",
    "using",
    "allow",
    "allows",
    "provide",
    "provides",
}


def tokenize_name(name: str) -> list[str]:
    """Tokenize a skill name by splitting camelCase, kebab-case, snake_case, and dots."""
    # Split camelCase
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    # Replace non-alphanumeric with spaces
    tokens = re.split(r"[^a-zA-Z0-9]+", s1.lower())
    return [t for t in tokens if len(t) > 1 and t not in STOP_WORDS]


def tokenize_text(text: str) -> list[str]:
    """Tokenize arbitrary text, filtering punctuation and stop words."""
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 0.0
    union = set1 | set2
    if not union:
        return 0.0
    return len(set1 & set2) / len(union)


def cosine_token_similarity(tokens1: list[str], tokens2: list[str]) -> float:
    """Compute cosine similarity of term frequency vectors."""
    if not tokens1 or not tokens2:
        return 0.0
    vec1 = Counter(tokens1)
    vec2 = Counter(tokens2)

    intersection = set(vec1.keys()) & set(vec2.keys())
    dot_product = sum(vec1[x] * vec2[x] for x in intersection)

    norm1 = math.sqrt(sum(v * v for v in vec1.values()))
    norm2 = math.sqrt(sum(v * v for v in vec2.values()))

    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot_product / (norm1 * norm2)


def string_ratio(s1: str, s2: str) -> float:
    """Compute normalized SequenceMatcher ratio between two strings."""
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1.strip().lower(), s2.strip().lower()).ratio()


class SimilarityBreakdown(BaseModel):
    name: float = 0.0
    description: float = 0.0
    tags: float = 0.0
    body: float = 0.0
    files: float = 0.0


class SimilarSkillMatch(BaseModel):
    skill_a: str
    skill_b: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    breakdown: SimilarityBreakdown
    skill_a_path: str
    skill_b_path: str
    skill_a_description: str = ""
    skill_b_description: str = ""
    skill_a_origin: str = "standalone"
    skill_b_origin: str = "standalone"


class SimilarSkillsResult(BaseModel):
    target: str
    threshold: float
    total_skills: int
    matches: list[SimilarSkillMatch] = Field(default_factory=list)


def calculate_name_similarity(name1: str, name2: str) -> tuple[float, list[str]]:
    """Compute similarity between two skill names."""
    reasons: list[str] = []
    if not name1 or not name2:
        return 0.0, reasons

    n1, n2 = name1.strip().lower(), name2.strip().lower()
    if n1 == n2:
        reasons.append(f"Identical skill name ('{name1}')")
        return 1.0, reasons

    tokens1 = set(tokenize_name(name1))
    tokens2 = set(tokenize_name(name2))

    jaccard = jaccard_similarity(tokens1, tokens2)
    seq_ratio = string_ratio(n1, n2)

    # Combined score
    score = max(jaccard, seq_ratio * 0.9)

    common_tokens = tokens1 & tokens2
    if common_tokens:
        tokens_str = ", ".join(sorted(common_tokens))
        reasons.append(f"Shared name keywords ({tokens_str})")
    elif seq_ratio >= 0.7:
        reasons.append(
            f"High name string similarity ({int(seq_ratio * 100)}%): '{name1}' vs '{name2}'"
        )

    return min(1.0, max(0.0, score)), reasons


def calculate_description_similarity(desc1: str, desc2: str) -> tuple[float, list[str]]:
    """Compute similarity between two skill descriptions."""
    reasons: list[str] = []
    if not desc1 or not desc2:
        return 0.0, reasons

    d1, d2 = desc1.strip().lower(), desc2.strip().lower()
    # Guard against identical trivial/placeholder descriptions (e.g. "TODO")
    placeholder_descriptions = {"todo", "tbd", "n/a", "none", "test", "description", "skill"}
    if d1 == d2:
        if d1 in placeholder_descriptions or len(d1) < 10:
            return 0.1, reasons
        reasons.append("Identical description text")
        return 1.0, reasons

    tokens1 = tokenize_text(desc1)
    tokens2 = tokenize_text(desc2)

    if not tokens1 or not tokens2:
        seq_ratio = string_ratio(d1, d2)
        if seq_ratio >= 0.6:
            reasons.append(f"Similar description phrasing ({int(seq_ratio * 100)}%)")
        return seq_ratio, reasons

    set1, set2 = set(tokens1), set(tokens2)
    jaccard = jaccard_similarity(set1, set2)
    cosine = cosine_token_similarity(tokens1, tokens2)
    seq_ratio = string_ratio(d1, d2)

    score = max(cosine, jaccard, seq_ratio * 0.85)

    common_words = set1 & set2
    if len(common_words) >= 3:
        sample_words = ", ".join(sorted(list(common_words)[:4]))
        reasons.append(f"Matching description concepts ({sample_words})")
    elif cosine >= 0.6:
        reasons.append(f"High description semantic overlap ({int(cosine * 100)}%)")

    return min(1.0, max(0.0, score)), reasons


def calculate_tags_similarity(tags1: list[str], tags2: list[str]) -> tuple[float | None, list[str]]:
    """Compute similarity between tags."""
    reasons: list[str] = []
    clean_tags1 = {t.strip().lower() for t in tags1 if t.strip()}
    clean_tags2 = {t.strip().lower() for t in tags2 if t.strip()}

    if not clean_tags1 or not clean_tags2:
        return None, reasons

    jaccard = jaccard_similarity(clean_tags1, clean_tags2)
    common_tags = clean_tags1 & clean_tags2

    if common_tags:
        tags_str = ", ".join(sorted(common_tags))
        reasons.append(f"Shared tags: {tags_str}")

    return jaccard, reasons


def calculate_body_similarity(body1: str, body2: str) -> tuple[float | None, list[str]]:
    """Compute similarity between markdown prompt bodies."""
    reasons: list[str] = []
    if not body1 or not body2:
        return None, reasons

    tokens1 = tokenize_text(body1)
    tokens2 = tokenize_text(body2)

    if not tokens1 or not tokens2:
        return None, reasons

    cosine = cosine_token_similarity(tokens1, tokens2)
    if cosine >= 0.65:
        reasons.append(f"Similar instruction/body structure ({int(cosine * 100)}% token overlap)")

    return cosine, reasons


def calculate_files_similarity(
    files1: list[str], files2: list[str]
) -> tuple[float | None, list[str]]:
    """Compute similarity between companion files/scripts."""
    reasons: list[str] = []
    # Extract file basenames
    names1 = {f.split("/")[-1].lower() for f in files1 if f}
    names2 = {f.split("/")[-1].lower() for f in files2 if f}

    if not names1 or not names2:
        return None, reasons

    jaccard = jaccard_similarity(names1, names2)
    common_files = names1 & names2
    if common_files:
        files_str = ", ".join(sorted(common_files))
        reasons.append(f"Matching file names: {files_str}")

    return jaccard, reasons


def compare_skills(s1: Skill, s2: Skill) -> SimilarSkillMatch:
    """Compare two skills and produce a detailed similarity match assessment."""
    all_reasons: list[str] = []

    name_score, name_reasons = calculate_name_similarity(s1.name, s2.name)
    all_reasons.extend(name_reasons)

    desc_score, desc_reasons = calculate_description_similarity(s1.description, s2.description)
    all_reasons.extend(desc_reasons)

    tags_score, tags_reasons = calculate_tags_similarity(s1.tags, s2.tags)
    all_reasons.extend(tags_reasons)

    body1 = s1.markdown_body or (s1.raw_content or "")
    body2 = s2.markdown_body or (s2.raw_content or "")
    body_score, body_reasons = calculate_body_similarity(body1, body2)
    all_reasons.extend(body_reasons)

    files1 = s1.referenced_files or s1.available_files or []
    files2 = s2.referenced_files or s2.available_files or []
    files_score, files_reasons = calculate_files_similarity(files1, files2)
    all_reasons.extend(files_reasons)

    # Dynamic weighted score calculation based on available features
    weights: dict[str, float] = {
        "name": 0.30,
        "description": 0.40,
        "tags": 0.15,
        "body": 0.10,
        "files": 0.05,
    }

    scores: dict[str, float] = {
        "name": name_score,
        "description": desc_score,
        "tags": tags_score if tags_score is not None else 0.0,
        "body": body_score if body_score is not None else 0.0,
        "files": files_score if files_score is not None else 0.0,
    }

    # If tags, body, or files are not available, redistribute weights to name & desc
    active_weights: dict[str, float] = {}
    active_weights["name"] = weights["name"]
    active_weights["description"] = weights["description"]
    if tags_score is not None:
        active_weights["tags"] = weights["tags"]
    if body_score is not None:
        active_weights["body"] = weights["body"]
    if files_score is not None:
        active_weights["files"] = weights["files"]

    total_weight = sum(active_weights.values())
    weighted_sum = sum(scores[k] * active_weights[k] for k in active_weights)
    overall_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Boost score if name or description is exceptionally close
    is_meaningful_desc = (
        len(s1.description.strip()) >= 10
        and len(s2.description.strip()) >= 10
        and s1.description.strip().lower()
        not in {"todo", "tbd", "n/a", "none", "test", "description", "skill"}
    )
    if name_score >= 0.95 and desc_score >= 0.8 and is_meaningful_desc:
        overall_score = max(overall_score, 0.90)
    elif desc_score >= 0.95 and is_meaningful_desc:
        overall_score = max(overall_score, 0.85)

    breakdown = SimilarityBreakdown(
        name=round(name_score, 3),
        description=round(desc_score, 3),
        tags=round(tags_score if tags_score is not None else 0.0, 3),
        body=round(body_score if body_score is not None else 0.0, 3),
        files=round(files_score if files_score is not None else 0.0, 3),
    )

    return SimilarSkillMatch(
        skill_a=s1.name,
        skill_b=s2.name,
        score=round(overall_score, 3),
        reasons=all_reasons,
        breakdown=breakdown,
        skill_a_path=s1.path,
        skill_b_path=s2.path,
        skill_a_description=s1.description,
        skill_b_description=s2.description,
        skill_a_origin=s1.origin.value if hasattr(s1.origin, "value") else str(s1.origin),
        skill_b_origin=s2.origin.value if hasattr(s2.origin, "value") else str(s2.origin),
    )


class _SkillFeatures:
    __slots__ = ("all_tokens", "desc_tokens", "files_set", "name_tokens", "skill", "tags_set")

    def __init__(self, skill: Skill) -> None:
        self.skill = skill
        self.name_tokens = set(tokenize_name(skill.name))
        self.desc_tokens = set(tokenize_text(skill.description))
        self.tags_set = {t.strip().lower() for t in skill.tags if t.strip()}
        files_list = getattr(skill, "available_files", []) or []
        self.files_set = {f.split("/")[-1].lower() for f in files_list if f}
        self.all_tokens = self.name_tokens | self.desc_tokens | self.tags_set


def find_similar_skills(
    skills: list[Skill],
    query_skill: str | None = None,
    threshold: float = 0.5,
    top_k: int = 10,
    target: str = ".",
) -> SimilarSkillsResult:
    """Find pairs of similar skills within a collection, or matches for a specific skill.

    Args:
        skills: Discovered list of skills.
        query_skill: Optional skill name or path to find similarities for.
        threshold: Minimum similarity score threshold (0.0 to 1.0).
        top_k: Maximum number of matches to return.
        target: Target name/path for reporting.
    """
    matches: list[SimilarSkillMatch] = []
    n = len(skills)

    if query_skill:
        # Match only against the specified query skill
        clean_q = query_skill.strip().lower()
        # 1. Exact name or exact path match
        target_skills = [
            s for s in skills if s.name.lower() == clean_q or s.path.lower() == clean_q
        ]
        # 2. Substring in name
        if not target_skills:
            target_skills = [s for s in skills if clean_q in s.name.lower()]
        # 3. Substring in path fallback
        if not target_skills:
            target_skills = [s for s in skills if clean_q in s.path.lower()]

        if not target_skills:
            return SimilarSkillsResult(
                target=target,
                threshold=threshold,
                total_skills=n,
                matches=[],
            )

        src_skill = target_skills[0]
        for other in skills:
            if other.path == src_skill.path and other.name == src_skill.name:
                continue
            match = compare_skills(src_skill, other)
            if match.score >= threshold:
                matches.append(match)
    else:
        # Precompute features to prune unpromising pairs for large collections
        feats = [_SkillFeatures(s) for s in skills]

        # Pairwise comparison
        for i in range(n):
            f1 = feats[i]
            for j in range(i + 1, n):
                f2 = feats[j]
                # If threshold is >= 0.2 and collection is not tiny, prune pairs with zero shared tokens
                # unless names are close in length and prefix
                if threshold >= 0.2 and n > 15:
                    shared_tokens = f1.all_tokens & f2.all_tokens
                    shared_files = f1.files_set & f2.files_set
                    name1, name2 = f1.skill.name.lower(), f2.skill.name.lower()
                    names_similar = name1 == name2 or (
                        len(name1) >= 4 and len(name2) >= 4 and name1[:4] == name2[:4]
                    )
                    if not (shared_tokens or shared_files or names_similar):
                        continue

                match = compare_skills(f1.skill, f2.skill)
                if match.score >= threshold:
                    matches.append(match)

    # Sort descending by score, then lexicographically by skill_a and skill_b
    matches.sort(key=lambda m: (-m.score, m.skill_a, m.skill_b))

    if top_k > 0:
        matches = matches[:top_k]

    return SimilarSkillsResult(
        target=target,
        threshold=threshold,
        total_skills=n,
        matches=matches,
    )
