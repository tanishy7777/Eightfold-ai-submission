"""Skill canonicalization via an explicit alias map.

'js', 'JS', 'Javascript' all collapse to 'JavaScript'. An unknown skill is
NOT dropped — it is kept as typed, but flagged via `is_known(...) == False` so
the confidence layer can discount it (kept-as-is, lower confidence).
"""

from __future__ import annotations

import re

# alias (lower-cased) -> canonical name. Small and explicit on purpose.
_ALIASES: dict[str, str] = {
    "js": "JavaScript", "javascript": "JavaScript", "java script": "JavaScript",
    "ecmascript": "JavaScript",
    "ts": "TypeScript", "typescript": "TypeScript",
    "py": "Python", "python": "Python", "python3": "Python",
    "go": "Go", "golang": "Go",
    "react": "React", "reactjs": "React", "react.js": "React", "react js": "React",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js", "node js": "Node.js",
    "c++": "C++", "cpp": "C++",
    "c#": "C#", "csharp": "C#", "c sharp": "C#",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "psql": "PostgreSQL",
    "k8s": "Kubernetes", "kubernetes": "Kubernetes",
    "aws": "AWS", "amazon web services": "AWS",
    "gcp": "GCP", "google cloud": "GCP", "google cloud platform": "GCP",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "tf": "TensorFlow", "tensorflow": "TensorFlow", "pytorch": "PyTorch",
    "sql": "SQL", "docker": "Docker", "kafka": "Kafka", "redis": "Redis",
    "java": "Java", "rust": "Rust", "ruby": "Ruby",
    "rails": "Ruby on Rails", "ruby on rails": "Ruby on Rails",
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "graphql": "GraphQL", "rest": "REST", "html": "HTML", "css": "CSS",
}

KNOWN_CANONICAL = set(_ALIASES.values())

# Multiplier applied to an unrecognized skill's confidence. < 1 so a known,
# canonicalized skill always outranks a guessed one with the same evidence.
UNKNOWN_SKILL_PENALTY = 0.7

_WS = re.compile(r"\s+")
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")  # drop "(ES6)", "(advanced)"


def canonical_skill(raw: object) -> str | None:
    """Canonical name for a skill, or None if empty. Unknown but non-empty
    input is returned cleaned-but-unchanged (kept, never invented away)."""
    if raw is None:
        return None
    s = _TRAILING_PAREN.sub("", _WS.sub(" ", str(raw).strip()))
    if not s:
        return None
    return _ALIASES.get(s.lower(), s)


def is_known(name: str) -> bool:
    """True if `name` is one of our canonical skills (alias map hit)."""
    return name in KNOWN_CANONICAL


def split_skills(text: object) -> list[str]:
    """Split a free-text skill list ('Python, JS and Go') into raw tokens."""
    if text is None:
        return []
    parts = re.split(r"[,\n;|]| and ", str(text))
    return [p.strip() for p in parts if p.strip()]
