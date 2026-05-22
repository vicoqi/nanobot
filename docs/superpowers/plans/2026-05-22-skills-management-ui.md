# Skills Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a skills management view to the agent detail page, allowing users to install/uninstall skills from a centralized manager skills directory via a card-based UI.

**Architecture:** New backend service (`skills.py`) handles filesystem scanning, copying, and deletion. Three new API endpoints on the existing agent router expose this to the frontend. The agent detail page is restructured with a left sidebar menu to switch between settings and skills views.

**Tech Stack:** Python (FastAPI, shutil, PyYAML), TypeScript/React (useState, fetch), TailwindCSS, shadcn/ui

---

## File Structure

| File | Responsibility |
|------|----------------|
| `nanobot/manager/services/skills.py` | **New.** Scan manager skills dir, parse SKILL.md frontmatter, copy/delete skill directories |
| `nanobot/manager/api/agents.py` | **Modify.** Add 3 route handlers for skills available/install/uninstall |
| `webui-manager/src/lib/api.ts` | **Modify.** Add 3 API functions + types |
| `webui-manager/src/pages/AgentDetailPage.tsx` | **Modify.** Restructure to sidebar layout + skills card grid |

---

### Task 1: Backend — Skills Service

**Files:**
- Create: `nanobot/manager/services/skills.py`

- [ ] **Step 1: Create `nanobot/manager/services/skills.py`**

```python
"""Skills filesystem operations for the agent manager."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

_STRIP_FRONTMATTER = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)

MANAGER_SKILLS_DIR = Path.home() / ".nanobot" / "manager" / "skills"


def _parse_frontmatter(content: str) -> dict | None:
    """Parse YAML frontmatter from a SKILL.md file."""
    if not content.startswith("---"):
        return None
    match = _STRIP_FRONTMATTER.match(content)
    if not match:
        return None
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def scan_available_skills() -> list[dict]:
    """Scan the manager skills directory and return skill metadata.

    Returns list of dicts: { "name": str, "description": str }
    """
    skills: list[dict] = []
    if not MANAGER_SKILLS_DIR.is_dir():
        return skills

    for skill_dir in sorted(MANAGER_SKILLS_DIR.iterdir()):
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


def get_installed_skill_names(workspace_path: str) -> set[str]:
    """Return the set of skill names installed in the given workspace."""
    ws_skills = Path(workspace_path) / "skills"
    if not ws_skills.is_dir():
        return set()
    return {
        d.name
        for d in ws_skills.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


def install_skill(skill_name: str, workspace_path: str) -> None:
    """Copy a skill from the manager directory to the agent workspace."""
    src = MANAGER_SKILLS_DIR / skill_name
    if not src.is_dir():
        raise FileNotFoundError(f"Skill not found: {skill_name}")

    dst = Path(workspace_path) / "skills" / skill_name
    if dst.exists():
        raise FileExistsError(f"Skill already installed: {skill_name}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def uninstall_skill(skill_name: str, workspace_path: str) -> None:
    """Remove a skill directory from the agent workspace."""
    dst = Path(workspace_path) / "skills" / skill_name
    if not dst.is_dir():
        raise FileNotFoundError(f"Skill not installed: {skill_name}")
    shutil.rmtree(dst)
```

- [ ] **Step 2: Commit**

```bash
git add nanobot/manager/services/skills.py
git commit -m "feat(manager): add skills service for scanning, installing, uninstalling skills"
```

---

### Task 2: Backend — API Endpoints

**Files:**
- Modify: `nanobot/manager/api/agents.py`

- [ ] **Step 1: Add imports and Pydantic request models**

At the top of `nanobot/manager/api/agents.py`, add to the existing imports (after line 24):

```python
from nanobot.manager.services.skills import (
    get_installed_skill_names,
    install_skill,
    scan_available_skills,
    uninstall_skill,
)
from pydantic import BaseModel
```

Add two request models after the `_check_owner` function (after line 45):

```python
class SkillActionRequest(BaseModel):
    skill_name: str
```

- [ ] **Step 2: Add `GET /api/agents/{id}/skills/available`**

Add after the `get_qrcode_status` endpoint (after line 229):

```python
@router.get("/{agent_id}/skills/available")
async def list_available_skills(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    available = scan_available_skills()
    installed = get_installed_skill_names(agent.workspace_path)
    return {
        "skills": [
            {**s, "installed": s["name"] in installed}
            for s in available
        ],
    }
```

- [ ] **Step 3: Add `POST /api/agents/{id}/skills/install`**

Add after the `list_available_skills` endpoint:

```python
@router.post("/{agent_id}/skills/install")
async def install_skill_endpoint(
    agent_id: int,
    req: SkillActionRequest,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    try:
        install_skill(req.skill_name, agent.workspace_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if agent.status == AgentStatus.RUNNING:
        await pm.restart_agent(agent, db)

    return {"success": True, "message": "Skill installed" + (" and agent restarted" if agent.status == AgentStatus.RUNNING else "")}
```

- [ ] **Step 4: Add `POST /api/agents/{id}/skills/uninstall`**

Add after the `install_skill_endpoint`:

```python
@router.post("/{agent_id}/skills/uninstall")
async def uninstall_skill_endpoint(
    agent_id: int,
    req: SkillActionRequest,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    try:
        uninstall_skill(req.skill_name, agent.workspace_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"success": True, "message": "Skill uninstalled"}
```

- [ ] **Step 5: Commit**

```bash
git add nanobot/manager/api/agents.py
git commit -m "feat(manager): add skills available/install/uninstall API endpoints"
```

---

### Task 3: Frontend — API Client

**Files:**
- Modify: `webui-manager/src/lib/api.ts`

- [ ] **Step 1: Add types and API functions**

Append to the end of `webui-manager/src/lib/api.ts` (after the admin section, before end of file):

```typescript
// -- Skills --

export interface AvailableSkill {
  name: string;
  description: string;
  installed: boolean;
}

export interface SkillsAvailableResponse {
  skills: AvailableSkill[];
}

export async function getAvailableSkills(id: number): Promise<SkillsAvailableResponse> {
  return request(`/api/agents/${id}/skills/available`);
}

export async function installSkill(id: number, skillName: string): Promise<{ success: boolean; message: string }> {
  return request(`/api/agents/${id}/skills/install`, {
    method: "POST",
    body: JSON.stringify({ skillName }),
  });
}

export async function uninstallSkill(id: number, skillName: string): Promise<{ success: boolean; message: string }> {
  return request(`/api/agents/${id}/skills/uninstall`, {
    method: "POST",
    body: JSON.stringify({ skillName }),
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add webui-manager/src/lib/api.ts
git commit -m "feat(webui): add skills API client functions and types"
```

---

### Task 4: Frontend — Restructure Agent Detail Page

**Files:**
- Modify: `webui-manager/src/pages/AgentDetailPage.tsx`

This is the largest change. The existing single-column layout is restructured into a sidebar + content area layout with two tabs.

- [ ] **Step 1: Update imports**

Replace the imports section (lines 1-16) with:

```typescript
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getAgent,
  updateAgent,
  startAgent,
  stopAgent,
  generateQRCode,
  getQRCodeStatus,
  getAvailableSkills,
  installSkill,
  uninstallSkill,
  getAgentStatus,
  type Agent,
  type AvailableSkill,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { QRCodeSVG } from "qrcode.react";
```

- [ ] **Step 2: Replace the entire component**

Replace the entire `AgentDetailPage` function (lines 18-204) with the new implementation below. The key changes:

1. Added `activeTab` state (`"settings"` | `"skills"`)
2. Added `skills` state and `fetchSkills` function
3. Added `handleInstallSkill` and `handleUninstallSkill` functions
4. Restructured layout: left sidebar + right content area
5. Extracted settings content into the sidebar switch

```typescript
type TabKey = "settings" | "skills";

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("settings");
  const [name, setName] = useState("");
  const [soul, setSoul] = useState("");
  const [qrUrl, setQrUrl] = useState("");
  const [language, setLanguage] = useState("zh");
  const [city, setCity] = useState("Shanghai");
  const [gender, setGender] = useState("female");
  const [polling, setPolling] = useState(false);
  const [saving, setSaving] = useState(false);
  const [skills, setSkills] = useState<AvailableSkill[]>([]);
  const [installingSkills, setInstallingSkills] = useState<Set<string>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAgent = useCallback(async () => {
    if (!id) return;
    try {
      const a = await getAgent(Number(id));
      setAgent(a);
      setName(a.name);
      setSoul(a.soul);
      setLanguage(a.language);
      setCity(a.city);
      setGender(a.gender);
    } catch {
      navigate("/dashboard");
    }
  }, [id, navigate]);

  const fetchSkills = useCallback(async () => {
    if (!id) return;
    try {
      const res = await getAvailableSkills(Number(id));
      setSkills(res.skills);
    } catch {
      // ignore — skills list is non-critical
    }
  }, [id]);

  useEffect(() => {
    fetchAgent();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchAgent]);

  useEffect(() => {
    if (activeTab === "skills") {
      fetchSkills();
    }
  }, [activeTab, fetchSkills]);

  async function handleSave() {
    if (!id) return;
    setSaving(true);
    try {
      await updateAgent(Number(id), { name, soul, language, city, gender });
      await fetchAgent();
    } catch (err: any) {
      alert(err.message);
    }
    setSaving(false);
  }

  async function handleToggle() {
    if (!id || !agent) return;
    try {
      if (agent.status === "running") {
        await stopAgent(Number(id));
      } else {
        await startAgent(Number(id));
      }
      await fetchAgent();
    } catch (err: any) {
      alert(err.message);
    }
  }

  function stopPolling() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setPolling(false);
  }

  async function handleQRCode() {
    if (!id) return;
    try {
      const result = await generateQRCode(Number(id));
      setQrUrl(result.qrCodeUrl);
      setPolling(true);

      intervalRef.current = setInterval(async () => {
        try {
          const status = await getQRCodeStatus(Number(id));
          if (status.wechatBound || status.qrCodeStatus === "confirmed") {
            stopPolling();
            await fetchAgent();
          } else if (status.qrCodeStatus === "expired") {
            stopPolling();
            alert("QR code expired. Please generate a new one.");
          }
        } catch {
          stopPolling();
        }
      }, 2000);
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleInstallSkill(skillName: string) {
    if (!id) return;
    setInstallingSkills((prev) => new Set(prev).add(skillName));
    try {
      await installSkill(Number(id), skillName);
      // Poll until agent is running again (max 30s)
      const deadline = Date.now() + 30_000;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const s = await getAgentStatus(Number(id));
          if (s.status === "running") break;
        } catch {
          break;
        }
      }
    } catch (err: any) {
      alert(err.message);
    }
    setInstallingSkills((prev) => {
      const next = new Set(prev);
      next.delete(skillName);
      return next;
    });
    await fetchSkills();
    await fetchAgent();
  }

  async function handleUninstallSkill(skillName: string) {
    if (!id) return;
    try {
      await uninstallSkill(Number(id), skillName);
    } catch (err: any) {
      alert(err.message);
    }
    await fetchSkills();
  }

  if (!agent) return <div className="p-6 text-center text-muted-foreground">Loading...</div>;

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: "settings", label: "设置", icon: "⚙️" },
    { key: "skills", label: "Skills", icon: "📦" },
  ];

  return (
    <div className="flex h-screen">
      {/* Left sidebar */}
      <div className="w-40 border-r bg-muted/30 flex flex-col pt-6">
        <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6 mx-2 justify-start text-sm">
          &larr; Back
        </Button>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-3 text-sm text-left transition-colors ${
              activeTab === tab.key
                ? "bg-primary text-primary-foreground font-medium"
                : "hover:bg-muted text-muted-foreground"
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Right content area */}
      <div className="flex-1 overflow-auto p-6">
        {activeTab === "settings" && (
          <>
            <h1 className="text-2xl font-bold mb-6">Agent Settings</h1>
            <div className="max-w-2xl space-y-4">
              <div>
                <label className="text-sm font-medium">Name</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-sm font-medium">Language</label>
                  <select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                  >
                    <option value="zh">中文</option>
                    <option value="en">English</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">City</label>
                  <Input value={city} onChange={(e) => setCity(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <label className="text-sm font-medium">Gender</label>
                  <select
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                    className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                  >
                    <option value="female">女性</option>
                    <option value="male">男性</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">Personality / SOUL</label>
                <Textarea value={soul} onChange={(e) => setSoul(e.target.value)} rows={5} className="mt-1" />
              </div>
              <div className="flex gap-2">
                <Button onClick={handleSave} disabled={saving}>
                  Save Changes
                </Button>
                <Button variant="outline" onClick={handleToggle}>
                  {agent.status === "running" ? "Stop Agent" : "Start Agent"}
                </Button>
              </div>
            </div>

            <Separator className="my-6 max-w-2xl" />

            <h2 className="text-lg font-semibold mb-4 max-w-2xl">WeChat Binding</h2>
            <div className="max-w-2xl">
              {agent.wechatBound ? (
                <p className="text-green-700">WeChat is bound to this agent.</p>
              ) : (
                <div className="space-y-4">
                  <Button onClick={handleQRCode} disabled={agent.status !== "running" || polling}>
                    {agent.status !== "running" ? "Start agent first to bind WeChat" : polling ? "Waiting for scan..." : "Generate QR Code"}
                  </Button>
                  {qrUrl && (
                    <div className="space-y-2">
                      <div className="inline-block rounded-lg border p-4 bg-white">
                        <QRCodeSVG value={qrUrl} size={200} />
                      </div>
                      {polling && (
                        <p className="text-sm text-muted-foreground animate-pulse">Waiting for scan...</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <Separator className="my-6 max-w-2xl" />

            <div className="max-w-2xl text-sm text-muted-foreground space-y-1">
              <p>Status: {agent.status}</p>
              <p>Port: {agent.gatewayPort}</p>
              <p>PID: {agent.pid || "N/A"}</p>
              <p>Created: {new Date(agent.createdAt).toLocaleString()}</p>
            </div>
          </>
        )}

        {activeTab === "skills" && (
          <>
            <h1 className="text-2xl font-bold mb-6">Skills Management</h1>
            {skills.length === 0 ? (
              <p className="text-muted-foreground">No skills available in manager directory.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {skills.map((skill) => {
                  const isInstalling = installingSkills.has(skill.name);
                  return (
                    <div
                      key={skill.name}
                      className="rounded-lg border bg-card p-4 flex flex-col gap-3"
                    >
                      <div>
                        <h3 className="font-medium text-sm">{skill.name}</h3>
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {skill.description}
                        </p>
                      </div>
                      <div className="mt-auto">
                        {isInstalling ? (
                          <Button disabled className="w-full" size="sm">
                            <span className="animate-pulse">Installing...</span>
                          </Button>
                        ) : skill.installed ? (
                          <Button
                            variant="secondary"
                            className="w-full"
                            size="sm"
                            onClick={() => handleUninstallSkill(skill.name)}
                          >
                            Uninstall
                          </Button>
                        ) : (
                          <Button
                            className="w-full"
                            size="sm"
                            onClick={() => handleInstallSkill(skill.name)}
                          >
                            Install
                          </Button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add webui-manager/src/pages/AgentDetailPage.tsx
git commit -m "feat(webui): add sidebar layout and skills management view to agent detail page"
```

---

### Task 5: Build and Verify

- [ ] **Step 1: Build the frontend**

```bash
cd webui-manager && bun run build
```

Expected: Build succeeds with no errors, output to `nanobot/manager/static/`.

- [ ] **Step 2: Run ruff check on backend changes**

```bash
ruff check nanobot/manager/services/skills.py nanobot/manager/api/agents.py
```

Expected: No errors or warnings.

- [ ] **Step 3: Commit the build output**

```bash
git add nanobot/manager/static/
git commit -m "build(webui-manager): rebuild static assets with skills management UI"
```
