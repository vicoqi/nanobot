import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { listAgents, createAgent, deleteAgent, startAgent, stopAgent, type Agent } from "@/lib/api";
import { clearToken } from "@/lib/auth";
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

export default function DashboardPage() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [soul, setSoul] = useState("");
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
      await createAgent(name, soul);
      setShowCreate(false);
      setName("");
      setSoul("");
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
    if (!confirm("Delete this agent?")) return;
    try {
      await deleteAgent(id);
      await fetchAgents();
    } catch (err: any) {
      alert(err.message);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">My Agents</h1>
        <div className="flex gap-2">
          <Dialog open={showCreate} onOpenChange={setShowCreate}>
            <DialogTrigger asChild>
              <Button>Create Agent</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Agent</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <Input placeholder="Agent name" value={name} onChange={(e) => setName(e.target.value)} />
                <Textarea
                  placeholder="Agent personality / SOUL (optional)"
                  value={soul}
                  onChange={(e) => setSoul(e.target.value)}
                  rows={4}
                />
                <Button onClick={handleCreate} disabled={loading || !name} className="w-full">
                  Create
                </Button>
              </div>
            </DialogContent>
          </Dialog>
          <Button
            variant="outline"
            onClick={() => {
              clearToken();
              navigate("/login");
            }}
          >
            Logout
          </Button>
        </div>
      </div>

      <Separator className="mb-6" />

      {agents.length === 0 ? (
        <p className="text-center text-muted-foreground py-12">No agents yet. Create your first one!</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {agents.map((agent) => (
            <div
              key={agent.id}
              className="rounded-lg border bg-card p-4 space-y-3 cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => navigate(`/agent/${agent.id}`)}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">{agent.name}</h3>
                <StatusBadge status={agent.status} />
              </div>
              {agent.soul && <p className="text-sm text-muted-foreground line-clamp-2">{agent.soul}</p>}
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {agent.wechatBound ? "WeChat bound" : "Not bound"}
                </span>
                <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                  <Button size="sm" variant="outline" onClick={() => handleToggle(agent)}>
                    {agent.status === "running" ? "Stop" : "Start"}
                  </Button>
                  <Button size="sm" variant="destructive" onClick={() => handleDelete(agent.id)}>
                    Delete
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
