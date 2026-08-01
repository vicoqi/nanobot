/**
 * Tests for the SkillsDiscover view.
 *
 * The webui-manager has no React component test environment wired up (no
 * ``@testing-library/react``, no jsdom/happy-dom, and bun:test ships no DOM).
 * Per the Task 9 brief's degraded approach, the testable pure logic is
 * extracted into ``src/lib/skillsDiscover.ts`` (source-filter table,
 * install-source resolver, description fallback, source-label mapper,
 * trending-vs-search switch, and a trailing-edge debounce) and exercised
 * here directly with ``bun:test``. The React component itself is not
 * rendered; it is covered by the type checker and manual smoke.
 *
 * Uses bun's built-in test runner (``bun:test``), matching ``api.test.ts``.
 */
import { describe, it, expect } from "bun:test";
import {
  SOURCE_FILTERS,
  pickInstallSource,
  skillDescription,
  skillSourceLabel,
  isSkillInstalled,
  shouldShowTrending,
  debounce,
} from "../lib/skillsDiscover";
import type { MarketplaceSkill } from "../lib/api";

/** Build a MarketplaceSkill with sensible defaults; ``over`` wins. */
function makeSkill(over: Partial<MarketplaceSkill> = {}): MarketplaceSkill {
  return {
    id: "s1",
    name: "Default Name",
    source: "skills_sh",
    installed: false,
    ...over,
  };
}

describe("SOURCE_FILTERS", () => {
  it("exposes all/skills_sh/skillhub in fixed order with stable label keys", () => {
    expect(SOURCE_FILTERS.map((f) => f.value)).toEqual([
      "all",
      "skills_sh",
      "skillhub",
    ]);
    for (const f of SOURCE_FILTERS) {
      expect(f.labelKey.startsWith("admin.skillsDiscover.")).toBe(true);
    }
  });
});

describe("pickInstallSource", () => {
  it("prefers skill.source when present", () => {
    expect(
      pickInstallSource(makeSkill({ source: "skillhub", provider: "skills_sh" })),
    ).toBe("skillhub");
  });

  it("falls back to provider when source is missing", () => {
    expect(
      pickInstallSource(
        makeSkill({ source: undefined, provider: "skillhub" }),
      ),
    ).toBe("skillhub");
  });

  it("falls back to skills_sh default when both source and provider are missing", () => {
    expect(
      pickInstallSource(makeSkill({ source: undefined, provider: undefined })),
    ).toBe("skills_sh");
  });

  it("treats empty/whitespace source as missing and falls through", () => {
    expect(
      pickInstallSource(makeSkill({ source: "   ", provider: "skillhub" })),
    ).toBe("skillhub");
  });

  it("treats empty/whitespace provider as missing and falls through", () => {
    expect(
      pickInstallSource(
        makeSkill({ source: undefined, provider: "  " }),
      ),
    ).toBe("skills_sh");
  });
});

describe("skillDescription", () => {
  it("returns trimmed description when present", () => {
    expect(skillDescription(makeSkill({ description: "  does X  " }))).toBe(
      "does X",
    );
  });

  it("falls back to name when description is missing", () => {
    expect(
      skillDescription(makeSkill({ description: undefined, name: "N" })),
    ).toBe("N");
  });

  it("falls back to name when description is empty/whitespace", () => {
    expect(skillDescription(makeSkill({ description: "   ", name: "N" }))).toBe(
      "N",
    );
  });
});

describe("skillSourceLabel", () => {
  it("labels skills_sh as the public brand 'skills.sh'", () => {
    expect(skillSourceLabel(makeSkill({ source: "skills_sh" }))).toBe(
      "skills.sh",
    );
  });

  it("labels skillhub as 'SkillHub'", () => {
    expect(skillSourceLabel(makeSkill({ source: "skillhub" }))).toBe(
      "SkillHub",
    );
  });

  it("surfaces unknown providers verbatim", () => {
    expect(skillSourceLabel(makeSkill({ source: "other" }))).toBe("other");
  });

  it("falls back to skills.sh brand when both source and provider are empty", () => {
    expect(
      skillSourceLabel(makeSkill({ source: undefined, provider: undefined })),
    ).toBe("skills.sh");
  });
});

describe("isSkillInstalled", () => {
  it("is true only when installed === true (strict)", () => {
    expect(isSkillInstalled(makeSkill({ installed: true }))).toBe(true);
    expect(isSkillInstalled(makeSkill({ installed: false }))).toBe(false);
    expect(isSkillInstalled(makeSkill({ installed: undefined }))).toBe(false);
  });
});

describe("shouldShowTrending", () => {
  it("is true for empty or whitespace query", () => {
    expect(shouldShowTrending("")).toBe(true);
    expect(shouldShowTrending("   ")).toBe(true);
    expect(shouldShowTrending("\t\n")).toBe(true);
  });

  it("is false once the user types real content", () => {
    expect(shouldShowTrending("weather")).toBe(false);
    expect(shouldShowTrending("  weather  ")).toBe(false);
  });
});

describe("debounce", () => {
  it("coalesces rapid calls into one trailing invocation with the latest args", async () => {
    const calls: string[] = [];
    const debounced = debounce((s: string) => {
      calls.push(s);
    }, 20);

    debounced("a");
    debounced("b");
    debounced("c");

    // Synchronous section: nothing has fired yet.
    expect(calls.length).toBe(0);

    await wait(45);
    expect(calls).toEqual(["c"]);
  });

  it("resets the wait window on each subsequent call", async () => {
    const calls: number[] = [];
    const debounced = debounce((n: number) => {
      calls.push(n);
    }, 25);

    debounced(1);
    await wait(15);
    debounced(2);
    await wait(15);
    debounced(3);
    await wait(40);

    expect(calls).toEqual([3]);
  });

  it("cancel() suppresses the pending trailing call", async () => {
    const calls: string[] = [];
    const debounced = debounce((s: string) => {
      calls.push(s);
    }, 20);

    debounced("a");
    debounced.cancel();
    await wait(45);

    expect(calls.length).toBe(0);
  });

  it("is safe to call cancel() when no timer is pending", () => {
    const debounced = debounce(() => {}, 20);
    expect(() => debounced.cancel()).not.toThrow();
  });
});

function wait(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
