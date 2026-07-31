/**
 * i18n consistency tests for the skills marketplace.
 *
 * Locks down two classes of regression that are easy to introduce when a
 * feature is added in one locale and forgotten in the other:
 *
 *   1. **Structural parity** — ``en`` and ``zh`` must expose the same set of
 *      translation keys. A missing key falls back to the raw dotted path at
 *      runtime (see ``getNestedValue`` in ``src/i18n/index.tsx``), which
 *      surfaces as an English-looking raw string in the Chinese UI — easy
 *      to miss in manual smoke. This test fails closed instead.
 *
 *   2. **Marketplace coverage** — every key actually consumed by the
 *      Skills Discover / Installed components (and the AdminPage skills
 *      sub-tab) must resolve to a non-empty localized string in both
 *      locales. This catches the case where a key exists under a slightly
 *      different name (e.g. ``sourceSkillhub`` vs ``sourceSkillHub``) and
 *      would silently render the dotted path.
 *
 * Uses bun's built-in test runner (``bun:test``), matching ``api.test.ts``.
 * No DOM is required — this file imports only the two plain TS dictionaries
 * and recurses their shape, so it stays in the ``.test.ts`` (not
 * ``.test.tsx``-with-jsdom) tier.
 */
import { describe, it, expect } from "bun:test";
import en from "../i18n/en";
import zh from "../i18n/zh";

/**
 * Collect every leaf path in a nested dictionary as a dotted string.
 * Non-plain-object values (strings, numbers, arrays) are treated as leaves
 * — our dictionaries only use ``{ nested }`` or ``string``, but defending
 * against other leaf types keeps the helper robust if someone adds a
 * numeric count later.
 */
function collectKeys(obj: unknown, prefix = ""): string[] {
  if (obj === null || typeof obj !== "object") {
    return prefix ? [prefix] : [];
  }
  if (Array.isArray(obj)) {
    return prefix ? [prefix] : [];
  }
  const out: string[] = [];
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object" && !Array.isArray(v)) {
      out.push(...collectKeys(v, path));
    } else {
      out.push(path);
    }
  }
  return out.sort();
}

/** Resolve a dotted path to its leaf value, or ``undefined`` if missing. */
function resolve(obj: unknown, path: string): unknown {
  let cur: unknown = obj;
  for (const seg of path.split(".")) {
    if (cur !== null && typeof cur === "object" && seg in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[seg];
    } else {
      return undefined;
    }
  }
  return cur;
}

describe("i18n structural parity", () => {
  it("en and zh expose the same set of top-level namespaces", () => {
    const enTop = Object.keys(en).sort();
    const zhTop = Object.keys(zh).sort();
    expect(enTop).toEqual(zhTop);
  });

  it("en and zh expose the same set of leaf translation keys", () => {
    const enKeys = collectKeys(en);
    const zhKeys = collectKeys(zh);
    // Snapshot the counts so a future addition that forgets one locale
    // produces a readable diff in the failure output rather than just
    // "sets are not equal".
    expect(enKeys.length).toBe(zhKeys.length);
    expect(enKeys).toEqual(zhKeys);
  });

  it("admin namespace has identical key shape in both locales", () => {
    const enAdmin = collectKeys(en.admin);
    const zhAdmin = collectKeys(zh.admin);
    expect(enAdmin).toEqual(zhAdmin);
  });

  it("skillsDiscover and skillsInstalled sub-trees exist and are object-valued in both locales", () => {
    for (const ns of ["admin.skillsDiscover", "admin.skillsInstalled"] as const) {
      const enLeaf = resolve(en, ns);
      const zhLeaf = resolve(zh, ns);
      expect(typeof enLeaf).toBe("object");
      expect(enLeaf).not.toBeNull();
      expect(typeof zhLeaf).toBe("object");
      expect(zhLeaf).not.toBeNull();
    }
  });
});

describe("skills marketplace key coverage", () => {
  // Every key the Skills Discover / Installed components and the AdminPage
  // skills sub-tab actually pass to ``t(...)``. If any of these is renamed
  // or removed, the corresponding component would silently render the raw
  // dotted path — this test makes that regression visible.
  const MARKETPLACE_KEYS: readonly string[] = [
    // AdminPage skills sub-tab header.
    "admin.tabSkills",
    "admin.skillsTabDiscover",
    "admin.skillsTabInstalled",
    // SkillsDiscover — search input, source-filter button group, status row,
    // empty state, and the install button's "Installed" label.
    "admin.skillsDiscover.searchPlaceholder",
    "admin.skillsDiscover.sourceAll",
    "admin.skillsDiscover.sourceSkillsSh",
    "admin.skillsDiscover.sourceSkillHub",
    "admin.skillsDiscover.trending",
    "admin.skillsDiscover.results",
    "admin.skillsDiscover.empty",
    "admin.skillsDiscover.installed",
    // SkillsInstalled — header, cascade confirm prompt, post-uninstall
    // toasts (cleaned / noAgents / failed), and empty state.
    "admin.skillsInstalled.title",
    "admin.skillsInstalled.subtitle",
    "admin.skillsInstalled.confirm",
    "admin.skillsInstalled.empty",
    "admin.skillsInstalled.cleaned",
    "admin.skillsInstalled.noAgents",
    "admin.skillsInstalled.failed",
    // Shared common labels reused by both views.
    "common.install",
    "common.uninstall",
    "common.installing",
    "common.uninstalling",
    "common.loading",
  ] as const;

  for (const key of MARKETPLACE_KEYS) {
    it(`[${key}] resolves to a non-empty string in en`, () => {
      const v = resolve(en, key);
      expect(typeof v).toBe("string");
      expect((v as string).trim().length).toBeGreaterThan(0);
    });

    it(`[${key}] resolves to a non-empty string in zh`, () => {
      const v = resolve(zh, key);
      expect(typeof v).toBe("string");
      expect((v as string).trim().length).toBeGreaterThan(0);
    });
  }

  it("cleaned toast carries the {n} placeholder in both locales", () => {
    expect((resolve(en, "admin.skillsInstalled.cleaned") as string)).toContain("{n}");
    expect((resolve(zh, "admin.skillsInstalled.cleaned") as string)).toContain("{n}");
  });
});
