"""PreToolUse: never-blocking injection of reference digests for source edits."""

from __future__ import annotations

from pathlib import Path

from hooklib import sources
from hooklib.event import Result, file_path


REFERENCE_DIR = Path(__file__).resolve().parents[3] / "reference"
DIGEST_CAP = 2500


def digest(name: str) -> str | None:
    path = REFERENCE_DIR / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    marker = "## Digest"
    start = text.find(marker)
    if start == -1:
        return None
    body = text[start + len(marker):]
    end = body.find("\n## ")
    if end != -1:
        body = body[:end]
    body = body.strip()[:DIGEST_CAP]
    return f"[{name}]\n{body}\nFull rules: reference/{name}"


def references_for(path: str) -> list[str]:
    lang = sources.language(path)
    if sources.is_test(path):
        if lang == "kotlin":
            return ["junit-rules.md", "mocking.md", "kotlin-style.md"]
        return ["junit-rules.md", "mocking.md", "assertions.md", "java-style.md"]
    if lang == "kotlin":
        return ["kotlin-style.md"]
    if lang == "java":
        return ["java-style.md"]
    return []


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    path = file_path(event)
    names = references_for(path)
    if not names:
        return Result(decision="allow", reason="")
    digests = [d for d in (digest(name) for name in names) if d]
    if not digests:
        return Result(decision="allow", reason="")
    return Result(
        decision="allow",
        reason="Reference digests injected.",
        context="\n\n".join(digests),
    )
