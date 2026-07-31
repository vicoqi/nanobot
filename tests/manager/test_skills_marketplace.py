"""Tests for marketplace search/trending/install ported to the global skills dir.

These tests mock the httpx clients so no real network egress happens. They
verify response parsing, installed-skill marking (now read from ``global_dir``
instead of the upstream ``workspace_path``), provider routing, validation,
trend loading, and (Task 5) safe install of SkillHub archives and skills.sh
CLI output into ``global_dir``.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nanobot.manager.services import skills_marketplace as sm
from nanobot.manager.services.skills_marketplace import (
    SkillsMarketplaceError,
    _installed_skill_names,
    _load_skill_page_trends,
    _load_weekly_installs,
    _marketplace_skill,
    _response_json_object,
    _skillhub_skill,
    _valid_provider,
    _valid_skill_id,
    _valid_skill_refs,
    install_marketplace_skill,
    marketplace_skill_trends,
    search_marketplace_skills,
    skills_install_supported,
    trending_marketplace_skills,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_installed(global_dir: Path, name: str) -> None:
    """Create a skill directory with SKILL.md inside ``global_dir``."""
    d = global_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")


def _make_response(status: int = 200, *, json=None, text: str | None = None) -> httpx.Response:
    """Build an httpx.Response with a request attached (raise_for_status-safe)."""
    request = httpx.Request("GET", "https://example.com/")
    return httpx.Response(status, json=json, text=text, request=request)


def _mock_client_factory(response: httpx.Response) -> MagicMock:
    """Return a mock matching ``_skills_client()`` / ``_skillhub_client()`` shape.

    The returned object is callable (``client()``) and synchronously returns an
    async-context-manager whose ``.get`` resolves to ``response``.
    """
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    # AsyncMock's default __aenter__ returns a child mock, not ``client``.
    # Bind it explicitly so ``async with client as c`` yields our configured
    # client with the stubbed ``.get``.
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=client)


async def _reset_weekly_cache() -> None:
    """Clear module-global trend cache so tests do not leak state."""
    sm._weekly_cache = {}
    sm._weekly_cache_expires_at = 0.0


# ---------------------------------------------------------------------------
# _response_json_object / pure helpers
# ---------------------------------------------------------------------------


def test_response_json_object_dict() -> None:
    resp = _make_response(json={"a": 1})
    assert _response_json_object(resp) == {"a": 1}


def test_response_json_object_non_dict_returns_none() -> None:
    resp = _make_response(json=[1, 2, 3])
    assert _response_json_object(resp) is None


def test_skills_install_supported_returns_bool() -> None:
    assert isinstance(skills_install_supported(), bool)


# ---------------------------------------------------------------------------
# _installed_skill_names — reads global_dir directly (key adaptation)
# ---------------------------------------------------------------------------


def test_installed_skill_names_reads_global_dir(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "alpha")
    _make_installed(global_dir, "beta")
    # Directory without SKILL.md is ignored.
    (global_dir / "not-a-skill").mkdir(parents=True)
    assert _installed_skill_names(global_dir) == {"alpha", "beta"}


def test_installed_skill_names_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert _installed_skill_names(tmp_path / "missing") == set()


# ---------------------------------------------------------------------------
# _marketplace_skill / _skillhub_skill parsing
# ---------------------------------------------------------------------------


def test_marketplace_skill_valid() -> None:
    row = {"source": "owner/repo", "skillId": "my-skill", "name": "My", "installs": 7}
    skill = _marketplace_skill(row, set())
    assert skill is not None
    assert skill["id"] == "owner/repo/my-skill"
    assert skill["skill_id"] == "my-skill"
    assert skill["installed"] is False
    assert skill["installs"] == 7
    assert skill["provider"] == "skills_sh"


def test_marketplace_skill_marks_installed() -> None:
    row = {"source": "owner/repo", "skillId": "my-skill", "name": "My"}
    skill = _marketplace_skill(row, {"my-skill"})
    assert skill is not None
    assert skill["installed"] is True


def test_marketplace_skill_rejects_bad_source() -> None:
    row = {"source": "bad", "skillId": "ok", "name": "x"}
    assert _marketplace_skill(row, set()) is None


def test_skillhub_skill_valid() -> None:
    row = {
        "slug": "hub-skill",
        "displayName": "Hub",
        "namespace": {"handle": "alice"},
        "installs": 3,
        "downloads": 10,
        "publisher": {"verified": True},
        "labels": {"requires_api_key": "true"},
        "version": "1.2.3",
    }
    skill = _skillhub_skill(row, set())
    assert skill is not None
    assert skill["skill_id"] == "hub-skill"
    assert skill["source"] == "@alice/hub-skill"
    assert skill["installed"] is False
    assert skill["verified"] is True
    assert skill["requires_api_key"] is True
    assert skill["version"] == "1.2.3"


def test_skillhub_skill_rejects_bad_slug() -> None:
    row = {"slug": "Invalid Slug"}
    assert _skillhub_skill(row, set()) is None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def test_valid_provider_defaults_to_all() -> None:
    assert _valid_provider("") == "all"


def test_valid_provider_rejects_unknown() -> None:
    with pytest.raises(SkillsMarketplaceError):
        _valid_provider("nope")


def test_valid_provider_allow_all_false_rejects_all() -> None:
    with pytest.raises(SkillsMarketplaceError):
        _valid_provider("all", allow_all=False)


def test_valid_skill_id_accepts_kebab() -> None:
    assert _valid_skill_id("foo-bar-123") is True


def test_valid_skill_id_rejects_uppercase() -> None:
    assert _valid_skill_id("FooBar") is False


def test_valid_skill_refs_parses_owner_repo_skill() -> None:
    """A ref shaped like owner/repo/skill-id splits into (owner/repo, skill-id)."""
    refs = _valid_skill_refs(["owner/repo/foo-bar", "bad-no-slash", "x"])
    assert ("owner/repo", "foo-bar") in refs
    assert len(refs) == 1


def test_valid_skill_refs_dedupes() -> None:
    refs = _valid_skill_refs(["owner/repo/foo", "owner/repo/foo"])
    assert refs == [("owner/repo", "foo")]


# ---------------------------------------------------------------------------
# search_marketplace_skills — skills.sh
# ---------------------------------------------------------------------------


async def test_search_skills_sh_marks_installed(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "already-installed")

    fake_resp = _make_response(
        json={
            "skills": [
                {
                    "source": "owner/repo",
                    "skillId": "already-installed",
                    "name": "Already",
                    "installs": 1,
                },
                {
                    "source": "owner/repo",
                    "skillId": "new-one",
                    "name": "New",
                    "installs": 0,
                },
            ]
        },
    )
    with patch.object(sm, "_skills_client", _mock_client_factory(fake_resp)):
        result = await search_marketplace_skills("query", global_dir, provider="skills_sh")

    skills = {s["skill_id"]: s for s in result["skills"]}
    assert skills["already-installed"]["installed"] is True
    assert skills["new-one"]["installed"] is False
    assert result["provider"] == "skills_sh"


async def test_search_skills_sh_query_too_short(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="at least 2"):
        await search_marketplace_skills("q", tmp_path, provider="skills_sh")


async def test_search_skills_sh_query_too_long(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="too long"):
        await search_marketplace_skills("x" * 101, tmp_path, provider="skills_sh")


async def test_search_skills_sh_http_error_raises_502(tmp_path: Path) -> None:
    fake_resp = _make_response(500, text="boom")
    with patch.object(sm, "_skills_client", _mock_client_factory(fake_resp)):
        with pytest.raises(SkillsMarketplaceError) as exc:
            await search_marketplace_skills("query", tmp_path, provider="skills_sh")
    assert exc.value.status == 502


# ---------------------------------------------------------------------------
# search_marketplace_skills — skillhub
# ---------------------------------------------------------------------------


async def test_search_skillhub_marks_installed(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "hub-installed")

    fake_resp = _make_response(
        json={
            "results": [
                {"slug": "hub-installed", "displayName": "HubInst"},
                {"slug": "hub-new", "displayName": "HubNew"},
            ]
        },
    )
    with patch.object(sm, "_skillhub_client", _mock_client_factory(fake_resp)):
        result = await search_marketplace_skills("query", global_dir, provider="skillhub")

    skills = {s["skill_id"]: s for s in result["skills"]}
    assert skills["hub-installed"]["installed"] is True
    assert skills["hub-new"]["installed"] is False
    assert result["provider"] == "skillhub"


# ---------------------------------------------------------------------------
# search_marketplace_skills — "all" combines both providers
# ---------------------------------------------------------------------------


async def test_search_all_combines_both_providers(tmp_path: Path) -> None:
    skills_sh_resp = _make_response(
        json={"skills": [{"source": "owner/repo", "skillId": "sh-one", "name": "SH"}]},
    )
    skillhub_resp = _make_response(
        json={"results": [{"slug": "hub-one", "displayName": "Hub"}]},
    )
    with (
        patch.object(sm, "_skills_client", _mock_client_factory(skills_sh_resp)),
        patch.object(sm, "_skillhub_client", _mock_client_factory(skillhub_resp)),
    ):
        result = await search_marketplace_skills("query", tmp_path, provider="all")

    ids = [s["skill_id"] for s in result["skills"]]
    assert "sh-one" in ids
    assert "hub-one" in ids
    assert result["provider"] == "all"


async def test_search_all_both_fail_raises_502(tmp_path: Path) -> None:
    bad = _make_response(503, text="down")
    with (
        patch.object(sm, "_skills_client", _mock_client_factory(bad)),
        patch.object(sm, "_skillhub_client", _mock_client_factory(bad)),
    ):
        with pytest.raises(SkillsMarketplaceError) as exc:
            await search_marketplace_skills("query", tmp_path, provider="all")
    assert exc.value.status == 502


# ---------------------------------------------------------------------------
# trending_marketplace_skills
# ---------------------------------------------------------------------------


async def test_trending_skills_sh_source_diversity(tmp_path: Path) -> None:
    """Trending picks one skill per source until the limit is reached."""
    fake_resp = _make_response(
        json={
            "skills": [
                {"source": "alice/a", "skillId": "one", "name": "One"},
                {"source": "alice/a", "skillId": "two", "name": "Two"},  # dup source
                {"source": "bob/b", "skillId": "three", "name": "Three"},
            ]
        },
    )
    with patch.object(sm, "_skills_client", _mock_client_factory(fake_resp)):
        result = await trending_marketplace_skills(tmp_path, limit=8, provider="skills_sh")

    sources = [s["source"] for s in result["skills"]]
    assert sources == ["alice/a", "bob/b"]
    assert result["period"] == "24h"
    # Rank reflects original leaderboard position (skipped dup still consumes rank).
    assert [s["rank"] for s in result["skills"]] == [1, 3]


async def test_trending_skillhub_caps_at_limit(tmp_path: Path) -> None:
    rows = [
        {"slug": f"skill-{i}", "displayName": f"S{i}"}
        for i in range(5)
    ]
    fake_resp = _make_response(json={"skills": rows})
    with patch.object(sm, "_skillhub_client", _mock_client_factory(fake_resp)):
        result = await trending_marketplace_skills(tmp_path, limit=2, provider="skillhub")
    assert len(result["skills"]) == 2
    assert result["period"] == "trending"


async def test_trending_all_combines(tmp_path: Path) -> None:
    skills_sh_resp = _make_response(
        json={"skills": [{"source": "alice/a", "skillId": "sh", "name": "SH"}]},
    )
    skillhub_resp = _make_response(
        json={"skills": [{"slug": "hub", "displayName": "Hub"}]},
    )
    with (
        patch.object(sm, "_skills_client", _mock_client_factory(skills_sh_resp)),
        patch.object(sm, "_skillhub_client", _mock_client_factory(skillhub_resp)),
    ):
        result = await trending_marketplace_skills(tmp_path, provider="all")
    ids = [s["skill_id"] for s in result["skills"]]
    assert "sh" in ids
    assert "hub" in ids
    assert result["provider"] == "all"


# ---------------------------------------------------------------------------
# marketplace_skill_trends + _load_weekly_installs + _load_skill_page_trends
# ---------------------------------------------------------------------------


async def test_load_weekly_installs_parses_values() -> None:
    await _reset_weekly_cache()
    resp = _make_response(
        json={
            "skills": [
                {
                    "source": "owner/repo",
                    "skillId": "trending-skill",
                    "weeklyInstalls": [1, 2, 3],
                }
            ]
        },
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    history = await _load_weekly_installs(client)
    assert history[("owner/repo", "trending-skill")] == [1, 2, 3]


async def test_load_skill_page_trends_extracts_values() -> None:
    page = _make_response(text='<script>data=\\"values\\": [10, 20, 30]</script>')
    client = AsyncMock()
    client.get = AsyncMock(return_value=page)
    result = await _load_skill_page_trends(client, [("owner/repo", "x")])
    assert result == {("owner/repo", "x"): [10, 20, 30]}


async def test_marketplace_skill_trends_returns_requested(tmp_path: Path) -> None:
    """End-to-end: weekly cache hit serves the requested skill ref."""
    await _reset_weekly_cache()
    weekly_resp = _make_response(
        json={
            "skills": [
                {
                    "source": "owner/repo",
                    "skillId": "wk",
                    "weeklyInstalls": [5, 6],
                }
            ]
        },
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=weekly_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    # ``_skills_client`` must return the client synchronously (not a coroutine)
    # because marketplace_skill_trends does ``async with _skills_client() as c``.
    with patch.object(sm, "_skills_client", MagicMock(return_value=client)):
        result = await marketplace_skill_trends(["owner/repo/wk"])
    assert result["trends"]["owner/repo/wk"] == [5, 6]


# ---------------------------------------------------------------------------
# Install — helpers (zip fixtures, fake skills.sh subprocess)
# ---------------------------------------------------------------------------


def _build_zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    """Return in-memory zip bytes for ``name -> text|bytes`` entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in entries.items():
            if isinstance(body, str):
                z.writestr(name, body.encode("utf-8"))
            else:
                z.writestr(name, body)
    return buf.getvalue()


class _FakeStreamResponse:
    """Minimal stand-in for the object yielded by ``httpx.AsyncClient.stream``."""

    def __init__(self, *, content: bytes, status_code: int = 200, headers=None) -> None:
        self._content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("GET", "https://fake.test/"),
                response=httpx.Response(self.status_code),
            )

    async def aiter_bytes(self):
        # Single-chunk yield is enough for the size checks exercised here.
        yield self._content


class _FakeStreamCM:
    """Async context manager wrapping a :class:`_FakeStreamResponse`."""

    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeStreamResponse:
        return self._response

    async def __aexit__(self, *_exc) -> None:
        return None


def _build_skillhub_mock_client(
    *,
    zip_bytes: bytes,
    download_url: str = "https://download.myqcloud.com/good.zip",
    redirect_status: int = 302,
) -> AsyncMock:
    """Build a mock matching ``_skillhub_client()`` for the install flow.

    - ``.get(...)`` for the redirect returns a redirect response with the
      configured ``Location``.
    - ``.stream("GET", location, ...)`` returns an async context manager
      that yields ``zip_bytes``.
    """
    client = AsyncMock()
    redirect_resp = httpx.Response(
        redirect_status,
        headers={"Location": download_url},
        request=httpx.Request("GET", "https://api.skillhub.cn/api/v1/download"),
    )

    async def _get(url, **_kwargs):
        return redirect_resp

    client.get = AsyncMock(side_effect=_get)

    stream_response = _FakeStreamResponse(content=zip_bytes)
    client.stream = MagicMock(return_value=_FakeStreamCM(stream_response))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _make_subprocess_patch(*, skill_id: str, body: str | None, returncode: int = 0):
    """Return an async side-effect for ``asyncio.create_subprocess_exec``.

    When ``body`` is not ``None`` the fake CLI writes ``SKILL.md`` with that
    body into ``<cwd>/skills/<skill_id>/`` to mirror the real skills.sh CLI
    layout confirmed by the Task 1 spike.
    """

    async def _exec(*_args, cwd=None, **_kwargs):
        if body is not None:
            skill_dir = Path(cwd) / "skills" / skill_id
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
        proc = MagicMock()
        proc.returncode = returncode

        async def _communicate():
            return (b"", b"") if body is None else (body.encode("utf-8"), b"")

        proc.communicate = _communicate
        proc.kill = MagicMock()
        return proc

    return _exec


# ---------------------------------------------------------------------------
# Install — SkillHub helpers (pure)
# ---------------------------------------------------------------------------


def test_skillhub_hash_ignored_rules() -> None:
    """Hash-skip rules target OS noise and the upstream manifest marker."""
    from nanobot.manager.services.skills_marketplace import _skillhub_hash_ignored

    assert _skillhub_hash_ignored("_meta.json") is True
    assert _skillhub_hash_ignored("foo/_meta.json") is False  # only at archive root
    assert _skillhub_hash_ignored("__MACOSX/x") is True
    assert _skillhub_hash_ignored("foo/__MACOSX/y") is True
    assert _skillhub_hash_ignored("foo/.DS_Store") is True
    assert _skillhub_hash_ignored("foo/._bar") is True
    assert _skillhub_hash_ignored("foo/THUMBS.DB") is True
    assert _skillhub_hash_ignored("foo/SKILL.md") is False


def test_valid_skillhub_download_url_accepts_myqcloud() -> None:
    from nanobot.manager.services.skills_marketplace import _valid_skillhub_download_url

    assert _valid_skillhub_download_url("https://download.myqcloud.com/x.zip") is True
    assert _valid_skillhub_download_url("https://a.b.myqcloud.com/x.zip") is True


def test_valid_skillhub_download_url_rejects_insecure() -> None:
    from nanobot.manager.services.skills_marketplace import _valid_skillhub_download_url

    assert _valid_skillhub_download_url("http://download.myqcloud.com/x.zip") is False
    assert _valid_skillhub_download_url("https://evil.com/x.zip") is False
    assert _valid_skillhub_download_url("https://user:pass@download.myqcloud.com/x") is False
    assert _valid_skillhub_download_url("https://download.myqcloud.com:8080/x") is False
    assert _valid_skillhub_download_url("not a url") is False


def test_validated_skillhub_entries_rejects_traversal(tmp_path: Path) -> None:
    from nanobot.manager.services.skills_marketplace import _validated_skillhub_entries

    archive = tmp_path / "bad.zip"
    archive.write_bytes(_build_zip_bytes({"../../etc/passwd": "x"}))
    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises(SkillsMarketplaceError, match="unsafe path"):
            _validated_skillhub_entries(zf)


def test_validated_skillhub_entries_rejects_absolute(tmp_path: Path) -> None:
    from nanobot.manager.services.skills_marketplace import _validated_skillhub_entries

    archive = tmp_path / "bad.zip"
    archive.write_bytes(_build_zip_bytes({"/etc/passwd": "x"}))
    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises(SkillsMarketplaceError, match="unsafe path"):
            _validated_skillhub_entries(zf)


def test_validated_skillhub_entries_rejects_symlink(tmp_path: Path) -> None:
    """A zip entry claiming to be a symlink must be rejected outright."""
    import stat

    from nanobot.manager.services.skills_marketplace import _validated_skillhub_entries

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        info = zipfile.ZipInfo("link")
        # external_attr stores the Unix mode in its top 16 bits.
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "target")
    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises(SkillsMarketplaceError, match="unsafe path"):
            _validated_skillhub_entries(zf)


def test_validated_skillhub_entries_requires_skill_md(tmp_path: Path) -> None:
    from nanobot.manager.services.skills_marketplace import _validated_skillhub_entries

    archive = tmp_path / "bad.zip"
    archive.write_bytes(_build_zip_bytes({"foo/something.txt": "x"}))
    with zipfile.ZipFile(archive, "r") as zf:
        with pytest.raises(SkillsMarketplaceError, match="SKILL.md"):
            _validated_skillhub_entries(zf)


def test_validated_skillhub_entries_accepts_valid(tmp_path: Path) -> None:
    from nanobot.manager.services.skills_marketplace import _validated_skillhub_entries

    archive = tmp_path / "ok.zip"
    # SkillHub archives store files at the zip root; the per-skill directory
    # is created at extract time by os.replace(stage, <repo>/<skill_id>).
    archive.write_bytes(
        _build_zip_bytes({"SKILL.md": "---\ndescription: d\n---\n", "extra.txt": "x"})
    )
    with zipfile.ZipFile(archive, "r") as zf:
        entries = _validated_skillhub_entries(zf)
    names = {normalized for _info, normalized in entries}
    assert names == {"SKILL.md", "extra.txt"}


def test_safe_output_tail_strips_ansi_and_tails() -> None:
    from nanobot.manager.services.skills_marketplace import _safe_output_tail

    # ANSI escape + leading/trailing blank lines are cleaned, only last 3 lines kept.
    raw = b"\x1b[31mline1\x1b[0m\n\nline2\nline3\nline4\n"
    assert _safe_output_tail(raw) == "line2 · line3 · line4"
    assert _safe_output_tail(None) == ""
    assert _safe_output_tail(b"") == ""


# ---------------------------------------------------------------------------
# Install — SkillHub end-to-end
# ---------------------------------------------------------------------------


async def test_install_skillhub_downloads_to_global(tmp_path: Path) -> None:
    """A valid SkillHub archive is extracted into ``<global_dir>/<skill_id>``."""
    from nanobot.manager.services.skills_marketplace import _validate_skillhub_archive

    global_dir = tmp_path / "manager-skills"
    # SkillHub archives store SKILL.md at the zip root; the per-skill
    # directory ``<global_dir>/<skill_id>`` is created by os.replace.
    zip_bytes = _build_zip_bytes({"SKILL.md": "---\ndescription: d\n---\n"})
    # Compute the real fingerprint so signature validation passes end-to-end.
    archive_copy = tmp_path / "expected.zip"
    archive_copy.write_bytes(zip_bytes)
    expected_hash = _validate_skillhub_archive(archive_copy)

    client = _build_skillhub_mock_client(zip_bytes=zip_bytes)
    with (
        patch.object(sm, "_skillhub_client", MagicMock(return_value=client)),
        patch.object(
            sm, "_skillhub_latest_version", new=AsyncMock(return_value="1.0.0")
        ),
        patch.object(
            sm,
            "_skillhub_signature",
            new=AsyncMock(return_value={"content_hash": expected_hash}),
        ),
    ):
        result = await install_marketplace_skill(
            "skillhub", "good-skill", global_dir, provider="skillhub"
        )

    assert (global_dir / "good-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "---\ndescription: d\n---\n"
    assert result["installed"] is True
    assert result["already_installed"] is False
    assert result["provider"] == "skillhub"
    assert result["version"] == "1.0.0"


async def test_install_skillhub_rejects_path_traversal(tmp_path: Path) -> None:
    """A malicious SkillHub archive must not leak files outside ``global_dir``."""
    global_dir = tmp_path / "manager-skills"
    zip_bytes = _build_zip_bytes({"../../etc/passwd": "root:x:0:0\n"})

    client = _build_skillhub_mock_client(zip_bytes=zip_bytes)
    with (
        patch.object(sm, "_skillhub_client", MagicMock(return_value=client)),
        patch.object(
            sm, "_skillhub_latest_version", new=AsyncMock(return_value="1.0.0")
        ),
        patch.object(
            sm,
            "_skillhub_signature",
            new=AsyncMock(return_value={"content_hash": "a" * 64}),
        ),
    ):
        with pytest.raises(SkillsMarketplaceError, match="unsafe path"):
            await install_marketplace_skill(
                "skillhub", "bad-skill", global_dir, provider="skillhub"
            )

    # Nothing escaped: no passwd file written next to the repo, no skill dir.
    assert not (tmp_path / "etc" / "passwd").exists()
    assert not (global_dir / "bad-skill").exists()


async def test_install_skillhub_rejects_fingerprint_mismatch(tmp_path: Path) -> None:
    """A fingerprint that does not match the downloaded bytes aborts install."""
    global_dir = tmp_path / "manager-skills"
    zip_bytes = _build_zip_bytes({"SKILL.md": "---\ndescription: d\n---\n"})

    client = _build_skillhub_mock_client(zip_bytes=zip_bytes)
    with (
        patch.object(sm, "_skillhub_client", MagicMock(return_value=client)),
        patch.object(
            sm, "_skillhub_latest_version", new=AsyncMock(return_value="1.0.0")
        ),
        patch.object(
            sm,
            "_skillhub_signature",
            new=AsyncMock(return_value={"content_hash": "0" * 64}),
        ),
    ):
        with pytest.raises(SkillsMarketplaceError, match="fingerprint did not match"):
            await install_marketplace_skill(
                "skillhub", "good-skill", global_dir, provider="skillhub"
            )
    assert not (global_dir / "good-skill").exists()


async def test_install_skillhub_rejects_unsafe_redirect(tmp_path: Path) -> None:
    """A non-myqcloud redirect target must be refused before download."""
    global_dir = tmp_path / "manager-skills"
    zip_bytes = _build_zip_bytes({"good-skill/SKILL.md": "x"})
    client = _build_skillhub_mock_client(
        zip_bytes=zip_bytes, download_url="https://evil.example.com/x.zip"
    )
    with (
        patch.object(sm, "_skillhub_client", MagicMock(return_value=client)),
        patch.object(
            sm, "_skillhub_latest_version", new=AsyncMock(return_value="1.0.0")
        ),
        patch.object(
            sm,
            "_skillhub_signature",
            new=AsyncMock(return_value={"content_hash": "a" * 64}),
        ),
    ):
        with pytest.raises(SkillsMarketplaceError, match="unsafe download location"):
            await install_marketplace_skill(
                "skillhub", "good-skill", global_dir, provider="skillhub"
            )


async def test_install_skillhub_rejects_oversize_declared(tmp_path: Path) -> None:
    """A declared content-length over the cap is refused without reading body."""
    global_dir = tmp_path / "manager-skills"
    zip_bytes = _build_zip_bytes({"good-skill/SKILL.md": "x"})
    client = _build_skillhub_mock_client(zip_bytes=zip_bytes)
    # Override the stream response to advertise an oversized payload.
    oversize_response = _FakeStreamResponse(
        content=zip_bytes, headers={"content-length": str(50 * 1024 * 1024)}
    )
    client.stream = MagicMock(return_value=_FakeStreamCM(oversize_response))
    with (
        patch.object(sm, "_skillhub_client", MagicMock(return_value=client)),
        patch.object(
            sm, "_skillhub_latest_version", new=AsyncMock(return_value="1.0.0")
        ),
        patch.object(
            sm,
            "_skillhub_signature",
            new=AsyncMock(return_value={"content_hash": "a" * 64}),
        ),
    ):
        with pytest.raises(SkillsMarketplaceError, match="too large"):
            await install_marketplace_skill(
                "skillhub", "good-skill", global_dir, provider="skillhub"
            )


async def test_install_skillhub_already_installed_short_circuits(tmp_path: Path) -> None:
    """An existing SkillHub skill returns success without re-downloading."""
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "good-skill")

    # If the dispatcher tries to dial out, these mocks would not be enough,
    # so their mere presence confirms we never entered the download branch.
    client = _build_skillhub_mock_client(zip_bytes=b"")
    with (
        patch.object(sm, "_skillhub_client", MagicMock(return_value=client)),
        patch.object(
            sm, "_skillhub_latest_version", new=AsyncMock(return_value="should-not-call")
        ),
    ):
        result = await install_marketplace_skill(
            "skillhub", "good-skill", global_dir, provider="skillhub"
        )
    assert result == {
        "installed": True,
        "already_installed": True,
        "name": "good-skill",
        "provider": "skillhub",
    }
    client.get.assert_not_called()


async def test_install_skillhub_invalid_skill_name(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="invalid SkillHub skill name"):
        await install_marketplace_skill(
            "skillhub", "BAD_UPPER", tmp_path, provider="skillhub"
        )


async def test_install_skillhub_invalid_version(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="invalid SkillHub skill version"):
        await install_marketplace_skill(
            "skillhub", "good-skill", tmp_path, provider="skillhub", version="../bad"
        )


async def test_install_skillhub_rejects_bad_fingerprint_field(tmp_path: Path) -> None:
    """Signature payloads without a 64-hex content_hash are rejected."""
    global_dir = tmp_path / "manager-skills"
    client = _build_skillhub_mock_client(zip_bytes=b"")
    with (
        patch.object(sm, "_skillhub_client", MagicMock(return_value=client)),
        patch.object(
            sm, "_skillhub_latest_version", new=AsyncMock(return_value="1.0.0")
        ),
        patch.object(
            sm,
            "_skillhub_signature",
            new=AsyncMock(return_value={"content_hash": "not-a-hex"}),
        ),
    ):
        with pytest.raises(SkillsMarketplaceError, match="valid package fingerprint"):
            await install_marketplace_skill(
                "skillhub", "good-skill", global_dir, provider="skillhub"
            )


# ---------------------------------------------------------------------------
# Install — skills.sh CLI (Task 1 spike conclusion B: cwd=tmp + shutil.move)
# ---------------------------------------------------------------------------


async def test_install_skills_sh_moves_to_global(tmp_path: Path) -> None:
    """skills.sh output is moved from ``<tmp>/skills/<id>`` into ``global_dir``."""
    global_dir = tmp_path / "manager-skills"
    body = "---\ndescription: d\n---\n"
    exec_fn = _make_subprocess_patch(skill_id="good-skill", body=body)
    with (
        patch.object(sm.asyncio, "create_subprocess_exec", side_effect=exec_fn),
        patch.object(sm.shutil, "which", return_value="/usr/bin/npx"),
    ):
        result = await install_marketplace_skill(
            "owner/repo", "good-skill", global_dir, provider="skills_sh"
        )
    assert (global_dir / "good-skill" / "SKILL.md").read_text(encoding="utf-8") == body
    assert result == {
        "installed": True,
        "already_installed": False,
        "name": "good-skill",
    }


async def test_install_skills_sh_returncode_failure(tmp_path: Path) -> None:
    """A non-zero CLI exit surfaces a marketplace error carrying output tail."""
    global_dir = tmp_path / "manager-skills"

    async def _exec(*args, cwd=None, **kwargs):
        proc = MagicMock()
        proc.returncode = 1

        async def _communicate():
            return (b"boom\nline2\nline3\nline4", b"")

        proc.communicate = _communicate
        proc.kill = MagicMock()
        return proc

    with (
        patch.object(sm.asyncio, "create_subprocess_exec", side_effect=_exec),
        patch.object(sm.shutil, "which", return_value="/usr/bin/npx"),
    ):
        with pytest.raises(SkillsMarketplaceError, match="failed") as exc:
            await install_marketplace_skill(
                "owner/repo", "bad-skill", global_dir, provider="skills_sh"
            )
    # Only the last 3 non-blank lines of CLI output are surfaced.
    assert "boom" not in exc.value.message
    assert "line2 · line3 · line4" in exc.value.message
    assert exc.value.status == 502
    assert not (global_dir / "bad-skill").exists()


async def test_install_skills_sh_cli_drops_nothing(tmp_path: Path) -> None:
    """If the CLI exits 0 but wrote no skill dir, install fails loudly."""
    global_dir = tmp_path / "manager-skills"

    async def _exec(*args, cwd=None, **kwargs):
        proc = MagicMock()
        proc.returncode = 0

        async def _communicate():
            return (b"ok", b"")

        proc.communicate = _communicate
        proc.kill = MagicMock()
        return proc

    with (
        patch.object(sm.asyncio, "create_subprocess_exec", side_effect=_exec),
        patch.object(sm.shutil, "which", return_value="/usr/bin/npx"),
    ):
        with pytest.raises(SkillsMarketplaceError, match="not found"):
            await install_marketplace_skill(
                "owner/repo", "ghost-skill", global_dir, provider="skills_sh"
            )
    assert not (global_dir / "ghost-skill").exists()


async def test_install_skills_sh_no_npx(tmp_path: Path) -> None:
    with patch.object(sm.shutil, "which", return_value=None):
        with pytest.raises(SkillsMarketplaceError, match="npx"):
            await install_marketplace_skill(
                "owner/repo", "good-skill", tmp_path, provider="skills_sh"
            )


async def test_install_skills_sh_invalid_source(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="invalid skill source"):
        await install_marketplace_skill("bad", "good-skill", tmp_path, provider="skills_sh")


async def test_install_skills_sh_invalid_skill_name(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="invalid skill name"):
        await install_marketplace_skill(
            "owner/repo", "BAD_UPPER", tmp_path, provider="skills_sh"
        )


async def test_install_skills_sh_already_installed_short_circuits(tmp_path: Path) -> None:
    """An already-installed skill returns success without invoking the CLI."""
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "good-skill")

    async def _never(*_args, **_kwargs):
        raise AssertionError("subprocess should not be launched when already installed")

    with (
        patch.object(sm.asyncio, "create_subprocess_exec", side_effect=_never),
        patch.object(sm.shutil, "which", return_value="/usr/bin/npx"),
    ):
        result = await install_marketplace_skill(
            "owner/repo", "good-skill", global_dir, provider="skills_sh"
        )
    assert result == {"installed": True, "already_installed": True, "name": "good-skill"}
    # Already-installed skill body is untouched.
    assert (global_dir / "good-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "---\ndescription: x\n---\n"


async def test_install_skills_sh_target_dir_exists_raises(tmp_path: Path) -> None:
    """A pre-existing target directory (without SKILL.md) is a conflict."""
    global_dir = tmp_path / "manager-skills"
    (global_dir / "good-skill").mkdir(parents=True)

    async def _never(*_args, **_kwargs):
        raise AssertionError("subprocess should not be launched on conflict")

    with (
        patch.object(sm.asyncio, "create_subprocess_exec", side_effect=_never),
        patch.object(sm.shutil, "which", return_value="/usr/bin/npx"),
    ):
        with pytest.raises(SkillsMarketplaceError, match="already exists"):
            await install_marketplace_skill(
                "owner/repo", "good-skill", global_dir, provider="skills_sh"
            )


# ---------------------------------------------------------------------------
# Install — dispatcher routing
# ---------------------------------------------------------------------------


async def test_install_marketplace_rejects_all_provider(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="provider"):
        await install_marketplace_skill(
            "owner/repo", "good-skill", tmp_path, provider="all"
        )


async def test_install_marketplace_rejects_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="provider"):
        await install_marketplace_skill(
            "owner/repo", "good-skill", tmp_path, provider="bogus"
        )
