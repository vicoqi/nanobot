import { useState, useEffect, useCallback } from "react";
import {
  listInstalledSkills,
  uninstallGlobalSkill,
  type InstalledSkill,
} from "@/lib/api";
import {
  skillInstalledDescription,
  classifyUninstall,
} from "@/lib/skillsInstalled";
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";

/**
 * Installed-skills management view for the admin skills tab.
 *
 * Renders the contents of the global manager-skills repo (shared by every
 * agent) as a card grid with per-row uninstall. Uninstalling cascades: the
 * backend removes the skill globally AND scrubs references from each agent
 * workspace, so the uninstall button is gated behind a ``window.confirm``
 * that warns about the cascade, and the post-uninstall toast reports the
 * concrete ``cleanedWorkspaces`` count returned by the API so the admin
 * knows how many agents were touched.
 *
 * Layout mirrors ``SkillsDiscover`` for visual consistency:
 *   ┌ title + subtitle ┐
 *   ├ post-uninstall notice (success / info / error) ┤
 *   ├ error banner ┤
 *   ├ loading / empty state ┤
 *   └ card grid: name + description + uninstall button ┘
 *
 * Wire contract (see Task 8 in ``src/lib/api.ts``):
 *   - ``listInstalledSkills`` → ``{ skills: InstalledSkill[] }`` (NOT
 *     ``results`` — the marketplace list endpoints wrap under ``skills``).
 *   - ``uninstallGlobalSkill`` → ``{ success, cleanedWorkspaces }``.
 */
export default function SkillsInstalled() {
  const { t } = useI18n();

  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  // Start in loading state so the first paint does not flash "empty" before
  // the initial list resolves.
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Per-skill uninstall in-flight marker so we can disable just the clicked
  // row's button (and label it "Uninstalling...") rather than locking the
  // whole list.
  const [uninstallingName, setUninstallingName] = useState<string | null>(
    null,
  );
  // Post-uninstall toast. ``kind`` drives styling; ``message`` is the
  // localized string already interpolated with the cleaned-workspaces count.
  const [notice, setNotice] = useState<{ kind: "success" | "info"; message: string } | null>(
    null,
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listInstalledSkills();
      // Defensive ``?? []`` so a malformed empty-body response renders the
      // empty state instead of crashing on ``.map``.
      setSkills(res.skills ?? []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial mount load. ``reload`` is stable (no deps), so this fires once.
  useEffect(() => {
    void reload();
  }, [reload]);

  const handleUninstall = useCallback(
    async (skill: InstalledSkill) => {
      // Cascade warning BEFORE the network call — the admin gets one chance
      // to back out before agent workspaces are scrubbed. The list endpoint
      // gives us no per-skill agent count, so the prompt is generic rather
      // than quoting a specific N; the concrete count surfaces in the
      // post-uninstall notice below.
      const ok = window.confirm(t("admin.skillsInstalled.confirm"));
      if (!ok) return;

      setUninstallingName(skill.name);
      // Clear any stale notice from a previous uninstall so the toast area
      // doesn't show a misleading old message next to a fresh error.
      setNotice(null);
      try {
        const res = await uninstallGlobalSkill(skill.name);
        const outcome = classifyUninstall(res);
        if (outcome.kind === "cleaned") {
          setNotice({
            kind: "success",
            message: t("admin.skillsInstalled.cleaned", { n: outcome.count }),
          });
        } else if (outcome.kind === "noAgents") {
          setNotice({
            kind: "info",
            message: t("admin.skillsInstalled.noAgents"),
          });
        } else {
          // ``success: false`` from the backend. Surface as a soft notice
          // rather than the hard error banner (which is reserved for thrown
          // network/parse failures).
          setNotice({
            kind: "info",
            message: t("admin.skillsInstalled.failed"),
          });
        }
        // Refresh the list so the uninstalled skill disappears. ``reload``
        // also clears loading correctly; we don't set a separate
        // "post-uninstall loading" state because the toast already signals
        // completion.
        await reload();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setUninstallingName(null);
      }
    },
    [reload, t],
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold leading-tight">
          {t("admin.skillsInstalled.title")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("admin.skillsInstalled.subtitle")}
        </p>
      </div>

      {/* Post-uninstall notice (success / info) */}
      {notice && (
        <div
          role="status"
          className={
            notice.kind === "success"
              ? "rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-400"
              : "rounded-md border border-muted bg-muted/40 p-3 text-sm text-muted-foreground"
          }
        >
          {notice.message}
        </div>
      )}

      {/* Error banner (thrown network/parse failures) */}
      {error && (
        <div
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      )}

      {/* Loading / empty state */}
      {loading && (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("common.loading")}
        </div>
      )}
      {!loading && skills.length === 0 && !error && (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("admin.skillsInstalled.empty")}
        </div>
      )}

      {/* Installed-skills grid */}
      {!loading && skills.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill) => {
            const uninstalling = uninstallingName === skill.name;
            return (
              <div
                key={skill.name}
                className="flex flex-col gap-2 rounded-lg border bg-card p-4"
              >
                <h3 className="font-medium leading-tight">{skill.name}</h3>
                <p className="line-clamp-3 text-sm text-muted-foreground">
                  {skillInstalledDescription(skill)}
                </p>
                <div className="mt-auto pt-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    className="w-full"
                    disabled={uninstalling}
                    onClick={() => handleUninstall(skill)}
                  >
                    {uninstalling
                      ? t("common.uninstalling")
                      : t("common.uninstall")}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
