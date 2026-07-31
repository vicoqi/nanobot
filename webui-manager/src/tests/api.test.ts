/**
 * Tests for the admin skills-marketplace API client.
 *
 * Uses bun's built-in test runner (``bun:test``) rather than vitest — the
 * repo has no vitest install and ``bun test`` runs without extra deps.
 *
 * NOTE: imports are RELATIVE (``../lib/api``) because bun's test runner does
 * not resolve the ``@/*`` tsconfig path alias that Vite resolves at build
 * time for the app code.
 */

import { describe, it, expect, beforeEach, afterEach, mock } from "bun:test";
import {
  searchMarketplace,
  trendingMarketplace,
  installMarketplaceSkill,
  listInstalledSkills,
  uninstallGlobalSkill,
} from "../lib/api";

// Must match the key used by ``src/lib/auth.ts`` (adminToken store).
const TOKEN_KEY = "nanobot_manager_admin_token";

// bun's test runtime does not ship a browser ``localStorage`` global, but
// ``src/lib/auth.ts`` reads the admin token through ``localStorage.getItem``.
// Install a minimal in-memory stub so the auth store works under test.
const store = new Map<string, string>();
const localStorageStub = {
  getItem: (k: string): string | null => (store.has(k) ? store.get(k)! : null),
  setItem: (k: string, v: string): void => {
    store.set(k, String(v));
  },
  removeItem: (k: string): void => {
    store.delete(k);
  },
  clear: (): void => store.clear(),
};
(globalThis as unknown as { localStorage: typeof localStorageStub }).localStorage =
  localStorageStub;

/** Build a minimal fetch Response for the ``request()`` helper. */
function jsonResponse(body: unknown, init?: { ok?: boolean; status?: number }): Response {
  const ok = init?.ok ?? true;
  const status = init?.status ?? (ok ? 200 : 500);
  return {
    ok,
    status,
    json: async () => body,
  } as Response;
}

/**
 * Typed handle on the active fetch mock. Kept separately from
 * ``global.fetch`` (which has the wider ``typeof fetch`` type) so we can read
 * ``.mock.calls`` without casting on every assertion.
 */
let fetchMock: ReturnType<typeof mock>;

/** Capture the URL + init of the last fetch call. */
function lastCall(): { url: string; init: RequestInit } {
  const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
  const last = calls[calls.length - 1];
  return { url: last[0], init: last[1] };
}

beforeEach(() => {
  fetchMock = mock(async () => jsonResponse({}));
  global.fetch = fetchMock as unknown as typeof fetch;
  localStorage.setItem(TOKEN_KEY, "T");
});

afterEach(() => {
  localStorage.removeItem(TOKEN_KEY);
});

describe("searchMarketplace", () => {
  it("hits the admin search endpoint with q + source and the admin JWT", async () => {
    (global.fetch as unknown as ReturnType<typeof mock>).mockImplementation(async () =>
      jsonResponse({
        query: "hello world",
        skills: [{ id: "x/y", name: "Y", installed: false }],
        provider: "all",
        install_supported: true,
      })
    );

    const res = await searchMarketplace("hello world", "skills_sh");

    const { url, init } = lastCall();
    // Query params URL-encoded via URLSearchParams.
    expect(url).toBe("/api/admin/skills/marketplace/search?q=hello+world&source=skills_sh");
    expect(init.method).toBeUndefined(); // default GET
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer T");

    expect(res.skills[0].id).toBe("x/y");
  });

  it("defaults source to 'all'", async () => {
    await searchMarketplace("q");
    expect(lastCall().url).toBe("/api/admin/skills/marketplace/search?q=q&source=all");
  });

  it("URL-encodes special characters in the query", async () => {
    await searchMarketplace("a&b=c");
    expect(lastCall().url).toBe(
      "/api/admin/skills/marketplace/search?q=a%26b%3Dc&source=all"
    );
  });
});

describe("trendingMarketplace", () => {
  it("hits the admin trending endpoint with source and the admin JWT", async () => {
    (global.fetch as unknown as ReturnType<typeof mock>).mockImplementation(async () =>
      jsonResponse({
        skills: [{ id: "s/k", name: "K", installed: true }],
        period: "24h",
        provider: "skills_sh",
        install_supported: true,
      })
    );

    const res = await trendingMarketplace("skills_sh");

    const { url, init } = lastCall();
    expect(url).toBe("/api/admin/skills/marketplace/trending?source=skills_sh");
    expect(init.method).toBeUndefined();
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer T");
    expect(res.skills[0].installed).toBe(true);
  });

  it("defaults source to 'all'", async () => {
    await trendingMarketplace();
    expect(lastCall().url).toBe("/api/admin/skills/marketplace/trending?source=all");
  });
});

describe("installMarketplaceSkill", () => {
  it("POSTs the camelCase body to the install endpoint with the admin JWT", async () => {
    (global.fetch as unknown as ReturnType<typeof mock>).mockImplementation(async () =>
      jsonResponse({
        installed: true,
        already_installed: false,
        name: "my-skill",
      })
    );

    const res = await installMarketplaceSkill("my-skill", "anthropic", "skills_sh", "1.2.0");

    const { url, init } = lastCall();
    expect(url).toBe("/api/admin/skills/marketplace/install");
    expect(init.method).toBe("POST");
    // Body MUST use camelCase keys (skillId) to match the backend alias.
    expect(JSON.parse(init.body as string)).toEqual({
      skillId: "my-skill",
      source: "anthropic",
      provider: "skills_sh",
      version: "1.2.0",
    });
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer T");
    expect(res.installed).toBe(true);
    expect(res.already_installed).toBe(false);
  });

  it("defaults provider to skills_sh and version to empty string", async () => {
    await installMarketplaceSkill("s", "src");
    expect(JSON.parse(lastCall().init.body as string)).toEqual({
      skillId: "s",
      source: "src",
      provider: "skills_sh",
      version: "",
    });
  });
});

describe("listInstalledSkills", () => {
  it("GETs the installed-skills list with the admin JWT", async () => {
    (global.fetch as unknown as ReturnType<typeof mock>).mockImplementation(async () =>
      jsonResponse({
        skills: [
          { name: "github", description: "GitHub skill" },
          { name: "cron", description: "Cron skill" },
        ],
      })
    );

    const res = await listInstalledSkills();

    const { url, init } = lastCall();
    expect(url).toBe("/api/admin/skills");
    expect(init.method).toBeUndefined();
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer T");
    expect(res.skills).toHaveLength(2);
    expect(res.skills[0].name).toBe("github");
  });
});

describe("uninstallGlobalSkill", () => {
  it("DELETEs the skill by URL-encoded name with the admin JWT", async () => {
    (global.fetch as unknown as ReturnType<typeof mock>).mockImplementation(async () =>
      jsonResponse({ success: true, cleanedWorkspaces: 3 })
    );

    const res = await uninstallGlobalSkill("my skill");

    const { url, init } = lastCall();
    // Path segment is encodeURIComponent-encoded (space -> %20, not +).
    expect(url).toBe("/api/admin/skills/my%20skill");
    expect(init.method).toBe("DELETE");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer T");
    expect(res.success).toBe(true);
    expect(res.cleanedWorkspaces).toBe(3);
  });

  it("URL-encodes path-traversal characters in the name", async () => {
    await uninstallGlobalSkill("..%2f");
    // encodeURIComponent encodes "/" but not "."; backend whitelist rejects
    // traversal regardless. We only assert the wire path here.
    expect(lastCall().url).toBe("/api/admin/skills/..%252f");
  });
});
