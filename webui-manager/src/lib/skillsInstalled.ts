/**
 * Pure, side-effect-free helpers for the Skills Installed view.
 *
 * Extracted from ``src/components/SkillsInstalled.tsx`` so the logic that
 * actually carries branch coverage (description fallback for the installed
 * list, and the install-result → toast-outcome classifier) can be unit-tested
 * under ``bun:test`` without a DOM — the webui-manager has no
 * React testing-library / jsdom wired up, per the Task 9/10 degraded approach.
 *
 * Everything here is deterministic and imports only the ``InstalledSkill`` /
 * ``UninstallSkillResponse`` *types* (erased at runtime), so the module is
 * safe to load in any JS runtime.
 */
import type { InstalledSkill, UninstallSkillResponse } from "./api";

/**
 * Description shown on an installed-skill row. The marketplace
 * ``InstalledSkill`` type declares ``description: string``, but in practice
 * some upstream repos emit an empty string for skills without a front-matter
 * description. Rendering an empty paragraph would look like a broken row, so
 * we fall back to the skill name — mirroring ``skillDescription`` in
 * ``skillsDiscover.ts`` for the marketplace cards.
 */
export function skillInstalledDescription(skill: InstalledSkill): string {
  const d =
    typeof skill.description === "string" ? skill.description.trim() : "";
  return d || skill.name;
}

/**
 * Bucketed outcome of an uninstall call, used by the component to pick the
 * right i18n key for the post-uninstall toast.
 *
 *   - ``cleaned``  → success and ≥1 agent workspace was cascaded. The count
 *                    is surfaced to the user ("cleaned N agent(s)").
 *   - ``noAgents`` → success but zero agents referenced the skill. Worth a
 *                    distinct, softer message so the admin knows nothing was
 *                    disturbed downstream.
 *   - ``failed``   → backend reported ``success: false`` (or the request
 *                    helper threw, in which case the component shows the error
 *                    banner instead and never calls this).
 */
export type UninstallOutcome =
  | { kind: "cleaned"; count: number }
  | { kind: "noAgents" }
  | { kind: "failed" };

/**
 * Classify a ``uninstallGlobalSkill`` response into a toast outcome.
 *
 * ``cleanedWorkspaces`` comes back as a number from the backend contract
 * (``UninstallSkillResponse``), but we defend against a stringified / NaN
 * value rather than trusting the wire shape blindly — a malformed response
 * should land on ``noAgents`` (the least surprising bucket) rather than
 * rendering "NaN agents" in the UI.
 */
export function classifyUninstall(
  res: UninstallSkillResponse,
): UninstallOutcome {
  if (!res.success) return { kind: "failed" };

  const raw = res.cleanedWorkspaces as unknown;
  const count =
    typeof raw === "number" && Number.isFinite(raw)
      ? raw
      : Number(raw) || 0;

  if (count <= 0) return { kind: "noAgents" };
  return { kind: "cleaned", count };
}
