from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.schema_diff import Diff
from app.models import Changelog, SchemaDiff, SchemaSnapshot

log = logging.getLogger("driftgate.changelog")


@dataclass
class _ChangelogResult:
    text: str
    model: Optional[str]


def _hash_diff_set(diffs: list[SchemaDiff]) -> str:
    ids = sorted(str(d.id) for d in diffs)
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()


def _diffs_to_core(diffs: list[SchemaDiff]) -> list[Diff]:
    return [
        Diff(
            severity=d.severity,
            change_type=d.change_type,
            path=d.path,
            old_type=d.old_type,
            new_type=d.new_type,
            old_value=d.old_value_json,
            new_value=d.new_value_json,
            message=d.message,
        )
        for d in diffs
    ]


def _template_changelog(diffs: list[Diff]) -> str:
    by_sev: dict[str, list[Diff]] = {"breaking": [], "risky": [], "safe": []}
    for d in diffs:
        by_sev.setdefault(d.severity, []).append(d)
    parts: list[str] = []
    for sev in ("breaking", "risky", "safe"):
        if by_sev[sev]:
            parts.append(f"## {sev.title()} ({len(by_sev[sev])})")
            for d in by_sev[sev]:
                parts.append(f"- `{d.path}` — {d.message}")
    return "\n".join(parts)


def _validate_llm_output(text: str, diffs: list[Diff]) -> bool:
    if not text or len(text) > 4000:
        return False
    if "##" not in text:
        return False
    # check that path-like tokens in the output are only from the input
    input_paths = {d.path for d in diffs}
    # extract identifiers that look like JSON paths (contain dots, brackets, etc.)
    found_paths = set(re.findall(r"`([^`]+)`", text))
    for fp in found_paths:
        if "." in fp or "[" in fp:
            if fp not in input_paths:
                log.warning("LLM output mentioned unknown path: %s", fp)
                return False
    return True


async def _call_anthropic(diffs_json: str) -> Optional[str]:
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        system = (
            "You are a changelog generator. You will receive a JSON list of API schema diffs "
            "that have ALREADY been classified by severity. Convert them into a developer-readable "
            "markdown changelog.\n\n"
            "Rules (strict):\n"
            "- Do NOT change severity classifications.\n"
            "- Do NOT invent fields, paths, causes, fixes, or migration advice.\n"
            "- Do NOT speculate about why the change occurred.\n"
            "- ONLY describe what changed, using the paths and types in the input.\n"
            "- Group by severity: ## Breaking, ## Risky, ## Safe.\n"
            "- Use backtick-quoted paths exactly as they appear in the input.\n"
            "- Output markdown only. No preamble, no postscript."
        )
        msg = await client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": f"Diffs:\n{diffs_json}"}],
        )
        return msg.content[0].text if msg.content else None
    except Exception as exc:
        log.warning("Anthropic call failed: %s", exc)
        return None


async def generate_changelog(
    db: AsyncSession, snapshot: SchemaSnapshot, diff_rows: list[SchemaDiff]
) -> Changelog:
    diff_set_hash = _hash_diff_set(diff_rows)

    # cache lookup
    r = await db.execute(
        select(Changelog).where(
            Changelog.snapshot_id == snapshot.id,
            Changelog.diff_set_hash == diff_set_hash,
        )
    )
    cached = r.scalar_one_or_none()
    if cached:
        return cached

    core_diffs = _diffs_to_core(diff_rows)
    diffs_json = json.dumps(
        [d.model_dump() for d in core_diffs], indent=2, default=str
    )

    text: str
    model_name: Optional[str] = None

    if settings.anthropic_api_key:
        llm_text = await _call_anthropic(diffs_json)
        if llm_text and _validate_llm_output(llm_text, core_diffs):
            text = llm_text
            model_name = settings.llm_model
        else:
            log.info("LLM output invalid or missing, using template fallback")
            text = _template_changelog(core_diffs)
    else:
        text = _template_changelog(core_diffs)

    changelog = Changelog(
        endpoint_id=snapshot.endpoint_id,
        snapshot_id=snapshot.id,
        diff_ids=[str(d.id) for d in diff_rows],
        diff_set_hash=diff_set_hash,
        generated_text=text,
        model_name=model_name,
    )
    db.add(changelog)
    await db.flush()
    await db.refresh(changelog)
    return changelog
