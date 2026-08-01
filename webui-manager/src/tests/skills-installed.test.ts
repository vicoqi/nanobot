/**
 * Tests for the SkillsInstalled view's pure helpers.
 *
 * Per the Task 10 brief's degraded approach (same as Task 9), the testable
 * pure logic is extracted into ``src/lib/skillsInstalled.ts`` (description
 * fallback for installed rows + the uninstall-result → toast-outcome
 * classifier) and exercised here directly with ``bun:test``. The React
 * component itself is not rendered; it is covered by the type checker and
 * the production build.
 *
 * Imports are RELATIVE (``../lib/...``) because bun's test runner does not
 * resolve the ``@/*`` tsconfig path alias that Vite resolves at build time.
 */
import { describe, it, expect } from "bun:test";
import {
  skillInstalledDescription,
  classifyUninstall,
} from "../lib/skillsInstalled";
import type { InstalledSkill, UninstallSkillResponse } from "../lib/api";

/** Build an InstalledSkill with sensible defaults; ``over`` wins. */
function makeInstalled(over: Partial<InstalledSkill> = {}): InstalledSkill {
  return {
    name: "default-skill",
    description: "does the default thing",
    ...over,
  };
}

describe("skillInstalledDescription", () => {
  it("returns the trimmed description when present", () => {
    expect(
      skillInstalledDescription(makeInstalled({ description: "  does X  " })),
    ).toBe("does X");
  });

  it("falls back to the skill name when description is empty", () => {
    expect(
      skillInstalledDescription(
        makeInstalled({ description: "", name: "fallback-name" }),
      ),
    ).toBe("fallback-name");
  });

  it("falls back to the skill name when description is whitespace only", () => {
    expect(
      skillInstalledDescription(
        makeInstalled({ description: "   \t\n  ", name: "N" }),
      ),
    ).toBe("N");
  });

  it("falls back to the skill name when description is missing entirely", () => {
    // The type says description is required, but the runtime guard defends
    // against malformed upstream payloads where the field is absent.
    expect(
      skillInstalledDescription(
        makeInstalled({ description: undefined as unknown as string, name: "N" }),
      ),
    ).toBe("N");
  });
});

describe("classifyUninstall", () => {
  it("classifies a successful response with ≥1 cleaned workspace as 'cleaned'", () => {
    const res: UninstallSkillResponse = { success: true, cleanedWorkspaces: 3 };
    expect(classifyUninstall(res)).toEqual({ kind: "cleaned", count: 3 });
  });

  it("uses count = 1 (boundary) as 'cleaned'", () => {
    expect(
      classifyUninstall({ success: true, cleanedWorkspaces: 1 }),
    ).toEqual({ kind: "cleaned", count: 1 });
  });

  it("classifies a successful response with zero workspaces as 'noAgents'", () => {
    expect(
      classifyUninstall({ success: true, cleanedWorkspaces: 0 }),
    ).toEqual({ kind: "noAgents" });
  });

  it("classifies success: false as 'failed' regardless of cleanedWorkspaces", () => {
    // Backend may report a partial cleanup count alongside success: false;
    // the user-facing outcome is still "failed".
    expect(
      classifyUninstall({ success: false, cleanedWorkspaces: 5 }),
    ).toEqual({ kind: "failed" });
  });

  it("defends against a stringified cleanedWorkspaces by coercing to a number", () => {
    // Defensive: if the wire shape ever drifts to a string, we still report a
    // meaningful count rather than landing on the failed/noAgents branch.
    expect(
      classifyUninstall({
        success: true,
        cleanedWorkspaces: "4" as unknown as number,
      }),
    ).toEqual({ kind: "cleaned", count: 4 });
  });

  it("treats a non-numeric cleanedWorkspaces as zero (noAgents)", () => {
    expect(
      classifyUninstall({
        success: true,
        cleanedWorkspaces: "NaN-ish" as unknown as number,
      }),
    ).toEqual({ kind: "noAgents" });
  });

  it("treats a negative cleanedWorkspaces as noAgents rather than a negative 'cleaned'", () => {
    // A negative count should never happen, but if it did we do not want to
    // render "cleaned -1 agents" — bucket as noAgents.
    expect(
      classifyUninstall({ success: true, cleanedWorkspaces: -2 }),
    ).toEqual({ kind: "noAgents" });
  });
});
