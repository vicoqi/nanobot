import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { listAgents, createAgent, deleteAgent, startAgent, stopAgent, type Agent } from "@/lib/api";
import { clearToken } from "@/lib/auth";
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import StatusBadge from "@/components/StatusBadge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";

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

export default function DashboardPage() {
  const navigate = useNavigate();
  const { t, locale, setLocale } = useI18n();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [soul, setSoul] = useState("");
  const [language, setLanguage] = useState("zh");
  const [city, setCity] = useState("Shanghai");
  const [gender, setGender] = useState("female");
  const [loading, setLoading] = useState(false);

  const fetchAgents = useCallback(async () => {
    try {
      setAgents(await listAgents());
    } catch {
      // auth lib redirects on 401
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  async function handleCreate() {
    setLoading(true);
    try {
      await createAgent(name, soul, language, city, gender);
      setShowCreate(false);
      setName("");
      setSoul("");
      setLanguage("zh");
      setCity("Shanghai");
      setGender("female");
      await fetchAgents();
    } catch (err: any) {
      alert(err.message);
    }
    setLoading(false);
  }

  async function handleToggle(agent: Agent) {
    try {
      if (agent.status === "running") {
        await stopAgent(agent.id);
      } else {
        await startAgent(agent.id);
      }
      await fetchAgents();
    } catch (err: any) {
      alert(err.message);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm(t("dashboard.confirmDelete"))) return;
    try {
      await deleteAgent(id);
      await fetchAgents();
    } catch (err: any) {
      alert(err.message);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger asChild>
              <Button className="col-span-2 sm:col-span-1">{t("dashboard.create")}</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t("dashboard.create")}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <Input placeholder={t("dashboard.agentName")} value={name} onChange={(e) => setName(e.target.value)} />
                <div className="grid gap-3 sm:grid-cols-3">
                  <select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    className="rounded-md border px-3 py-2 text-sm"
                  >
                    <option value="zh">中文</option>
                    <option value="en">English</option>
                  </select>
                  <Input placeholder={t("dashboard.city")} value={city} onChange={(e) => setCity(e.target.value)} />
                  <select
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                    className="rounded-md border px-3 py-2 text-sm"
                  >
                    <option value="female">{t("agent.genderFemale")}</option>
                    <option value="male">{t("agent.genderMale")}</option>
                  </select>
                </div>
                <Textarea
                  placeholder={t("dashboard.personality")}
                  value={soul}
                  onChange={(e) => setSoul(e.target.value)}
                  rows={4}
                />
                <Button onClick={handleCreate} disabled={loading || !name} className="w-full">
                  {t("dashboard.createBtn")}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
            className="w-full sm:w-auto"
          >
            {locale === "zh" ? "中 / EN" : "EN / 中"}
          </Button>
          <Button
            variant="outline"
            className="w-full sm:w-auto"
            onClick={() => {
              clearToken();
              navigate("/login");
            }}
          >
            {t("common.logout")}
          </Button>
        </div>
      </div>

      <Separator className="mb-6" />

      {agents.length === 0 ? (
        <p className="text-center text-muted-foreground py-12">{t("dashboard.empty")}</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="rounded-lg border bg-card p-4 space-y-3 cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => navigate(`/agent/${agent.id}`)}
            >
              <div className="flex items-start justify-between gap-3">
                <h3 className="min-w-0 break-words font-semibold">{agent.name}</h3>
                <StatusBadge status={agent.status} />
              </div>
              {agent.soul && <p className="text-sm text-muted-foreground line-clamp-2">{agent.soul}</p>}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>{agent.lastActiveAt ? formatRelativeTime(agent.lastActiveAt, t) : t("dashboard.neverActive")}</span>
                  <span>{agent.wechatBound ? t("dashboard.wechatBound") : t("dashboard.notBound")}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:flex sm:gap-1" onClick={(e) => e.stopPropagation()}>
                  <Button size="sm" variant="outline" className="w-full sm:w-auto" onClick={() => handleToggle(agent)}>
                    {agent.status === "running" ? t("common.stop") : t("common.start")}
                  </Button>
                  <Button size="sm" variant="destructive" className="w-full sm:w-auto" onClick={() => handleDelete(agent.id)}>
                    {t("common.delete")}
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
