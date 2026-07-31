/**
 * Pure, side-effect-free helpers for the Skills Discover view.
 *
 * Extracted from ``src/components/SkillsDiscover.tsx`` so the logic that
 * actually has branch coverage (source-filter table, install-source
 * resolution, description fallback, source-label mapping, trending switch,
 * search debounce) can be unit-tested under ``bun:test`` without a DOM
 * (the webui-manager has no React testing-library / jsdom set up).
 *
 * Everything here is deterministic and imports only the ``MarketplaceSkill``
 * *type* (erased at runtime), so the module is safe to load in any JS
 * runtime.
 */
import type { MarketplaceSkill } from "./api";

/** The three source-filter values the UI exposes. */
export type SourceValue = "all" | "skills_sh" | "skillhub";

export interface SourceFilter {
  value: SourceValue;
  /** i18n key resolved by ``useI18n().t(...)`` in the component. */
  labelKey: string;
}

/**
 * Fixed source-filter button group rendered above the result grid.
 * Order matters: All → skills.sh → SkillHub.
 */
export const SOURCE_FILTERS: readonly SourceFilter[] = [
  { value: "all", labelKey: "admin.skillsDiscover.sourceAll" },
  { value: "skills_sh", labelKey: "admin.skillsDiscover.sourceSkillsSh" },
  { value: "skillhub", labelKey: "admin.skillsDiscover.sourceSkillHub" },
] as const;

/**
 * Resolve the ``source`` argument to pass to ``installMarketplaceSkill``.
 *
 * The marketplace row carries both ``source`` (the upstream bucket the row
 * was listed under — ``skills_sh`` / ``skillhub``) and an optional
 * ``provider``. The install endpoint keys off ``source``; we prefer the
 * row's explicit value and fall back to ``provider``, finally the
 * ``skills_sh`` default so a skillhub row that omits ``source`` still hits
 * the right installer rather than 400'ing.
 *
 * Empty/whitespace strings are treated as missing — providers sometimes
 * serialize ``""`` for unknown fields.
 */
export function pickInstallSource(skill: MarketplaceSkill): string {
  const fromSource =
    typeof skill.source === "string" ? skill.source.trim() : "";
  if (fromSource) return fromSource;

  const fromProvider =
    typeof skill.provider === "string" ? skill.provider.trim() : "";
  if (fromProvider) return fromProvider;

  return "skills_sh";
}

/**
 * Description shown on a result card. Not every provider emits one, so we
 * fall back to the skill name rather than rendering an empty paragraph
 * (which would look like a broken card).
 */
export function skillDescription(skill: MarketplaceSkill): string {
  const d =
    typeof skill.description === "string" ? skill.description.trim() : "";
  return d || skill.name;
}

/** Compact human-readable badge label for a skill's upstream source. */
export function skillSourceLabel(skill: MarketplaceSkill): string {
  const raw = (skill.source || skill.provider || "").toString().trim();
  if (raw === "skills_sh") return "skills.sh";
  if (raw === "skillhub") return "SkillHub";
  if (raw) return raw;
  return "skills.sh";
}

/** Strict installed flag — backend emits ``installed: true`` only. */
export function isSkillInstalled(skill: MarketplaceSkill): boolean {
  return skill.installed === true;
}

/**
 * Whether the view should show the trending leaderboard instead of search
 * results. Drives the ``useEffect`` branch in the component: empty query →
 * trending, anything typed → search.
 */
export function shouldShowTrending(query: string): boolean {
  return query.trim() === "";
}

export interface Debounced<A extends unknown[]> {
  (...args: A): void;
  /** Cancel any pending trailing invocation. Safe to call when idle. */
  cancel(): void;
}

/**
 * Trailing-edge debounce. Rapid calls collapse into a single invocation of
 * ``fn`` with the latest arguments, ``ms`` after the last call.
 *
 * Used by the component to debounce the search input (300ms) so each
 * keystroke does not fire a fresh ``/marketplace/search`` round-trip.
 */
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  ms: number,
): Debounced<A> {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const wrapped = (...args: A): void => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, ms);
  };

  return Object.assign(wrapped, {
    cancel(): void {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    },
  });
}
