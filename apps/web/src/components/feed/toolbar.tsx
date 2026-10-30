"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ActiveChip } from "@/lib/feed-filters";
import {
  SORT_OPTIONS,
  activeFilterChips,
  parseFeedFilters,
} from "@/lib/feed-filters";
import { formatCount } from "@/lib/format";

export function FeedToolbar({
  total,
  shown,
}: {
  total: number;
  shown: number;
}) {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const filters = parseFeedFilters(searchParams);
  const [query, setQuery] = useState(filters.q);

  const push = useCallback(
    (mutate: (params: URLSearchParams) => void) => {
      const next = new URLSearchParams(searchParams.toString());
      mutate(next);
      next.delete("page");
      const params = next.toString();
      startTransition(() => {
        router.push(params ? `${pathname}?${params}` : pathname, { scroll: false });
      });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    setQuery(filters.q);
  }, [filters.q]);

  useEffect(() => {
    const next = query.trim();
    if (next === filters.q) return;
    const timeout = window.setTimeout(() => {
      push((params) => {
        if (next) params.set("q", next);
        else params.delete("q");
      });
    }, 380);
    return () => window.clearTimeout(timeout);
  }, [filters.q, push, query]);

  const commitQuery = () => {
    const next = query.trim();
    push((params) => {
      if (next) params.set("q", next);
      else params.delete("q");
    });
  };

  const removeChip = (chip: ActiveChip) => {
    if (chip.key === "min_salary") {
      push((params) => {
        params.delete("min_salary");
        params.delete("currency");
        params.delete("salary_period");
      });
      return;
    }
    if (chip.value) {
      push((params) => {
        const values = params.getAll(chip.key).filter((value) => value !== chip.value);
        params.delete(chip.key);
        values.forEach((value) => params.append(chip.key, value));
      });
      return;
    }
    push((params) => params.delete(chip.key));
  };

  const clearAll = () => {
    startTransition(() => router.push("/jobs", { scroll: false }));
  };

  const chips = activeFilterChips(filters);
  const count = formatCount(total);
  const summary =
    shown < total ? `${count} roles · ${shown} shown` : `${count} roles`;

  return (
    <div className="feed-toolbar">
      <div className="feed-search">
        <label htmlFor="feed-search-input">Search the feed</label>
        <div className="feed-search-field">
          <span className="feed-search-icon" aria-hidden="true" />
          <input
            id="feed-search-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitQuery();
              }
            }}
            placeholder="Role, company or keyword"
            maxLength={200}
            autoComplete="off"
          />
          {query && (
            <button
              type="button"
              className="feed-search-clear"
              aria-label="Clear search"
              onClick={() => {
                setQuery("");
                push((params) => params.delete("q"));
              }}
            >
              ×
            </button>
          )}
        </div>
      </div>

      <div className="feed-toolbar-controls">
        <label className="feed-sort">
          <span>Sort</span>
          <select
            className="feed-select"
            value={filters.sort}
            onChange={(event) =>
              push((params) => {
                if (event.target.value === "newest") params.delete("sort");
                else params.set("sort", event.target.value);
              })
            }
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <span className={`feed-result-count${pending ? " is-pending" : ""}`} aria-live="polite">
          {pending ? "Scanning…" : summary}
        </span>
      </div>

      <div className={`feed-pending${pending ? " is-on" : ""}`} aria-hidden="true" />

      {chips.length > 0 && (
        <div className="feed-active-row">
          <span className="feed-active-label">Active</span>
          {chips.map((chip) => (
            <button
              key={`${chip.key}-${chip.value ?? chip.label}`}
              type="button"
              className="feed-active-chip"
              onClick={() => removeChip(chip)}
            >
              {chip.label}
              <span aria-hidden="true">×</span>
            </button>
          ))}
          <button type="button" className="feed-text-btn" onClick={clearAll}>
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
