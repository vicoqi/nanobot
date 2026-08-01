import { getToken, clearToken, getAdminToken, clearAdminToken } from "./auth";

const BASE = "";

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  // Match both the legacy admin routes ("/admin/...") and the newer
  // marketplace routes mounted under "/api/admin/...". Without the second
  // branch, admin JWT would never be attached to the skills-marketplace
  // calls and every request would 401.
  const isAdmin = path.startsWith("/admin") || path.startsWith("/api/admin");
  const token = isAdmin ? getAdminToken() : getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (res.status === 401) {
    if (isAdmin) {
      clearAdminToken();
    } else {
      clearToken();
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

// -- Auth --

export interface TokenResponse {
  token: string;
}

export async function register(username: string, password: string): Promise<TokenResponse> {
  return request("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function adminLogin(password: string): Promise<TokenResponse> {
  return request("/admin/auth/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

// -- Agents --

export interface Agent {
  id: number;
  userId: number;
  name: string;
  soul: string;
  status: "creating" | "running" | "stopped" | "error";
  configPath: string;
  workspacePath: string;
  gatewayPort: number;
  pid: number | null;
  wechatBound: boolean;
  qrCodeId: string;
  qrCodeUrl: string;
  qrCodeStatus: string;
  wechatBotId: string;
  wechatBotToken: string;
  language: string;
  city: string;
  gender: string;
  dailyDeliveryEnabled: boolean;
  createdAt: string;
  updatedAt: string;
  lastActiveAt: string | null;
}

export interface AgentStatusResponse {
  status: string;
  pid: number | null;
  alive: boolean;
  gatewayPort: number;
  wechatBound: boolean;
  qrCodeStatus: string;
}

export async function listAgents(): Promise<Agent[]> {
  return request("/api/agents");
}

export async function createAgent(
  name: string,
  soul: string,
  language = "zh",
  city = "Shanghai",
  gender = "female"
): Promise<Agent> {
  return request("/api/agents", {
    method: "POST",
    body: JSON.stringify({ name, soul, language, city, gender }),
  });
}

export async function getAgent(id: number): Promise<Agent> {
  return request(`/api/agents/${id}`);
}

export async function updateAgent(
  id: number,
  data: {
    name?: string;
    soul?: string;
    language?: string;
    city?: string;
    gender?: string;
    dailyDeliveryEnabled?: boolean;
  }
): Promise<Agent> {
  return request(`/api/agents/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteAgent(id: number): Promise<void> {
  await request(`/api/agents/${id}`, { method: "DELETE" });
}

export async function startAgent(id: number): Promise<Agent> {
  return request(`/api/agents/${id}/start`, { method: "POST" });
}

export async function stopAgent(id: number): Promise<Agent> {
  return request(`/api/agents/${id}/stop`, { method: "POST" });
}

export async function getAgentStatus(id: number): Promise<AgentStatusResponse> {
  return request(`/api/agents/${id}/status`);
}

export async function generateQRCode(id: number): Promise<{ qrCodeUrl: string; qrCodeId: string }> {
  return request(`/api/agents/${id}/qrcode`, { method: "POST" });
}

export async function getQRCodeStatus(id: number): Promise<{ qrCodeStatus: string; wechatBound: boolean }> {
  return request(`/api/agents/${id}/qrcode/status`);
}

// -- Admin --

export interface AdminStats {
  totalUsers: number;
  totalAgents: number;
  runningAgents: number;
  stoppedAgents: number;
  errorAgents: number;
}

export interface AdminUser {
  id: number;
  username: string;
  agentCount: number;
  createdAt: string;
}

export async function getAdminStats(): Promise<AdminStats> {
  return request("/admin/stats");
}

export async function getAdminAgents(): Promise<Agent[]> {
  return request("/admin/agents");
}

export async function getAdminUsers(): Promise<AdminUser[]> {
  return request("/admin/users");
}

export async function adminStartAgent(id: number): Promise<Agent> {
  return request(`/admin/agents/${id}/start`, { method: "POST" });
}

export async function adminStopAgent(id: number): Promise<Agent> {
  return request(`/admin/agents/${id}/stop`, { method: "POST" });
}

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

// -- Admin: Skills Marketplace --
//
// Types mirror the live backend contract in
// ``nanobot/manager/api/marketplace.py`` + ``services/skills_marketplace.py``.
// Note the marketplace list endpoints wrap results under ``skills`` (not
// ``results``) and ``install`` returns ``{installed, already_installed, name}``
// rather than ``{success}`` — the UI (Discover/Installed views) reads these
// exact shapes.

export interface MarketplaceSkill {
  id: string;
  /** Raw skill name as used on the upstream provider (skills.sh / SkillHub). */
  skill_id?: string;
  name: string;
  /** Not emitted by every provider; UI falls back to ``name``. */
  description?: string;
  source: string;
  provider?: string;
  installs?: number;
  url?: string;
  installed: boolean;
  install_supported?: boolean;
  /** Ranking metric, e.g. ``installs_24h`` for trending rows. */
  metric?: string;
  rank?: number;
}

export interface InstalledSkill {
  name: string;
  description: string;
}

export interface MarketplaceSearchResponse {
  query: string;
  skills: MarketplaceSkill[];
  provider: string;
  install_supported: boolean;
}

export interface MarketplaceTrendingResponse {
  skills: MarketplaceSkill[];
  period: string;
  provider: string;
  install_supported: boolean;
}

export interface MarketplaceInstallResponse {
  installed: boolean;
  already_installed: boolean;
  name: string;
  provider?: string;
}

export interface UninstallSkillResponse {
  success: boolean;
  cleanedWorkspaces: number;
}

/** Search the public skills marketplace (skills.sh + SkillHub). */
export async function searchMarketplace(
  q: string,
  source = "all"
): Promise<MarketplaceSearchResponse> {
  const params = new URLSearchParams({ q, source });
  return request(`/api/admin/skills/marketplace/search?${params.toString()}`);
}

/** Fetch the provider-aware marketplace trending leaderboard. */
export async function trendingMarketplace(
  source = "all"
): Promise<MarketplaceTrendingResponse> {
  const params = new URLSearchParams({ source });
  return request(`/api/admin/skills/marketplace/trending?${params.toString()}`);
}

/**
 * Install a marketplace skill into the global manager-skills repo.
 * Body keys are camelCase to match the backend's pydantic ``to_camel`` alias
 * (``skillId`` on the wire, ``skill_id`` in Python).
 */
export async function installMarketplaceSkill(
  skillId: string,
  source: string,
  provider = "skills_sh",
  version = ""
): Promise<MarketplaceInstallResponse> {
  return request("/api/admin/skills/marketplace/install", {
    method: "POST",
    body: JSON.stringify({ skillId, source, provider, version }),
  });
}

/** List skills installed in the global repo. */
export async function listInstalledSkills(): Promise<{ skills: InstalledSkill[] }> {
  return request("/api/admin/skills");
}

/**
 * Remove a skill from the global repo and cascade-clean agent workspaces.
 * ``name`` is a path segment, so it is encoded with ``encodeURIComponent``
 * (not folded into URLSearchParams).
 */
export async function uninstallGlobalSkill(name: string): Promise<UninstallSkillResponse> {
  return request(`/api/admin/skills/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}
