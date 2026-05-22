# Skills Management UI for Agent Detail Page

## Summary

Add a skills management section to the agent detail page in the WebUI manager. The page gains a left sidebar menu with two views: Agent Settings (existing form) and Skills Management (new). Skills are installed by copying from a centralized manager skills directory to individual agent workspace directories.

## Page Layout

The current single-page agent detail form is restructured into a sidebar + content area layout:

```
┌──────────┬─────────────────────────────────┐
│          │                                 │
│  ⚙️ 设置  │   Content area switches based   │
│          │   on selected menu item          │
│  📦 Skills│                                 │
│          │                                 │
└──────────┴─────────────────────────────────┘
```

- Left sidebar: ~160px fixed width, two menu items (Settings, Skills)
- Right content area: switches based on selected menu item
- URL does not change; pure frontend state toggle (`useState`)
- Selecting "Settings" shows the existing agent form (name, soul, language, city, gender)
- Selecting "Skills" shows the skills card grid

## Skills Management View

### Data

Two sources merged into one list:

- **Available skills**: scanned from `~/.nanobot/manager/skills/*/SKILL.md` (parse YAML frontmatter for `name` + `description`)
- **Installed status**: determined by checking if the directory exists under `~/.nanobot/workspaces/agent-{port}/skills/{name}/`

### Card Grid

Each available skill is rendered as a card in a responsive grid (2-3 columns).

Card content:
- Skill name (from frontmatter `name`)
- Description (from frontmatter `description`, truncated if long)

Three button states:

| State | Button | Behavior |
|-------|--------|----------|
| Not installed | `[安装]` (primary) | Click triggers install |
| Installing | `[⏳ 安装中...]` (disabled, loading) | Shown for ~30s during install |
| Installed | `[卸载]` (secondary) | Click triggers uninstall |

### Install Flow

1. User clicks `[安装]`
2. Frontend calls `POST /api/agents/{id}/skills/install { skillName }`
3. Backend copies the skill directory and restarts the agent if running
4. Frontend polls `GET /api/agents/{id}/status` until `status === "running"` (max 30s timeout)
5. Card refreshes to show `[卸载]` state

### Uninstall Flow

1. User clicks `[卸载]`
2. Frontend calls `POST /api/agents/{id}/skills/uninstall { skillName }`
3. Backend deletes the skill directory from workspace
4. No agent restart needed (skill won't load on next session anyway)
5. Card immediately updates to show `[安装]` state

## Manager API

Three new endpoints on the existing agent router (`/api/agents/{id}/`):

### GET /api/agents/{id}/skills/available

Returns all installable skills with their installed status.

Response:
```json
{
  "skills": [
    {
      "name": "alphaear-news",
      "description": "Fetch hot finance news, unified trends...",
      "installed": true
    }
  ]
}
```

Implementation:
- Scan `~/.nanobot/manager/skills/*/SKILL.md`
- Parse YAML frontmatter for `name` and `description`
- Check existence of `~/.nanobot/workspaces/agent-{port}/skills/{name}/` to set `installed`

### POST /api/agents/{id}/skills/install

Installs a skill by copying from the manager skills directory to the agent workspace.

Request:
```json
{ "skillName": "alphaear-news" }
```

Response:
```json
{ "success": true, "message": "Skill installed and agent restarted" }
```

Implementation:
- Validate `skillName` exists in `~/.nanobot/manager/skills/`
- `shutil.copytree` from manager skills to `workspace/skills/{skillName}/`
- If agent is running, call stop then start (reuse existing logic)
- If agent is stopped, only copy files (no restart)

### POST /api/agents/{id}/skills/uninstall

Removes a skill from the agent workspace.

Request:
```json
{ "skillName": "alphaear-news" }
```

Response:
```json
{ "success": true, "message": "Skill uninstalled" }
```

Implementation:
- Validate `skillName` exists in `workspace/skills/`
- `shutil.rmtree` on `workspace/skills/{skillName}/`
- Do not restart agent

## Files Changed

### Frontend

| File | Change |
|------|--------|
| `webui-manager/src/lib/api.ts` | Add 3 API functions + request/response types |
| `webui-manager/src/pages/AgentDetailPage.tsx` | Restructure to sidebar layout + add skills management view |

### Backend

| File | Change |
|------|--------|
| `nanobot/manager/api/agents.py` | Add 3 route handlers |
| `nanobot/manager/services/skills.py` | New file: skill scanning, install (copy), uninstall (delete) logic |

### Not Changed

- Database schema (no new columns needed; install state is filesystem-derived)
- `config_builder.py` (no changes)
- Agent-side code (skills loader works as-is)
