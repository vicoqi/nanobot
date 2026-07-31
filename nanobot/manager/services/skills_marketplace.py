"""Search and trend fetching for the public Agent Skills marketplaces.

Ported from upstream ``HKUDS/nanobot`` (``nanobot/webui/skills_marketplace.py``).
Only the search/trending half is ported here; marketplace install lives in a
sibling module (Task 5).

Key adaptation: the upstream parameter ``workspace_path`` has been renamed to
``global_dir`` and now points at the global manager-skills repository. A skill
is considered installed when ``<global_dir>/<name>/SKILL.md`` exists — the
directory name is the skill name.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx

from nanobot.security.network import PinnedDNSAsyncTransport

_PROVIDER_ALL = "all"
_PROVIDER_SKILLS_SH = "skills_sh"
_PROVIDER_SKILLHUB = "skillhub"
_PROVIDERS = {_PROVIDER_ALL, _PROVIDER_SKILLS_SH, _PROVIDER_SKILLHUB}
_SEARCH_URL = "https://skills.sh/api/search"
_TRENDING_URL = "https://skills.sh/api/skills/trending/0"
_SKILL_PAGE_BASE_URL = "https://www.skills.sh"
_SKILLHUB_API_BASE_URL = "https://api.skillhub.cn"
_SKILLHUB_SEARCH_URL = f"{_SKILLHUB_API_BASE_URL}/api/v1/search"
_SKILLHUB_TRENDING_URL = f"{_SKILLHUB_API_BASE_URL}/api/v1/showcase/trending"
_SKILLHUB_PAGE_BASE_URL = "https://skillhub.cn"
_ALL_TIME_URLS = (
    "https://skills.sh/api/skills/all-time/0",
    "https://skills.sh/api/skills/all-time/1",
)
_TREND_VALUES_RE = re.compile(r'\\"values\\":\s*\[([0-9,\s]+)\]')
_SOURCE_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?$"
)
_SKILL_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._+-]{0,63})$")
_WEEKLY_CACHE_TTL_SECONDS = 300
_weekly_cache: dict[tuple[str, str], list[int]] = {}
_weekly_cache_expires_at = 0.0


def _response_json_object(response: httpx.Response) -> dict[str, Any] | None:
    """Narrow an untyped HTTP JSON response at the external-data boundary."""
    payload = cast(object, response.json())
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else None


class SkillsMarketplaceError(Exception):
    """A safe error that can be returned to the WebUI."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def skills_install_supported() -> bool:
    """Return whether the official skills CLI can be launched."""
    return shutil.which("npx") is not None


async def trending_marketplace_skills(
    global_dir: Path,
    *,
    limit: int = 8,
    provider: str = _PROVIDER_ALL,
) -> dict[str, Any]:
    """Return provider-aware marketplace rankings without mixing metric semantics."""
    selected = _valid_provider(provider)
    if selected == _PROVIDER_SKILLHUB:
        return await _trending_skillhub_skills(global_dir, limit=limit)
    if selected == _PROVIDER_SKILLS_SH:
        return await _trending_skills_sh_skills(global_dir, limit=limit)

    results = await asyncio.gather(
        _trending_skills_sh_skills(global_dir, limit=limit),
        _trending_skillhub_skills(global_dir, limit=limit),
        return_exceptions=True,
    )
    payloads = [result for result in results if isinstance(result, dict)]
    if not payloads:
        raise SkillsMarketplaceError(
            "skill marketplaces are temporarily unavailable",
            status=502,
        )
    return {
        "skills": [
            skill
            for payload in payloads
            for skill in payload.get("skills", [])
            if isinstance(skill, dict)
        ],
        "period": "mixed",
        "provider": _PROVIDER_ALL,
        "install_supported": any(bool(payload.get("install_supported")) for payload in payloads),
    }


async def _trending_skills_sh_skills(
    global_dir: Path,
    *,
    limit: int,
) -> dict[str, Any]:
    """Return a source-diverse snapshot of skills.sh's real 24-hour leaderboard."""
    try:
        async with _skills_client() as client:
            response = await client.get(_TRENDING_URL)
            response.raise_for_status()
            payload = _response_json_object(response) or {}
    except (httpx.HTTPError, ValueError) as exc:
        raise SkillsMarketplaceError(
            "skills.sh trending skills are temporarily unavailable",
            status=502,
        ) from exc

    installed = _installed_skill_names(global_dir)
    rows = payload.get("skills", [])
    skills: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        row_payload = cast(dict[str, Any], row)
        source = row_payload.get("source")
        if not isinstance(source, str) or source in seen_sources:
            continue
        skill = _marketplace_skill(row_payload, installed, rank=rank)
        if skill is None:
            continue
        seen_sources.add(source)
        skills.append(skill)
        if len(skills) >= min(max(limit, 1), 20):
            break

    return {
        "skills": skills,
        "period": "24h",
        "provider": _PROVIDER_SKILLS_SH,
        "install_supported": skills_install_supported(),
    }


async def search_marketplace_skills(
    query: str,
    global_dir: Path,
    *,
    limit: int = 20,
    provider: str = _PROVIDER_ALL,
) -> dict[str, Any]:
    """Search one or all catalogs and annotate locally installed results."""
    normalized = " ".join(query.split())
    if len(normalized) < 2:
        raise SkillsMarketplaceError("search query must contain at least 2 characters")
    if len(normalized) > 100:
        raise SkillsMarketplaceError("search query is too long")

    selected = _valid_provider(provider)
    if selected == _PROVIDER_SKILLHUB:
        return await _search_skillhub_skills(normalized, global_dir, limit=limit)
    if selected == _PROVIDER_SKILLS_SH:
        return await _search_skills_sh_skills(normalized, global_dir, limit=limit)

    results = await asyncio.gather(
        _search_skills_sh_skills(normalized, global_dir, limit=limit),
        _search_skillhub_skills(normalized, global_dir, limit=limit),
        return_exceptions=True,
    )
    payloads = [result for result in results if isinstance(result, dict)]
    if not payloads:
        raise SkillsMarketplaceError(
            "skill marketplaces are temporarily unavailable",
            status=502,
        )
    return {
        "query": normalized,
        "skills": [
            skill
            for payload in payloads
            for skill in payload.get("skills", [])
            if isinstance(skill, dict)
        ],
        "provider": _PROVIDER_ALL,
        "install_supported": any(bool(payload.get("install_supported")) for payload in payloads),
    }


async def _search_skills_sh_skills(
    normalized: str,
    global_dir: Path,
    *,
    limit: int,
) -> dict[str, Any]:
    try:
        async with _skills_client() as client:
            response = await client.get(
                _SEARCH_URL,
                params={"q": normalized, "limit": min(max(limit, 1), 50)},
            )
            response.raise_for_status()
            payload = _response_json_object(response) or {}
    except (httpx.HTTPError, ValueError) as exc:
        raise SkillsMarketplaceError(
            "skills.sh search is temporarily unavailable",
            status=502,
        ) from exc

    installed = _installed_skill_names(global_dir)
    rows = payload.get("skills", [])
    skills: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        skill = _marketplace_skill(cast(dict[str, Any], row), installed)
        if skill is not None:
            skills.append(skill)

    return {
        "query": normalized,
        "skills": skills,
        "provider": _PROVIDER_SKILLS_SH,
        "install_supported": skills_install_supported(),
    }


async def _search_skillhub_skills(
    normalized: str,
    global_dir: Path,
    *,
    limit: int,
) -> dict[str, Any]:
    try:
        async with _skillhub_client() as client:
            response = await client.get(
                _SKILLHUB_SEARCH_URL,
                params={"q": normalized, "limit": min(max(limit, 1), 50)},
            )
            response.raise_for_status()
            payload = _response_json_object(response) or {}
    except (httpx.HTTPError, ValueError) as exc:
        raise SkillsMarketplaceError(
            "SkillHub search is temporarily unavailable",
            status=502,
        ) from exc

    installed = _installed_skill_names(global_dir)
    rows = payload.get("results", [])
    skills = [
        skill
        for row in rows
        if isinstance(row, dict)
        if (skill := _skillhub_skill(cast(dict[str, Any], row), installed)) is not None
    ]
    return {
        "query": normalized,
        "skills": skills,
        "provider": _PROVIDER_SKILLHUB,
        "install_supported": True,
    }


async def _trending_skillhub_skills(
    global_dir: Path,
    *,
    limit: int,
) -> dict[str, Any]:
    try:
        async with _skillhub_client() as client:
            response = await client.get(_SKILLHUB_TRENDING_URL)
            response.raise_for_status()
            payload = _response_json_object(response) or {}
    except (httpx.HTTPError, ValueError) as exc:
        raise SkillsMarketplaceError(
            "SkillHub trending skills are temporarily unavailable",
            status=502,
        ) from exc

    installed = _installed_skill_names(global_dir)
    rows = payload.get("skills", [])
    skills: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        skill = _skillhub_skill(cast(dict[str, Any], row), installed, rank=rank)
        if skill is not None:
            skills.append(skill)
        if len(skills) >= min(max(limit, 1), 20):
            break
    return {
        "skills": skills,
        "period": "trending",
        "provider": _PROVIDER_SKILLHUB,
        "install_supported": True,
    }


async def marketplace_skill_trends(
    skill_ids: list[str] | None = None,
) -> dict[str, dict[str, list[int]]]:
    """Return install history independently, filling requested cache misses."""
    requested = _valid_skill_refs(skill_ids or [])
    async with _skills_client() as client:
        weekly_installs = await _load_weekly_installs(client)
        missing = [ref for ref in requested if ref not in weekly_installs]
        if missing:
            weekly_installs.update(await _load_skill_page_trends(client, missing))

    selected = requested or list(weekly_installs)
    return {
        "trends": {
            f"{source}/{skill_id}": values
            for source, skill_id in selected
            if (values := weekly_installs.get((source, skill_id))) is not None
        }
    }


def _skills_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=PinnedDNSAsyncTransport(),
        timeout=10.0,
        follow_redirects=False,
    )


def _skillhub_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=PinnedDNSAsyncTransport(),
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=False,
    )


def _installed_skill_names(global_dir: Path) -> set[str]:
    """Return skill names installed under the global manager-skills repo.

    A directory under ``global_dir`` counts as an installed skill when it
    contains a ``SKILL.md`` file; the directory name is the skill name.
    """
    if not global_dir.is_dir():
        return set()
    return {
        d.name
        for d in global_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


def _marketplace_skill(
    row: dict[str, Any],
    installed: set[str],
    *,
    rank: int | None = None,
) -> dict[str, Any] | None:
    source = row.get("source")
    skill_id = row.get("skillId")
    if not isinstance(source, str) or not _SOURCE_RE.fullmatch(source):
        return None
    if not isinstance(skill_id, str) or not _valid_skill_id(skill_id):
        return None
    display_name = row.get("name")
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = skill_id
    installs = row.get("installs")
    skill: dict[str, Any] = {
        "id": f"{source}/{skill_id}",
        "skill_id": skill_id,
        "name": display_name.strip(),
        "source": source,
        "provider": _PROVIDER_SKILLS_SH,
        "installs": installs if isinstance(installs, int) and installs >= 0 else 0,
        "url": f"https://skills.sh/{source}/{skill_id}",
        "installed": skill_id in installed,
        "install_supported": skills_install_supported(),
        "metric": "installs_24h" if rank is not None else "installs_total",
    }
    if rank is not None:
        skill["rank"] = rank
    return skill


def _skillhub_skill(
    row: dict[str, Any],
    installed: set[str],
    *,
    rank: int | None = None,
) -> dict[str, Any] | None:
    skill_id = row.get("slug")
    if not isinstance(skill_id, str) or not _valid_skill_id(skill_id):
        return None
    display_name = row.get("displayName") or row.get("name") or skill_id
    if not isinstance(display_name, str) or not display_name.strip():
        display_name = skill_id

    namespace = row.get("namespace")
    namespace_payload = cast(dict[str, Any], namespace) if isinstance(namespace, dict) else {}
    handle = namespace_payload.get("handle")
    if not isinstance(handle, str) or not handle.strip():
        owner = row.get("owner_name") or row.get("ownerName")
        handle = owner if isinstance(owner, str) and owner.strip() else "community"
    source = f"@{handle.strip()}/{skill_id}"

    installs = row.get("installs")
    downloads = row.get("downloads")
    publisher = row.get("publisher")
    publisher_payload = cast(dict[str, Any], publisher) if isinstance(publisher, dict) else {}
    verified = publisher_payload.get("verified") is True
    labels = row.get("labels")
    labels_payload = cast(dict[str, Any], labels) if isinstance(labels, dict) else {}
    requires_api_key = str(labels_payload.get("requires_api_key", "")).lower() == "true"
    version = row.get("version")
    if not isinstance(version, str) or _VERSION_RE.fullmatch(version) is None:
        version = ""

    skill: dict[str, Any] = {
        "id": f"{_PROVIDER_SKILLHUB}:{skill_id}",
        "skill_id": skill_id,
        "name": display_name.strip(),
        "source": source,
        "provider": _PROVIDER_SKILLHUB,
        "installs": installs if isinstance(installs, int) and installs >= 0 else 0,
        "downloads": downloads if isinstance(downloads, int) and downloads >= 0 else 0,
        "url": f"{_SKILLHUB_PAGE_BASE_URL}/{quote(handle.strip(), safe='')}/"
        f"{quote(skill_id, safe='')}",
        "installed": skill_id in installed,
        "install_supported": True,
        "metric": "installs_total",
        "version": version,
        "verified": verified,
        "requires_api_key": requires_api_key,
    }
    if rank is not None:
        skill["rank"] = rank
    return skill


async def _load_weekly_installs(
    client: httpx.AsyncClient,
) -> dict[tuple[str, str], list[int]]:
    global _weekly_cache, _weekly_cache_expires_at

    now = time.monotonic()
    if now < _weekly_cache_expires_at:
        return _weekly_cache

    responses = await asyncio.gather(
        *(client.get(url) for url in _ALL_TIME_URLS),
        return_exceptions=True,
    )
    history: dict[tuple[str, str], list[int]] = {}
    successful = False
    for response in responses:
        if isinstance(response, BaseException):
            continue
        try:
            response.raise_for_status()
            payload = _response_json_object(response) or {}
        except (httpx.HTTPError, ValueError):
            continue
        successful = True
        rows = payload.get("skills", [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_payload = cast(dict[str, Any], row)
            source = row_payload.get("source")
            skill_id = row_payload.get("skillId")
            values = row_payload.get("weeklyInstalls")
            if isinstance(source, str) and isinstance(skill_id, str) and isinstance(values, list):
                clean = [
                    value
                    for value in cast(list[object], values)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0
                ]
                if len(clean) >= 2:
                    history[(source, skill_id)] = clean

    if successful:
        _weekly_cache = history
        _weekly_cache_expires_at = now + _WEEKLY_CACHE_TTL_SECONDS
    return history


def _valid_skill_refs(skill_ids: list[str]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for value in skill_ids[:20]:
        if "/" not in value:
            continue
        source, skill_id = value.rsplit("/", 1)
        ref = (source, skill_id)
        if _SOURCE_RE.fullmatch(source) and _valid_skill_id(skill_id) and ref not in refs:
            refs.append(ref)
    return refs


async def _load_skill_page_trends(
    client: httpx.AsyncClient,
    refs: list[tuple[str, str]],
) -> dict[tuple[str, str], list[int]]:
    semaphore = asyncio.Semaphore(6)

    async def fetch(ref: tuple[str, str]) -> tuple[tuple[str, str], list[int]]:
        source, skill_id = ref
        try:
            async with semaphore:
                response = await client.get(f"{_SKILL_PAGE_BASE_URL}/{source}/{skill_id}")
            response.raise_for_status()
        except httpx.HTTPError:
            return ref, []

        match = _TREND_VALUES_RE.search(response.text)
        if match is None:
            return ref, []
        values = [int(value) for value in match.group(1).split(",") if value.strip()]
        return ref, values if len(values) >= 2 else []

    return dict(await asyncio.gather(*(fetch(ref) for ref in refs)))


def _valid_skill_id(value: str) -> bool:
    return len(value) <= 64 and _SKILL_RE.fullmatch(value) is not None


def _valid_provider(value: str, *, allow_all: bool = True) -> str:
    normalized = value.strip().lower() or _PROVIDER_ALL
    allowed = _PROVIDERS if allow_all else _PROVIDERS - {_PROVIDER_ALL}
    if normalized not in allowed:
        raise SkillsMarketplaceError("invalid skill marketplace provider")
    return normalized
