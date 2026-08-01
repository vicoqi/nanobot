# Admin Skills Marketplace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 manager 后台为超级管理员增加全局 skills 市场（Discover + Installed），admin 从 skills.sh/SkillHub 下载 skill 进全局仓库，供所有 agent skills tab 选装。

**Architecture:** 移植上游 `skills_marketplace.py` 的搜索/trending/下载校验逻辑到 manager 服务层，把 per-workspace 安装改为「下载到全局仓库」；agent 侧 skills 扫描改指向全局仓库，symlink 安装机制不变。前端在 AdminPage 加 skills tab（Discover/Installed 子 tab）。

**Tech Stack:** Python 3.11+ / asyncio / FastAPI / httpx / pytest（后端）；React + TypeScript + Vite + Tailwind + shadcn（webui-manager 前端）

## Global Constraints

- Python 3.11+，asyncio 全异步；行宽 100；ruff 规则 E/F/I/N/W（E501 ignored）。
- 测试遵循项目惯例：pytest，`asyncio_mode = "auto"`，用 `assert`（与 `tests/` 现有一致）。网络层用 httpx mock（respx 或 monkeypatch），不真连远程。
- 上游移植来源：`HKUDS/nanobot` main 分支（分叉点 `2144af7c` 之后）。移植时**合并**到本仓库文件，不覆盖本仓库既有改动。
- 全局仓库路径：`ManagerConfig.data_dir / "manager-skills"`（即 `~/.nanobot/manager-skills/`）。
- agent workspace skills 目录：`<workspace>/skills/`（现有，不变）。

---

## File Structure

**后端 — 创建/修改：**
- Modify `nanobot/manager/services/skills.py` — 全局仓库路径参数化，scan/install/uninstall 指向全局仓库
- Modify `nanobot/manager/api/agents.py` — skills 端点传入全局仓库路径
- Modify `nanobot/security/network.py` — 合并移植 `PinnedDNSAsyncTransport`
- Create `nanobot/manager/services/skills_marketplace.py` — 移植上游市场逻辑（搜索/trending/下载/install-to-global）
- Create `nanobot/manager/api/marketplace.py` — admin 市场 API 端点
- Modify `nanobot/manager/app.py` — 注册 marketplace router

**前端 — 创建/修改：**
- Modify `webui-manager/src/lib/api.ts` — 市场 API 客户端 + 类型
- Create `webui-manager/src/components/SkillsDiscover.tsx` — Discover 视图
- Create `webui-manager/src/components/SkillsInstalled.tsx` — Installed 视图
- Modify `webui-manager/src/pages/AdminPage.tsx` — 加 skills tab + 子 tab
- Modify `webui-manager/src/i18n/en.ts`、`zh.ts` — i18n key

**测试 — 创建：**
- `tests/manager/test_skills_global.py`、`tests/manager/test_skills_marketplace.py`、`tests/manager/test_marketplace_api.py`

---

## Task 1: Spike — 验证 skills.sh CLI 目标目录能力

**目的**：上游 `_install_skills_sh_skill` 用 `npx` 跑官方 skills CLI，默认装到 `<workspace>/skills`。改成「装到全局仓库」前，必须确认 CLI 能接受自定义目标目录。此任务**决定 Task 5 的 skills.sh 策略**，必须最先做。

**Files:** 无代码改动，产出调研结论记入本文件末尾「Spike 结论」。

- [ ] **Step 1: 查 CLI 帮助**

 Run（服务器，已有 npx 10.9.8）:
 ```bash
 npx -y @anthropic-ai/skills@latest --help 2>&1 | head -40
 # 若包名不对，试: npx -y skills@latest --help
 ```
 上游代码用的是 `npx` + `_CLI_AGENT="openclaw"`，先在源码确认确切包名/命令：拉上游 `_install_skills_sh_skill` 完整实现（`gh api repos/HKUDS/nanobot/contents/nanobot/webui/skills_marketplace.py` 看 L370-410）。

- [ ] **Step 2: 试装一个 skill 到自定义目录**

 用上游的调用方式，把目标指到一个临时全局仓库目录：
 ```bash
 mkdir -p /tmp/spike-global
 # 按 CLI 实际参数尝试（例如 --target / --out / --dest / 或以 cwd 调用）
 npx -y <skills-cli> install <some-skill> --target /tmp/spike-global
 ls /tmp/spike-global
 ```

- [ ] **Step 3: 记录结论到本文件「Spike 结论」段**

 三种结果之一：
 - **A. CLI 支持自定义目标** → Task 5 直接用，skills.sh 源完整支持。
 - **B. CLI 仅装到 `<cwd>/skills`** → Task 5 以全局仓库为 cwd 调用（`subprocess cwd=global_dir`），或 `global_dir/skills` 后搬迁。
 - **C. CLI 完全无法控制目标** → Task 5 skills.sh 降级为「仅搜索展示」，安装只走 SkillHub；spec 的降级条款生效。

> ⚠️ 阻塞：Task 5 依赖本任务结论。若跳过，Task 5 的 skills.sh 部分无法定稿。

---

## Task 2: 全局仓库基础设施（skills.py 改造）

把 skills 服务从「扫描包内只读目录」改为「扫描全局仓库路径」，路径由调用方（API 层，持有 config）注入。

**Files:**
- Modify: `nanobot/manager/services/skills.py`
- Modify: `nanobot/manager/api/agents.py`（3 个 skills 端点调用处）
- Test: `tests/manager/test_skills_global.py`

**Interfaces:**
- Produces（供后续 Task）:
  - `scan_available_skills(global_dir: Path) -> list[dict]`
  - `get_installed_skill_names(workspace_path: Path) -> set[str]`（不变）
  - `install_skill(skill_name: str, workspace_path: Path, global_dir: Path) -> None`
  - `uninstall_skill(skill_name: str, workspace_path: Path) -> None`（不变）
  - `global_skills_dir(config) -> Path`：返回 `config.data_dir / "manager-skills"`（新 helper，集中路径规则）

- [ ] **Step 1: 写失败测试 `tests/manager/test_skills_global.py`**

 ```python
 import pytest
 from pathlib import Path
 from nanobot.manager.services.skills import (
     scan_available_skills, install_skill, uninstall_skill,
     get_installed_skill_names, global_skills_dir,
 )
 from nanobot.manager.config import ManagerConfig

 def _make_skill(global_dir: Path, name: str, desc: str = "test"):
     d = global_dir / name
     d.mkdir(parents=True)
     (d / "SKILL.md").write_text(f"---\ndescription: {desc}\n---\nbody", encoding="utf-8")

 def test_scan_reads_global_dir(tmp_path):
     global_dir = tmp_path / "manager-skills"
     _make_skill(global_dir, "alpha")
     result = scan_available_skills(global_dir)
     assert [s["name"] for s in result] == ["alpha"]
     assert result[0]["description"] == "test"

 def test_install_symlinks_from_global_to_workspace(tmp_path):
     global_dir = tmp_path / "manager-skills"
     workspace = tmp_path / "ws"
     (workspace / "skills").mkdir(parents=True)
     _make_skill(global_dir, "alpha")
     install_skill("alpha", workspace, global_dir)
     installed = get_installed_skill_names(workspace)
     assert "alpha" in installed
     # 确认是 symlink 指向全局仓库
     assert (workspace / "skills" / "alpha").is_symlink()

 def test_global_skills_dir_uses_config(tmp_path, monkeypatch):
     cfg = ManagerConfig()
     monkeypatch.setattr(cfg, "_config_path", tmp_path / "manager-config.json")
     assert global_skills_dir(cfg) == tmp_path / "manager-skills"
 ```

- [ ] **Step 2: 运行测试看失败**

 Run: `pytest tests/manager/test_skills_global.py -v`
 Expected: FAIL（`global_skills_dir` 不存在 / `install_skill` 参数不匹配）

- [ ] **Step 3: 改造 `skills.py`**

 ```python
 # 顶部新增
 from pathlib import Path
 # MANAGER_SKILLS_DIR 常量删除（不再扫描包内目录）

 def global_skills_dir(config) -> Path:
     return config.data_dir / "manager-skills"

 def scan_available_skills(global_dir: Path) -> list[dict]:
     skills: list[dict] = []
     if not global_dir.is_dir():
         return skills
     for skill_dir in sorted(global_dir.iterdir()):
         if not skill_dir.is_dir():
             continue
         skill_file = skill_dir / "SKILL.md"
         if not skill_file.exists():
             continue
         content = skill_file.read_text(encoding="utf-8")
         frontmatter = _parse_frontmatter(content) or {}
         skills.append({
             "name": skill_dir.name,
             "description": frontmatter.get("description", skill_dir.name),
         })
     return skills

 def install_skill(skill_name: str, workspace_path: str, global_dir: Path) -> None:
     src = Path(global_dir) / skill_name          # 源改为全局仓库
     if not src.is_dir():
         raise FileNotFoundError(f"Skill not found: {skill_name}")
     dst = Path(workspace_path) / "skills" / skill_name
     dst.parent.mkdir(parents=True, exist_ok=True)
     try:
         os.symlink(src.resolve(), dst)
     except FileExistsError:
         raise FileExistsError(f"Skill already installed: {skill_name}") from None
     logger.info("Installed skill '{}' to {}", skill_name, workspace_path)
 # uninstall_skill、get_installed_skill_names 保持不变
 ```

- [ ] **Step 4: 改造 `agents.py` 调用处**

 `list_available_skills` / `install_skill_endpoint` / `uninstall_skill_endpoint` 三个端点内，取 `config = get_config()`、`gdir = global_skills_dir(config)`，传入 `scan_available_skills(gdir)` / `install_skill(req.skill_name, agent.workspace_path, gdir)`。`install_skill` 导入签名更新。

- [ ] **Step 5: 运行测试看通过**

 Run: `pytest tests/manager/test_skills_global.py tests/manager/test_api.py -v`
 Expected: PASS

- [ ] **Step 6: Commit**

 ```bash
 git add nanobot/manager/services/skills.py nanobot/manager/api/agents.py tests/manager/test_skills_global.py
 git commit -m "refactor(manager): point skills scan/install at global skills dir"
 ```

---

## Task 3: 移植 PinnedDNSAsyncTransport

从上游 `security/network.py` 移植该类，**合并**进本仓库 `network.py`（本仓库 network.py 已有自定义改动，不可覆盖）。

**Files:**
- Modify: `nanobot/security/network.py`（追加类）
- Test: `tests/security/test_pinned_dns_transport.py`

**Interfaces:**
- Produces: `PinnedDNSAsyncTransport`（httpx AsyncBaseTransport 子类，构造接收主机→IP 映射或解析规则；供 Task 4 的 `_skills_client`/`_skillhub_client` 使用）

- [ ] **Step 1: 取上游实现**

 ```bash
 gh api repos/HKUDS/nanobot/contents/nanobot/security/network.py --jq '.content' | base64 -d > /tmp/upstream_network.py
 # 提取 PinnedDNSAsyncTransport 类（class 体 + 其依赖的辅助函数/常量）
 grep -n "class PinnedDNSAsyncTransport" /tmp/upstream_network.py
 ```

- [ ] **Step 2: 写失败测试**

 ```python
 # tests/security/test_pinned_dns_transport.py
 import httpx, pytest
 from nanobot.security.network import PinnedDNSAsyncTransport

 def test_transport_is_httpx_transport():
     t = PinnedDNSAsyncTransport({})  # 构造参数依上游实际签名
     assert isinstance(t, httpx.AsyncBaseTransport)

 def test_transport_rejects_unpinned_host():
     # 具体断言依上游行为：未在 pin 映射中的主机应被拒绝/不解析
     t = PinnedDNSAsyncTransport({"skills.sh": "1.2.3.4"})
     # 用 mock 或 transport.handle_async_request 验证行为（依上游实现细化）
 ```

- [ ] **Step 3: 运行看失败** — `pytest tests/security/test_pinned_dns_transport.py -v` → FAIL（类未导入）

- [ ] **Step 4: 合并移植**

 把上游 `PinnedDNSAsyncTransport` 类（及其私有依赖）追加到本仓库 `nanobot/security/network.py` 末尾。**保留**本仓库 network.py 原有全部内容（SSRF 检查等）。如上游用到的辅助函数本仓库已有同名，复用；否则一并搬入。

- [ ] **Step 5: 运行看通过** — `pytest tests/security/test_pinned_dns_transport.py tests/security/test_security_network.py -v` → PASS

- [ ] **Step 6: Commit**

 ```bash
 git add nanobot/security/network.py tests/security/test_pinned_dns_transport.py
 git commit -m "feat(security): port PinnedDNSAsyncTransport from upstream"
 ```

---

## Task 4: 移植市场搜索/trending

移植搜索与热门拉取逻辑，把 `workspace_path` 语义改为「全局仓库路径」（用于已装标记）。

**Files:**
- Create: `nanobot/manager/services/skills_marketplace.py`
- Test: `tests/manager/test_skills_marketplace.py`

**Interfaces:**
- Produces（签名保持上游，仅 `workspace_path` 改语义为 `global_dir`）:
  - `async search_marketplace_skills(query: str, global_dir: Path, *, limit: int = 20, provider: str = "all") -> dict[str, Any]`
  - `async trending_marketplace_skills(global_dir: Path, *, limit: int = 8, provider: str = "all") -> dict[str, Any]`
  - `def skills_install_supported() -> bool`

- [ ] **Step 1: 写失败测试（mock httpx）**

 ```python
 # tests/manager/test_skills_marketplace.py
 import pytest
 from pathlib import Path
 from unittest.mock import AsyncMock, patch
 import httpx

 @pytest.mark.asyncio
 async def test_search_returns_and_marks_installed(tmp_path):
     global_dir = tmp_path / "manager-skills"
     (global_dir / "already-installed").mkdir(parents=True)
     (global_dir / "already-installed" / "SKILL.md").write_text("---\ndescription: x\n---\n")

     fake_resp = httpx.Response(200, json={
         "results": [{"id": "already-installed", "name": "Already", "description": "d"},
                     {"id": "new-one", "name": "New", "description": "d2"}]
     })
     with patch("nanobot.manager.services.skills_marketplace._skills_client") as mk:
         client = AsyncMock(); client.get = AsyncMock(return_value=fake_resp)
         client.__aenter__ = AsyncMock(return_value=client); client.__aexit__ = AsyncMock()
         mk.return_value = client
         from nanobot.manager.services.skills_marketplace import search_marketplace_skills
         result = await search_marketplace_skills("q", global_dir)
     names = {s["id"]: s for s in result["results"]}
     assert names["already-installed"]["installed"] is True
     assert names["new-one"]["installed"] is False
 ```

- [ ] **Step 2: 运行看失败** — `pytest tests/manager/test_skills_marketplace.py -v` → FAIL（模块不存在）

- [ ] **Step 3: 移植搜索/trending**

 从上游 `skills_marketplace.py` 移植到 `nanobot/manager/services/skills_marketplace.py`：
 - 常量（`_PROVIDER_ALL`、`_PROVIDER_SKILLS_SH`、`_PROVIDER_SKILLHUB`、各 URL）
 - `_response_json_object`、`SkillsMarketplaceError`
 - `_skills_client`、`_skillhub_client`（用 Task 3 的 `PinnedDNSAsyncTransport`）
 - `skills_install_supported`
 - `search_marketplace_skills` + `_search_skills_sh_skills` + `_search_skillhub_skills`
 - `trending_marketplace_skills` + `_trending_skills_sh_skills` + `_trending_skillhub_skills`
 - `marketplace_skill_trends` + `_load_weekly_installs` + `_load_skill_page_trends`
 - 各 `_valid_*` 校验函数

 **关键适配**：把内部 `_installed_skill_names(workspace_path)` 改为读 `global_dir` 直接（全局仓库下 skill 名 = 目录名）：
 ```python
 def _installed_skill_names(global_dir: Path) -> set[str]:
     if not global_dir.is_dir():
         return set()
     return {d.name for d in global_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()}
 ```

- [ ] **Step 4: 运行看通过** — `pytest tests/manager/test_skills_marketplace.py -v` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add nanobot/manager/services/skills_marketplace.py tests/manager/test_skills_marketplace.py
 git commit -m "feat(manager): port marketplace search/trending to global skills dir"
 ```

---

## Task 5: 移植市场安装（SkillHub + skills.sh）

移植下载/校验/解压逻辑，install 目标改为全局仓库。

**Files:**
- Modify: `nanobot/manager/services/skills_marketplace.py`（追加 install 部分）
- Test: `tests/manager/test_skills_marketplace.py`（追加 install 用例）

**Interfaces:**
- Produces:
  - `async install_marketplace_skill(source: str, skill_id: str, global_dir: Path, *, provider: str = "skills_sh", version: str = "") -> dict[str, Any]`

- [ ] **Step 1: 写失败测试（mock 下载，含恶意路径拒绝）**

 ```python
 @pytest.mark.asyncio
 async def test_install_skillhub_downloads_to_global(tmp_path):
     global_dir = tmp_path / "manager-skills"
     # 构造一个合法 zip（含 SKILL.md），mock _skillhub_client 返回 zip 字节
     import zipfile, io
     buf = io.BytesIO()
     with zipfile.ZipFile(buf, "w") as z:
         z.writestr("good-skill/SKILL.md", "---\ndescription: d\n---\n")
     fake = httpx.Response(200, content=buf.getvalue())
     with patch("nanobot.manager.services.skills_marketplace._skillhub_client") as mk, \
          patch("nanobot.manager.services.skills_marketplace._skillhub_signature", new=AsyncMock(return_value=("sig","ver"))), \
          patch("nanobot.manager.services.skills_marketplace._skillhub_latest_version", new=AsyncMock(return_value="1.0")):
         client = AsyncMock(); client.get = AsyncMock(return_value=fake)
         client.__aenter__ = AsyncMock(return_value=client); client.__aexit__ = AsyncMock()
         mk.return_value = client
         from nanobot.manager.services.skills_marketplace import install_marketplace_skill
         result = await install_marketplace_skill("skillhub", "good-skill", global_dir, provider="skillhub")
     assert (global_dir / "good-skill" / "SKILL.md").exists()
     assert result["success"] is True

 def test_install_rejects_path_traversal(tmp_path):
     # 构造含 ../../etc/passwd 条目的 zip，断言抛 SkillsMarketplaceError
     ...
 ```

- [ ] **Step 2: 运行看失败** — `pytest tests/manager/test_skills_marketplace.py -v` → FAIL

- [ ] **Step 3: 移植 install 逻辑**

 从上游移植：
 - `install_marketplace_skill`、`_install_skillhub_skill`、`_skillhub_latest_version`、`_skillhub_signature`、`_download_skillhub_archive`、`_validate_skillhub_archive`、`_extract_skillhub_archive`、`_skillhub_hash_ignored`、`_valid_skillhub_download_url`、`_validated_skillhub_entries`
 - **适配**：解压目标从 `<workspace>/skills/<name>` 改为 `<global_dir>/<name>`；`require_path_within` 的边界改为 `global_dir`。
 - **skills.sh**（依据 Task 1 结论）：
   - 结论 A：`_install_skills_sh_skill` 用 CLI 的 `--target` 指向 `global_dir`
   - 结论 B：`subprocess` 以 `cwd=global_dir` 或 `cwd=global_dir.parent` 调用，必要时从 `global_dir/skills/<name>` 搬到 `global_dir/<name>`
   - 结论 C：`_install_skills_sh_skill` 抛 `SkillsMarketplaceError("skills.sh install unsupported on this host")`，Discover 页对 skills.sh 结果隐藏安装按钮（Task 9 处理 UI）

- [ ] **Step 4: 运行看通过** — `pytest tests/manager/test_skills_marketplace.py -v` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add nanobot/manager/services/skills_marketplace.py tests/manager/test_skills_marketplace.py
 git commit -m "feat(manager): port marketplace install to global skills dir"
 ```

---

## Task 6: admin 市场 API 端点

**Files:**
- Create: `nanobot/manager/api/marketplace.py`
- Modify: `nanobot/manager/app.py`（注册 router）
- Test: `tests/manager/test_marketplace_api.py`

**Interfaces:**
- Consumes: Task 4/5 的 `search_marketplace_skills` / `trending_marketplace_skills` / `install_marketplace_skill`；Task 2 的 `global_skills_dir`、`scan_available_skills`
- Produces（HTTP）:
  - `GET /api/admin/skills/marketplace/search?q=&source=`
  - `GET /api/admin/skills/marketplace/trending?source=`
  - `POST /api/admin/skills/marketplace/install` body `{skillId, source, provider?, version?}`
  - `GET /api/admin/skills`（Installed 列表）
  - `DELETE /api/admin/skills/{name}`（Task 7 实现清理）

- [ ] **Step 1: 写失败测试**

 ```python
 # tests/manager/test_marketplace_api.py
 import pytest
 from unittest.mock import AsyncMock, patch

 @pytest.mark.asyncio
 async def test_search_endpoint_requires_admin(async_client, no_auth):
     r = await async_client.get("/api/admin/skills/marketplace/search?q=x")
     assert r.status_code == 401

 @pytest.mark.asyncio
 async def test_search_endpoint_returns_results(async_client, admin_auth):
     with patch("nanobot.manager.api.marketplace.search_marketplace_skills",
                new=AsyncMock(return_value={"results": [{"id":"a","installed":False}]})):
         r = await async_client.get("/api/admin/skills/marketplace/search?q=x")
     assert r.status_code == 200
     assert r.json()["results"][0]["id"] == "a"

 @pytest.mark.asyncio
 async def test_installed_endpoint_lists_global(async_client, admin_auth, tmp_global):
     r = await async_client.get("/api/admin/skills")
     assert r.status_code == 200
 ```

 （`async_client` / `admin_auth` / `tmp_global` fixtures 参考 `tests/manager/test_api.py` 既有模式；若无 admin auth helper，按 `test_api.py` 的鉴权设置方式补。）

- [ ] **Step 2: 运行看失败** — `pytest tests/manager/test_marketplace_api.py -v` → FAIL（路由 404）

- [ ] **Step 3: 实现端点**

 ```python
 # nanobot/manager/api/marketplace.py
 from fastapi import APIRouter, Depends, HTTPException
 from pydantic import BaseModel
 from nanobot.manager.app import get_config
 from nanobot.manager.auth import get_current_admin
 from nanobot.manager.services.skills import global_skills_dir, scan_available_skills, uninstall_skill
 from nanobot.manager.services.skills_marketplace import (
     search_marketplace_skills, trending_marketplace_skills, install_marketplace_skill,
 )

 router = APIRouter(prefix="/api/admin/skills", tags=["admin-skills"])

 class InstallRequest(BaseModel):
     skillId: str
     source: str
     provider: str = "skills_sh"
     version: str = ""

 @router.get("/marketplace/search")
 async def search(q: str, source: str = "all", payload: dict = Depends(get_current_admin)):
     config = get_config()
     return await search_marketplace_skills(q, global_skills_dir(config), provider=source)

 @router.get("/marketplace/trending")
 async def trending(source: str = "all", payload: dict = Depends(get_current_admin)):
     config = get_config()
     return await trending_marketplace_skills(global_skills_dir(config), provider=source)

 @router.post("/marketplace/install")
 async def install(req: InstallRequest, payload: dict = Depends(get_current_admin)):
     config = get_config()
     from nanobot.manager.services.skills_marketplace import SkillsMarketplaceError
     try:
         return await install_marketplace_skill(req.source, req.skillId, global_skills_dir(config),
                                                provider=req.provider, version=req.version)
     except SkillsMarketplaceError as e:
         raise HTTPException(status_code=400, detail=str(e))

 @router.get("")
 async def installed(payload: dict = Depends(get_current_admin)):
     config = get_config()
     return {"skills": scan_available_skills(global_skills_dir(config))}

 # DELETE /{name} 在 Task 7 完成
 ```
 在 `app.py` 注册：`from nanobot.manager.api.marketplace import router as marketplace_router` 并 `app.include_router(marketplace_router)`。

- [ ] **Step 4: 运行看通过** — `pytest tests/manager/test_marketplace_api.py -v` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add nanobot/manager/api/marketplace.py nanobot/manager/app.py tests/manager/test_marketplace_api.py
 git commit -m "feat(manager): add admin marketplace API endpoints"
 ```

---

## Task 7: 卸载连带清理（决策 5a）

卸载全局 skill 时，遍历所有 agent workspace 清理断链 symlink，再删全局仓库目录。

**Files:**
- Modify: `nanobot/manager/services/skills.py`（新增 `uninstall_global_skill`）
- Modify: `nanobot/manager/api/marketplace.py`（DELETE 端点接通）
- Test: `tests/manager/test_skills_global.py`（追加）

**Interfaces:**
- Produces: `uninstall_global_skill(skill_name: str, global_dir: Path, workspaces_dir: Path) -> int`（返回清理的 symlink 数）

- [ ] **Step 1: 写失败测试**

 ```python
 def test_uninstall_global_cleans_all_workspaces(tmp_path):
     global_dir = tmp_path / "manager-skills"
     workspaces = tmp_path / "workspaces"
     _make_skill(global_dir, "alpha")
     # 两个 agent workspace 都 symlink 了 alpha
     for ws in ["agent-1", "agent-2"]:
         ws_dir = workspaces / ws; (ws_dir / "skills").mkdir(parents=True)
         (ws_dir / "skills" / "alpha").symlink_to((global_dir / "alpha").resolve())
     from nanobot.manager.services.skills import uninstall_global_skill
     cleaned = uninstall_global_skill("alpha", global_dir, workspaces)
     assert cleaned == 2
     assert not (global_dir / "alpha").exists()
     assert not (workspaces / "agent-1" / "skills" / "alpha").exists()

 def test_uninstall_global_tolerates_missing(tmp_path):
     from nanobot.manager.services.skills import uninstall_global_skill
     cleaned = uninstall_global_skill("nope", tmp_path, tmp_path)  # 不存在不抛
     assert cleaned == 0
 ```

- [ ] **Step 2: 运行看失败** — `pytest tests/manager/test_skills_global.py::test_uninstall_global_cleans_all_workspaces -v` → FAIL

- [ ] **Step 3: 实现 `uninstall_global_skill`**

 ```python
 def uninstall_global_skill(skill_name: str, global_dir: Path, workspaces_dir: Path) -> int:
     cleaned = 0
     # ① 清所有 workspace 的 symlink
     if workspaces_dir.is_dir():
         for ws in workspaces_dir.iterdir():
             link = ws / "skills" / skill_name
             if link.is_symlink():
                 try:
                     link.unlink(); cleaned += 1
                 except OSError:
                     pass
     # ② 删全局仓库目录
     target = Path(global_dir) / skill_name
     if target.exists():
         shutil.rmtree(target, ignore_errors=True)
     logger.info("Uninstalled global skill '{}', cleaned {} workspace symlinks", skill_name, cleaned)
     return cleaned
 ```

- [ ] **Step 4: 接通 DELETE 端点**

 ```python
 # marketplace.py
 from nanobot.manager.services.skills import uninstall_global_skill

 @router.delete("/{skill_name}")
 async def uninstall(skill_name: str, payload: dict = Depends(get_current_admin)):
     config = get_config()
     cleaned = uninstall_global_skill(skill_name, global_skills_dir(config), config.workspaces_dir)
     return {"success": True, "cleanedWorkspaces": cleaned}
 ```

- [ ] **Step 5: 运行看通过** — `pytest tests/manager/test_skills_global.py tests/manager/test_marketplace_api.py -v` → PASS

- [ ] **Step 6: Commit**

 ```bash
 git add nanobot/manager/services/skills.py nanobot/manager/api/marketplace.py tests/manager/test_skills_global.py
 git commit -m "feat(manager): cascade-clean workspace symlinks on global skill uninstall"
 ```

---

## Task 8: 前端 API 客户端 + 类型

**Files:**
- Modify: `webui-manager/src/lib/api.ts`
- Modify: `webui-manager/src/tests/api.test.ts`

**Interfaces:**
- Produces:
  - `searchMarketplace(q: string, source?: string): Promise<{results: MarketplaceSkill[]}>`
  - `trendingMarketplace(source?: string): Promise<{results: MarketplaceSkill[]}>`
  - `installMarketplaceSkill(skillId: string, source: string, provider?: string): Promise<{success: boolean}>`
  - `listInstalledSkills(): Promise<{skills: InstalledSkill[]}>`
  - `uninstallGlobalSkill(name: string): Promise<{success: boolean, cleanedWorkspaces: number}>`
  - 类型 `MarketplaceSkill`、`InstalledSkill`

- [ ] **Step 1: 写失败测试 `api.test.ts`**

 ```typescript
 import { describe, it, expect, vi, beforeEach } from "vitest";
 import { searchMarketplace, installMarketplaceSkill } from "@/lib/api";

 beforeEach(() => {
   global.fetch = vi.fn();
   localStorage.setItem("adminToken", "T"); // 依现有 auth 存储方式
 });

 it("searchMarketplace calls admin skills search", async () => {
   (global.fetch as any).mockResolvedValue({ ok: true, json: async () => ({ results: [{ id: "x", installed: false }] }) });
   const r = await searchMarketplace("q");
   expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/api/admin/skills/marketplace/search?q=q"), expect.any(Object));
   expect(r.results[0].id).toBe("x");
 });
 ```

- [ ] **Step 2: 运行看失败** — `cd webui-manager && bun run test -- api.test` → FAIL（函数不存在）

- [ ] **Step 3: 实现 api.ts**

 参照现有 `api.ts` 的 fetch 封装与 admin token 注入模式，新增上述 5 个函数 + 2 个类型（`MarketplaceSkill { id, name, description, installed, provider?, source? }`、`InstalledSkill { name, description }`）。

- [ ] **Step 4: 运行看通过** — `bun run test -- api.test` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add webui-manager/src/lib/api.ts webui-manager/src/tests/api.test.ts
 git commit -m "feat(webui-manager): add marketplace API client and types"
 ```

---

## Task 9: Discover 视图组件

**Files:**
- Create: `webui-manager/src/components/SkillsDiscover.tsx`
- Test: `webui-manager/src/tests/skills-discover.test.tsx`

- [ ] **Step 1: 写失败测试**

 ```typescript
 // skills-discover.test.tsx
 import { render, screen, waitFor } from "@testing-library/react";
 import { describe, it, expect, vi } from "vitest";
 import SkillsDiscover from "@/components/SkillsDiscover";

 describe("SkillsDiscover", () => {
   it("renders search results", async () => {
     vi.mock("@/lib/api", () => ({
       searchMarketplace: vi.fn().mockResolvedValue({ results: [{ id: "s1", name: "Skill One", description: "d", installed: false }] }),
       trendingMarketplace: vi.fn().mockResolvedValue({ results: [] }),
     }));
     render(<SkillsDiscover />);
     await waitFor(() => expect(screen.getByText("Skill One")).toBeInTheDocument());
   });

   it("disables install button for already-installed", async () => {
     vi.mock("@/lib/api", () => ({
       searchMarketplace: vi.fn().mockResolvedValue({ results: [{ id: "s1", name: "X", description: "", installed: true }] }),
       trendingMarketplace: vi.fn().mockResolvedValue({ results: [] }),
       installMarketplaceSkill: vi.fn(),
     }));
     render(<SkillsDiscover />);
     await waitFor(() => expect(screen.getByText("X")).toBeInTheDocument());
     // 已装置灰（具体依实现：button disabled 或文案「已安装」）
   });
 });
 ```

- [ ] **Step 2: 运行看失败** — `bun run test -- skills-discover` → FAIL

- [ ] **Step 3: 实现 `SkillsDiscover.tsx`**

 包含：搜索框（受控，debounce）、源过滤按钮组（全部/skills.sh/SkillHub）、trending 区、结果卡片网格。每张卡片：name / description / 来源标签 / 安装按钮（`installed` 时禁用并显示「已安装」；点击调 `installMarketplaceSkill`，loading 态）。**若 Task 1 结论为 C**，对 `provider === "skills_sh"` 的结果隐藏安装按钮、显示「仅可搜索」提示。

- [ ] **Step 4: 运行看通过** — `bun run test -- skills-discover` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add webui-manager/src/components/SkillsDiscover.tsx webui-manager/src/tests/skills-discover.test.tsx
 git commit -m "feat(webui-manager): add SkillsDiscover view"
 ```

---

## Task 10: Installed 视图组件

**Files:**
- Create: `webui-manager/src/components/SkillsInstalled.tsx`
- Test: `webui-manager/src/tests/skills-installed.test.tsx`

- [ ] **Step 1: 写失败测试**

 ```typescript
 // skills-installed.test.tsx
 import { render, screen, waitFor, fireEvent } from "@testing-library/react";
 import { describe, it, expect, vi } from "vitest";
 import SkillsInstalled from "@/components/SkillsInstalled";

 describe("SkillsInstalled", () => {
   it("lists installed skills and confirms before uninstall", async () => {
     const uninstallMock = vi.fn().mockResolvedValue({ success: true, cleanedWorkspaces: 2 });
     vi.mock("@/lib/api", () => ({
       listInstalledSkills: vi.fn().mockResolvedValue({ skills: [{ name: "alpha", description: "d" }] }),
       uninstallGlobalSkill: uninstallMock,
     }));
     vi.spyOn(window, "confirm").mockReturnValue(true);
     render(<SkillsInstalled />);
     await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
     fireEvent.click(screen.getByText(/uninstall|卸载/i));
     await waitFor(() => expect(uninstallMock).toHaveBeenCalledWith("alpha"));
   });
 });
 ```

- [ ] **Step 2: 运行看失败** — `bun run test -- skills-installed` → FAIL

- [ ] **Step 3: 实现 `SkillsInstalled.tsx`**

 `listInstalledSkills` 渲染卡片/行表；卸载按钮点击 → `window.confirm`（提示将清理 N 个 agent）→ `uninstallGlobalSkill` → 刷新。空状态文案。

- [ ] **Step 4: 运行看通过** — `bun run test -- skills-installed` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add webui-manager/src/components/SkillsInstalled.tsx webui-manager/src/tests/skills-installed.test.tsx
 git commit -m "feat(webui-manager): add SkillsInstalled view"
 ```

---

## Task 11: AdminPage 集成 skills tab

**Files:**
- Modify: `webui-manager/src/pages/AdminPage.tsx`
- Modify: `webui-manager/src/tests/app-layout.test.tsx`（或新增 admin-skills-tab 测试）

- [ ] **Step 1: 写失败测试**

 ```typescript
 it("shows skills tab with Discover/Installed subtabs", async () => {
   // 渲染 AdminPage（登录态），断言存在 skills tab 按钮，点击后出现 Discover/Installed 子按钮
 });
 ```

- [ ] **Step 2: 运行看失败**

- [ ] **Step 3: 改造 AdminPage**

 在现有 `tab` 状态扩展为 `"agents" | "users" | "skills"`，顶部加第三个 tab 按钮。`tab === "skills"` 时渲染内部子 tab（`"discover" | "installed"`，默认 discover），分别挂载 `<SkillsDiscover />` / `<SkillsInstalled />`。沿用现有 Button 风格。

- [ ] **Step 4: 运行看通过** — `bun run test` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add webui-manager/src/pages/AdminPage.tsx webui-manager/src/tests/app-layout.test.tsx
 git commit -m "feat(webui-manager): add skills tab to AdminPage"
 ```

---

## Task 12: i18n 文案

**Files:**
- Modify: `webui-manager/src/i18n/en.ts`、`zh.ts`
- Modify: `webui-manager/src/tests/i18n.test.tsx`

- [ ] **Step 1: 写失败测试** — 断言 en/zh 都有 `admin.skillsDiscover`、`admin.skillsInstalled`、`admin.install`、`admin.uninstall`、`admin.confirmUninstall`、`admin.searchPlaceholder`、`admin.sourceAll`、`admin.sourceSkillsSh`、`admin.sourceSkillhub`、`admin.installed`、`admin.noSkills` 等 key，且 en/zh key 集合一致。

- [ ] **Step 2: 运行看失败**

- [ ] **Step 3: 补 key**（en/zh 各一份，文案对照）

- [ ] **Step 4: 运行看通过** — `bun run test -- i18n` → PASS

- [ ] **Step 5: Commit**

 ```bash
 git add webui-manager/src/i18n/en.ts webui-manager/src/i18n/zh.ts webui-manager/src/tests/i18n.test.tsx
 git commit -m "feat(webui-manager): add i18n keys for skills marketplace"
 ```

---

## Spike 结论（Task 1 — 2026-08-01 实测）

- skills.sh CLI 包名/命令：`npx --yes skills@latest add <source> --skill <id> --agent openclaw --copy --yes`
- 目标目录支持：**方案 B**（CLI 无 `--target`；以 `cwd` 控制，实测装到 `<cwd>/skills/<id>/`；`--agent openclaw` 强制落 cwd 不落 user-global）
- skills.sh 安装策略（Task 5）：以 `cwd=临时目录` 跑 CLI → 装到 `tmp/skills/<id>/` → `shutil.move(tmp/skills/<id>, global_dir/<id>)`

---

## Self-Review

**1. Spec 覆盖**：架构（Tasks 2/4/5/6）✅；卸载连带清理 5a（Task 7）✅；UI 子 tab 6a（Tasks 9/10/11）✅；i18n（Task 12）✅；安全校验（随 Task 4/5 移植）✅；Discover/Installed（Tasks 9/10）✅；agent 侧扫描改全局仓库（Task 2）✅；PinnedDNS（Task 3）✅。无遗漏。

**2. 占位符**：无 TBD/TODO（Spike 结论段为 Task 1 的产出占位，属预期）。

**3. 类型一致性**：`global_skills_dir` / `scan_available_skills` / `install_skill` / `uninstall_global_skill` / `install_marketplace_skill` 在各 Task 间签名一致 ✅。前端 `searchMarketplace` 等与后端端点路径一致 ✅。

**4. 已知风险**（spec 已记）：skills.sh CLI（Task 1 解决）、PinnedDNS 合并不覆盖（Task 3 Step 4 已强调保留本仓库内容）。
