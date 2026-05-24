import { useState, useEffect } from "react";

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
import {
  adminLogin,
  getAdminStats,
  getAdminAgents,
  getAdminUsers,
  adminStartAgent,
  adminStopAgent,
  type AdminStats,
  type Agent,
  type AdminUser,
} from "@/lib/api";
import { setAdminToken, clearAdminToken, isAdminLoggedIn } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import StatusBadge from "@/components/StatusBadge";

export default function AdminPage() {
  const [loggedIn, setLoggedIn] = useState(isAdminLoggedIn());
  const [password, setPassword] = useState("");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [tab, setTab] = useState<"agents" | "users">("agents");
  const [togglingId, setTogglingId] = useState<number | null>(null);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    try {
      const { token } = await adminLogin(password);
      setAdminToken(token);
      setLoggedIn(true);
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function loadData() {
    try {
      const [s, a, u] = await Promise.all([getAdminStats(), getAdminAgents(), getAdminUsers()]);
      setStats(s);
      setAgents(a);
      setUsers(u);
    } catch {
      // auth lib handles 401
    }
  }

  useEffect(() => {
    if (loggedIn) loadData();
  }, [loggedIn]);

  async function handleToggle(id: number, action: "start" | "stop") {
    setTogglingId(id);
    try {
      await (action === "start" ? adminStartAgent(id) : adminStopAgent(id));
      await loadData();
    } catch (err: any) {
      alert(err.message);
    }
    setTogglingId(null);
  }

  if (!loggedIn) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <form onSubmit={handleLogin} className="w-full max-w-sm space-y-4 p-6">
          <h1 className="text-2xl font-bold text-center">Admin Login</h1>
          <Input
            type="password"
            placeholder="Admin password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" className="w-full">
            Login
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Admin Dashboard</h1>
        <Button
          variant="outline"
          onClick={() => {
            clearAdminToken();
            setLoggedIn(false);
          }}
        >
          Logout
        </Button>
      </div>

      {stats && (
        <div className="grid grid-cols-5 gap-4 mb-6">
          {[
            { label: "Users", value: stats.totalUsers },
            { label: "Agents", value: stats.totalAgents },
            { label: "Running", value: stats.runningAgents },
            { label: "Stopped", value: stats.stoppedAgents },
            { label: "Errors", value: stats.errorAgents },
          ].map((s) => (
            <div key={s.label} className="rounded-lg border bg-card p-4 text-center">
              <div className="text-2xl font-bold">{s.value}</div>
              <div className="text-sm text-muted-foreground">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {(["agents", "users"] as const).map((t) => (
          <Button key={t} variant={tab === t ? "default" : "outline"} size="sm" onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </Button>
        ))}
      </div>

      <Separator className="mb-4" />

      {tab === "agents" && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-4">ID</th>
              <th className="py-2 pr-4">Name</th>
              <th className="py-2 pr-4">User ID</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Port</th>
              <th className="py-2 pr-4">WeChat</th>
              <th className="py-2 pr-4">Last Active</th>
              <th className="py-2 pr-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.id} className="border-b">
                <td className="py-2 pr-4">{a.id}</td>
                <td className="py-2 pr-4">{a.name}</td>
                <td className="py-2 pr-4">{a.userId}</td>
                <td className="py-2 pr-4"><StatusBadge status={a.status} /></td>
                <td className="py-2 pr-4">{a.gatewayPort}</td>
                <td className="py-2 pr-4">{a.wechatBound ? "Yes" : "No"}</td>
                <td className="py-2 pr-4">{a.lastActiveAt ? formatRelativeTime(a.lastActiveAt) : "-"}</td>
                <td className="py-2 pr-4">
                  {a.status === "running" ? (
                    <Button variant="outline" size="sm" disabled={togglingId === a.id} onClick={() => handleToggle(a.id, "stop")}>
                      {togglingId === a.id ? "Stopping..." : "Stop"}
                    </Button>
                  ) : a.status === "stopped" || a.status === "error" ? (
                    <Button size="sm" disabled={togglingId === a.id} onClick={() => handleToggle(a.id, "start")}>
                      {togglingId === a.id ? "Starting..." : "Start"}
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">Creating...</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === "users" && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-4">ID</th>
              <th className="py-2 pr-4">Username</th>
              <th className="py-2 pr-4">Agents</th>
              <th className="py-2 pr-4">Created</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b">
                <td className="py-2 pr-4">{u.id}</td>
                <td className="py-2 pr-4">{u.username}</td>
                <td className="py-2 pr-4">{u.agentCount}</td>
                <td className="py-2 pr-4">{new Date(u.createdAt).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
