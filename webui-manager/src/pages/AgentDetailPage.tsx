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
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import StatusBadge from "@/components/StatusBadge";
import { QRCodeSVG } from "qrcode.react";

type TabKey = "settings" | "skills";

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useI18n();
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
      // non-critical
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
    if (!id || intervalRef.current) return;
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
            alert(t("agent.qrExpired"));
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
    await Promise.all([fetchSkills(), fetchAgent()]);
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

  if (!agent) return <div className="p-6 text-center text-muted-foreground">{t("common.loading")}</div>;

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: "settings", label: t("agent.settings"), icon: "⚙️" },
    { key: "skills", label: t("agent.skills"), icon: "📦" },
  ];

  return (
    <div className="flex h-screen">
      {/* Left sidebar */}
      <div className="w-40 border-r bg-muted/30 flex flex-col pt-6">
        <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-6 mx-2 justify-start text-sm">
          {t("common.back")}
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
      <div className="flex-1 overflow-auto">
        <div className="mx-auto max-w-4xl p-6">
        {activeTab === "settings" && (
          <>
            <h1 className="text-2xl font-bold mb-6">{t("agent.settingsTitle")}</h1>
            <div className="max-w-2xl space-y-4">
              <div>
                <label className="text-sm font-medium">{t("agent.name")}</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-sm font-medium">{t("agent.language")}</label>
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
                  <label className="text-sm font-medium">{t("agent.city")}</label>
                  <Input value={city} onChange={(e) => setCity(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <label className="text-sm font-medium">{t("agent.gender")}</label>
                  <select
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                    className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                  >
                    <option value="female">{t("agent.genderFemale")}</option>
                    <option value="male">{t("agent.genderMale")}</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">{t("agent.personality")}</label>
                <Textarea value={soul} onChange={(e) => setSoul(e.target.value)} rows={5} className="mt-1" />
              </div>
              <div className="flex gap-2">
                <Button onClick={handleSave} disabled={saving}>
                  {t("agent.saveChanges")}
                </Button>
                <Button variant="outline" onClick={handleToggle}>
                  {agent.status === "running" ? t("agent.stopAgent") : t("agent.startAgent")}
                </Button>
              </div>
            </div>

            <Separator className="my-6 max-w-2xl" />

            <h2 className="text-lg font-semibold mb-4 max-w-2xl">{t("agent.wechatBinding")}</h2>
            <div className="max-w-2xl">
              {agent.wechatBound ? (
                <p className="text-green-700">{t("agent.wechatBound")}</p>
              ) : (
                <div className="space-y-4">
                  <Button onClick={handleQRCode} disabled={agent.status !== "running" || polling}>
                    {agent.status !== "running" ? t("agent.startFirst") : polling ? t("agent.waitingScan") : t("agent.generateQR")}
                  </Button>
                  {qrUrl && (
                    <div className="space-y-2">
                      <div className="inline-block rounded-lg border p-4 bg-white">
                        <QRCodeSVG value={qrUrl} size={200} />
                      </div>
                      {polling && (
                        <p className="text-sm text-muted-foreground animate-pulse">{t("agent.waitingScan")}</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <Separator className="my-6 max-w-2xl" />

            <div className="max-w-2xl text-sm text-muted-foreground space-y-1">
              <p>{t("agent.status")} <StatusBadge status={agent.status} /></p>
              <p>{t("agent.port")} {agent.gatewayPort}</p>
              <p>{t("agent.pid")} {agent.pid || t("common.na")}</p>
              <p>{t("agent.created")} {new Date(agent.createdAt).toLocaleString()}</p>
            </div>
          </>
        )}

        {activeTab === "skills" && (
          <>
            <h1 className="text-2xl font-bold mb-6">{t("agent.skillsTitle")}</h1>
            {skills.length === 0 ? (
              <p className="text-muted-foreground">{t("agent.noSkills")}</p>
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
                            <span className="animate-pulse">{t("common.installing")}</span>
                          </Button>
                        ) : skill.installed ? (
                          <Button
                            variant="secondary"
                            className="w-full"
                            size="sm"
                            onClick={() => handleUninstallSkill(skill.name)}
                          >
                            {t("common.uninstall")}
                          </Button>
                        ) : (
                          <Button
                            className="w-full"
                            size="sm"
                            onClick={() => handleInstallSkill(skill.name)}
                          >
                            {t("common.install")}
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
    </div>
  );
}
