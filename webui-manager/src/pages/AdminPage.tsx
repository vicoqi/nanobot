import { useState, useEffect } from "react";
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
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import StatusBadge from "@/components/StatusBadge";

function formatRelativeTime(iso: string, t: (key: string, params?: Record<string, string | number>) => string): string {
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return t("time.justNow");
  if (mins < 60) return t("time.minutesAgo", { n: mins });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t("time.hoursAgo", { n: hours });
  const days = Math.floor(hours / 24);
  if (days < 30) return t("time.daysAgo", { n: days });
  return new Date(iso).toLocaleDateString();
}

export default function AdminPage() {
  const { t, locale, setLocale } = useI18n();
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
          <h1 className="text-2xl font-bold text-center">{t("admin.login")}</h1>
          <Input
            type="password"
            placeholder={t("admin.password")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" className="w-full">
            {t("auth.login")}
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{t("admin.title")}</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
          >
            {locale === "zh" ? "中 / EN" : "EN / 中"}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              clearAdminToken();
              setLoggedIn(false);
            }}
          >
            {t("common.logout")}
          </Button>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-5 gap-4 mb-6">
          {[
            { label: t("admin.statsUsers"), value: stats.totalUsers },
            { label: t("admin.statsAgents"), value: stats.totalAgents },
            { label: t("admin.statsRunning"), value: stats.runningAgents },
            { label: t("admin.statsStopped"), value: stats.stoppedAgents },
            { label: t("admin.statsErrors"), value: stats.errorAgents },
          ].map((s) => (
            <div key={s.label} className="rounded-lg border bg-card p-4 text-center">
              <div className="text-2xl font-bold">{s.value}</div>
              <div className="text-sm text-muted-foreground">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-4">
        <Button variant={tab === "agents" ? "default" : "outline"} size="sm" onClick={() => setTab("agents")}>
          {t("admin.tabAgents")}
        </Button>
        <Button variant={tab === "users" ? "default" : "outline"} size="sm" onClick={() => setTab("users")}>
          {t("admin.tabUsers")}
        </Button>
      </div>

      <Separator className="mb-4" />

      {tab === "agents" && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-4">{t("admin.colId")}</th>
              <th className="py-2 pr-4">{t("admin.colName")}</th>
              <th className="py-2 pr-4">{t("admin.colUserId")}</th>
              <th className="py-2 pr-4">{t("admin.colStatus")}</th>
              <th className="py-2 pr-4">{t("admin.colPort")}</th>
              <th className="py-2 pr-4">{t("admin.colWechat")}</th>
              <th className="py-2 pr-4">{t("admin.colLastActive")}</th>
              <th className="py-2 pr-4">{t("admin.colActions")}</th>
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
                <td className="py-2 pr-4">{a.wechatBound ? t("common.yes") : t("common.no")}</td>
                <td className="py-2 pr-4">{a.lastActiveAt ? formatRelativeTime(a.lastActiveAt, t) : "-"}</td>
                <td className="py-2 pr-4">
                  {a.status === "running" ? (
                    <Button variant="outline" size="sm" disabled={togglingId === a.id} onClick={() => handleToggle(a.id, "stop")}>
                      {togglingId === a.id ? t("admin.stopping") : t("common.stop")}
                    </Button>
                  ) : a.status === "stopped" || a.status === "error" ? (
                    <Button size="sm" disabled={togglingId === a.id} onClick={() => handleToggle(a.id, "start")}>
                      {togglingId === a.id ? t("admin.starting") : t("common.start")}
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">{t("admin.creating")}</span>
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
              <th className="py-2 pr-4">{t("admin.colId")}</th>
              <th className="py-2 pr-4">{t("admin.colUsername")}</th>
              <th className="py-2 pr-4">{t("admin.colAgents")}</th>
              <th className="py-2 pr-4">{t("admin.colCreated")}</th>
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
