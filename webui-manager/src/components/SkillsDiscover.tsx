import { useState, useEffect, useCallback, useRef } from "react";
import {
  searchMarketplace,
  trendingMarketplace,
  installMarketplaceSkill,
  type MarketplaceSkill,
} from "@/lib/api";
import {
  SOURCE_FILTERS,
  pickInstallSource,
  skillDescription,
  skillSourceLabel,
  isSkillInstalled,
  installSkillId,
  shouldShowTrending,
  debounce,
  type SourceValue,
} from "@/lib/skillsDiscover";
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Marketplace discovery view for the admin skills tab.
 *
 * Layout:
 *   ┌ search input (controlled, 300ms debounce) ┐
 *   ├ source filter: All / skills.sh / SkillHub ┤
 *   ├ status row: "Trending" | "Results" + Loading ┤
 *   └ result grid: name + description + source badge + install button ┘
 *
 * Behavior:
 *   - Empty query → ``trendingMarketplace(source)`` leaderboard.
 *   - Non-empty query → ``searchMarketplace(q, source)``.
 *   - Install button calls ``installMarketplaceSkill(id, source, provider)``
 *     and optimistically flips the card to "Installed" on success; the
 *     surrounding list state is updated in place rather than refetched so
 *     scroll position and trending rank are preserved.
 *
 * The list endpoints wrap results under ``skills`` (NOT ``results``) and
 * ``install`` returns ``{installed, already_installed, name}`` — see the
 * Task 8 contract in ``src/lib/api.ts``.
 */
export default function SkillsDiscover() {
  const { t } = useI18n();

  // Search state. ``query`` mirrors the input immediately so typing feels
  // responsive; ``debouncedQuery`` lags by 300ms and drives the fetch so we
  // don't spam the endpoint on every keystroke.
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  // Stable debounced setter — ``useRef`` keeps the same debounced fn across
  // renders so we don't reset the wait window on every render.
  const debouncedSetQuery = useRef(debounce(setDebouncedQuery, 300)).current;

  const [source, setSource] = useState<SourceValue>("all");
  const [results, setResults] = useState<MarketplaceSkill[]>([]);
  // Start in loading state so the first paint does not flash "empty" before
  // the trending fetch resolves.
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [installingId, setInstallingId] = useState<string | null>(null);

  function onSearchChange(value: string) {
    setQuery(value);
    debouncedSetQuery(value);
  }

  // Search effect — only runs when a real query is present. The trending
  // effect below owns the empty-query branch.
  useEffect(() => {
    if (shouldShowTrending(debouncedQuery)) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    searchMarketplace(debouncedQuery.trim(), source)
      .then((res) => {
        if (cancelled) return;
        setResults(res.skills ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setResults([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, source]);

  // Trending effect — owns the empty-query branch. Fires on mount and
  // whenever the source filter changes while no search term is active.
  useEffect(() => {
    if (!shouldShowTrending(debouncedQuery)) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    trendingMarketplace(source)
      .then((res) => {
        if (cancelled) return;
        setResults(res.skills ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setResults([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, source]);

  const handleInstall = useCallback(async (skill: MarketplaceSkill) => {
    setInstallingId(skill.id);
    try {
      const installSource = pickInstallSource(skill);
      const res = await installMarketplaceSkill(
        installSkillId(skill),
        installSource,
        skill.provider ?? "skills_sh",
      );
      // ``installed`` and ``already_installed`` both mean the skill is now in
      // the global repo; flip the card in place (optimistic refresh).
      if (res.installed || res.already_installed) {
        setResults((prev) =>
          prev.map((s) =>
            s.id === skill.id ? { ...s, installed: true } : s,
          ),
        );
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstallingId(null);
    }
  }, []);

  const showTrending = shouldShowTrending(debouncedQuery);

  return (
    <div className="space-y-4">
      {/* Search */}
      <Input
        type="search"
        placeholder={t("admin.skillsDiscover.searchPlaceholder")}
        value={query}
        onChange={(e) => onSearchChange(e.target.value)}
        className="sm:max-w-md"
        aria-label={t("admin.skillsDiscover.searchPlaceholder")}
      />

      {/* Source filter */}
      <div className="flex flex-wrap gap-2">
        {SOURCE_FILTERS.map((f) => (
          <Button
            key={f.value}
            size="sm"
            variant={source === f.value ? "default" : "outline"}
            onClick={() => setSource(f.value)}
          >
            {t(f.labelKey)}
          </Button>
        ))}
      </div>

      {/* Status row */}
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <span>
          {showTrending
            ? t("admin.skillsDiscover.trending")
            : t("admin.skillsDiscover.results")}
        </span>
        {loading && <span>{t("common.loading")}</span>}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && results.length === 0 && !error && (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("admin.skillsDiscover.empty")}
        </div>
      )}

      {/* Result grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {results.map((skill) => {
          const installed = isSkillInstalled(skill);
          const installing = installingId === skill.id;
          return (
            <div
              key={skill.id}
              className="flex flex-col gap-2 rounded-lg border bg-card p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-medium leading-tight">{skill.name}</h3>
                <span className="shrink-0 rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {skillSourceLabel(skill)}
                </span>
              </div>
              <p className="line-clamp-3 text-sm text-muted-foreground">
                {skillDescription(skill)}
              </p>
              <div className="mt-auto pt-2">
                <Button
                  size="sm"
                  className="w-full"
                  disabled={installed || installing}
                  onClick={() => handleInstall(skill)}
                >
                  {installed
                    ? t("admin.skillsDiscover.installed")
                    : installing
                      ? t("common.installing")
                      : t("common.install")}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
