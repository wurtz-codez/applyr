"use client";

import { useCallback, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { FacetValue } from "@/lib/job-types";
import {
  CURRENCIES,
  POSTED_OPTIONS,
  PROVIDER_LABELS,
  SALARY_PERIODS,
  WORK_MODE_LABELS,
  activeFilterChips,
  parseFeedFilters,
} from "@/lib/feed-filters";

type Props = {
  workModes: FacetValue[];
  employmentTypes: FacetValue[];
  experienceLevels: FacetValue[];
  locations: FacetValue[];
  tags: FacetValue[];
  sources: FacetValue[];
};

function Group({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="feed-filter-group">
      <div className="feed-filter-label">
        <span>{label}</span>
        {hint && <span>{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function Chip({
  active,
  count,
  onClick,
  children,
}: {
  active: boolean;
  count?: number;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={`feed-chip${active ? " is-active" : ""}`}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
      {typeof count === "number" && <b>{count}</b>}
    </button>
  );
}

export function FeedFilterPanel({
  workModes,
  employmentTypes,
  experienceLevels,
  locations,
  tags,
  sources,
}: Props) {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [open, setOpen] = useState(false);

  const filters = parseFeedFilters(searchParams);
  const activeCount = activeFilterChips(filters).length;

  const push = useCallback(
    (mutate: (params: URLSearchParams) => void) => {
      const next = new URLSearchParams(searchParams.toString());
      mutate(next);
      next.delete("page");
      const query = next.toString();
      startTransition(() => {
        router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
      });
    },
    [pathname, router, searchParams],
  );

  const setSingle = (key: string, value: string) => {
    push((params) => {
      if (value) params.set(key, value);
      else params.delete(key);
    });
  };

  const toggleMulti = (key: string, value: string) => {
    push((params) => {
      const current = params.getAll(key);
      params.delete(key);
      if (!current.includes(value)) current.push(value);
      current.forEach((item) => params.append(key, item));
    });
  };

  const clearAll = () => {
    startTransition(() => router.push("/jobs", { scroll: false }));
  };

  const isLocation = (value: string) =>
    filters.location.toLowerCase() === value.toLowerCase();

  return (
    <aside className="feed-filters" aria-label="Filter listings">
      <button
        type="button"
        className="feed-filter-toggle"
        aria-expanded={open}
        aria-controls="feed-filter-panel"
        onClick={() => setOpen((value) => !value)}
      >
        <span>{open ? "Hide filters" : "Filters"}</span>
        <b>{activeCount}</b>
      </button>

      <div
        id="feed-filter-panel"
        className={`feed-filter-panel${open ? " is-open" : ""}`}
      >
        <div className="feed-filter-head">
          <span>Filter the feed</span>
          {pending ? (
            <span className="feed-pending-label">Updating…</span>
          ) : (
            activeCount > 0 && (
              <button type="button" className="feed-text-btn" onClick={clearAll}>
                Clear all
              </button>
            )
          )}
        </div>

        <Group label="Listing type">
          <div className="feed-segmented">
            {[
              { value: "jobs", label: "Jobs" },
              { value: "all", label: "All" },
              { value: "search", label: "Search pages" },
            ].map((item) => (
              <button
                key={item.value}
                type="button"
                className={filters.type === item.value ? "is-active" : ""}
                aria-pressed={filters.type === item.value}
                onClick={() => setSingle("type", item.value === "jobs" ? "" : item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </Group>

        <Group label="Work mode">
          <div className="feed-chip-wrap">
            <Chip active={!filters.workMode} onClick={() => setSingle("work_mode", "")}>
              Any
            </Chip>
            {workModes.map((item) => (
              <Chip
                key={item.value}
                active={filters.workMode === item.value}
                count={item.count}
                onClick={() =>
                  setSingle("work_mode", filters.workMode === item.value ? "" : item.value)
                }
              >
                {WORK_MODE_LABELS[item.value] ?? item.value}
              </Chip>
            ))}
          </div>
        </Group>

        <Group label="Source">
          <div className="feed-check-list">
            {sources.map((item) => (
              <label className="feed-check" key={item.value}>
                <input
                  type="checkbox"
                  checked={filters.sources.includes(item.value)}
                  onChange={() => toggleMulti("source", item.value)}
                />
                <span>{PROVIDER_LABELS[item.value] ?? item.value}</span>
                <span className="feed-check-count">{item.count}</span>
              </label>
            ))}
          </div>
        </Group>

        <Group label="Employment">
          <div className="feed-chip-wrap">
            <Chip
              active={!filters.employmentType}
              onClick={() => setSingle("employment_type", "")}
            >
              Any
            </Chip>
            {employmentTypes.map((item) => (
              <Chip
                key={item.value}
                active={
                  filters.employmentType.toLowerCase() === item.value.toLowerCase()
                }
                count={item.count}
                onClick={() =>
                  setSingle(
                    "employment_type",
                    filters.employmentType.toLowerCase() === item.value.toLowerCase()
                      ? ""
                      : item.value,
                  )
                }
              >
                {item.value}
              </Chip>
            ))}
          </div>
        </Group>

        <Group label="Experience">
          <select
            className="feed-select"
            value={filters.experienceLevel}
            onChange={(event) => setSingle("experience_level", event.target.value)}
            aria-label="Experience level"
          >
            <option value="">Any level</option>
            {experienceLevels.map((item) => (
              <option key={item.value} value={item.value}>
                {item.value} ({item.count})
              </option>
            ))}
          </select>
        </Group>

        <Group label="Location">
          <form
            key={filters.location}
            className="feed-inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              setSingle("location", String(data.get("location") ?? "").trim());
            }}
          >
            <input
              className="feed-input"
              name="location"
              defaultValue={filters.location}
              placeholder="City or country"
              maxLength={200}
              aria-label="Filter by location"
            />
            <button type="submit" className="feed-form-btn">Set</button>
          </form>
          <div className="feed-chip-wrap feed-chip-wrap--tight">
            {locations.map((item) => (
              <Chip
                key={item.value}
                active={isLocation(item.value)}
                count={item.count}
                onClick={() =>
                  setSingle("location", isLocation(item.value) ? "" : item.value)
                }
              >
                {item.value}
              </Chip>
            ))}
          </div>
        </Group>

        <Group label="Company">
          <form
            key={filters.company}
            className="feed-inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              setSingle("company", String(data.get("company") ?? "").trim());
            }}
          >
            <input
              className="feed-input"
              name="company"
              defaultValue={filters.company}
              placeholder="Company name"
              maxLength={300}
              aria-label="Filter by company"
            />
            <button type="submit" className="feed-form-btn">Set</button>
          </form>
        </Group>

        <Group label="Tags" hint="matches all">
          <div className="feed-chip-wrap">
            {tags.map((item) => (
              <Chip
                key={item.value}
                active={filters.tags.includes(item.value)}
                count={item.count}
                onClick={() => toggleMulti("tag", item.value)}
              >
                #{item.value}
              </Chip>
            ))}
          </div>
        </Group>

        <Group label="Posted">
          <div className="feed-chip-wrap">
            {POSTED_OPTIONS.map((item) => (
              <Chip
                key={item.value || "any"}
                active={filters.postedWithin === item.value}
                onClick={() => setSingle("posted_within_days", item.value)}
              >
                {item.label}
              </Chip>
            ))}
          </div>
        </Group>

        <Group label="Minimum salary">
          <form
            key={`${filters.minSalary}|${filters.currency}|${filters.salaryPeriod}`}
            className="feed-salary-form"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              const minimum = String(data.get("min_salary") ?? "").trim();
              const currency = String(data.get("currency") ?? "USD");
              const period = String(data.get("salary_period") ?? "yearly");
              push((params) => {
                if (minimum && Number(minimum) > 0) {
                  params.set("min_salary", minimum);
                  params.set("currency", currency);
                  params.set("salary_period", period);
                } else {
                  params.delete("min_salary");
                  params.delete("currency");
                  params.delete("salary_period");
                }
              });
            }}
          >
            <div className="feed-salary-row">
              <input
                className="feed-input"
                name="min_salary"
                defaultValue={filters.minSalary}
                placeholder="Minimum"
                inputMode="decimal"
                maxLength={12}
                aria-label="Minimum salary"
              />
              <select
                className="feed-select"
                name="currency"
                defaultValue={filters.currency}
                aria-label="Salary currency"
              >
                {CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>{currency}</option>
                ))}
              </select>
            </div>
            <div className="feed-salary-row">
              <select
                className="feed-select"
                name="salary_period"
                defaultValue={filters.salaryPeriod}
                aria-label="Salary period"
              >
                {SALARY_PERIODS.map((period) => (
                  <option key={period} value={period}>{period}</option>
                ))}
              </select>
              <button type="submit" className="feed-form-btn">Apply</button>
            </div>
            <p className="feed-filter-hint">Only listings with a stated minimum.</p>
          </form>
        </Group>

        <button
          type="button"
          className="feed-filter-done"
          onClick={() => {
            setOpen(false);
            const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
              ? "auto"
              : "smooth";
            document
              .getElementById("feed-results")
              ?.scrollIntoView({ behavior, block: "start" });
          }}
        >
          Show results <span aria-hidden="true">↓</span>
        </button>
      </div>
    </aside>
  );
}
