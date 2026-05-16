import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getAgent,
  updateAgent,
  startAgent,
  stopAgent,
  generateQRCode,
  getQRCodeStatus,
  type Agent,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { QRCodeSVG } from "qrcode.react";

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [name, setName] = useState("");
  const [soul, setSoul] = useState("");
  const [qrUrl, setQrUrl] = useState("");
  const [polling, setPolling] = useState(false);
  const [saving, setSaving] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAgent = useCallback(async () => {
    if (!id) return;
    try {
      const a = await getAgent(Number(id));
      setAgent(a);
      setName(a.name);
      setSoul(a.soul);
    } catch {
      navigate("/dashboard");
    }
  }, [id, navigate]);

  useEffect(() => {
    fetchAgent();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchAgent]);

  async function handleSave() {
    if (!id) return;
    setSaving(true);
    try {
      await updateAgent(Number(id), { name, soul });
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

  if (!agent) return <div className="p-6 text-center text-muted-foreground">Loading...</div>;

  return (
    <div className="mx-auto max-w-2xl p-6">
      <Button variant="ghost" onClick={() => navigate("/dashboard")} className="mb-4">
        &larr; Back
      </Button>

      <h1 className="text-2xl font-bold mb-6">Agent Settings</h1>

      <div className="space-y-4">
        <div>
          <label className="text-sm font-medium">Name</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" />
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

      <Separator className="my-6" />

      <h2 className="text-lg font-semibold mb-4">WeChat Binding</h2>
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

      <Separator className="my-6" />

      <div className="text-sm text-muted-foreground space-y-1">
        <p>Status: {agent.status}</p>
        <p>Port: {agent.gatewayPort}</p>
        <p>PID: {agent.pid || "N/A"}</p>
        <p>Created: {new Date(agent.createdAt).toLocaleString()}</p>
      </div>
    </div>
  );
}
