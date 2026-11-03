import Link from "next/link";
import { ApiError, getRegisteredSources, getIngestionRuns } from "@/lib/api";
import { FeedOffline } from "@/components/feed/offline";
import { SourceConsole } from "@/components/feed/source-console";

export const dynamic = "force-dynamic";
export const metadata = { title: "Sources — Applyr" };

export default async function SourcesPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const page = Math.min(100000, Math.max(1, Number(raw.page) || 1));
  const runPage = Math.min(100000, Math.max(1, Number(raw.runs) || 1));
  try {
    const [sources, runs] = await Promise.all([getRegisteredSources(page), getIngestionRuns(runPage)]);
    return <>
      <section className="feed-hero"><div className="feed-hero-copy">
        <p className="feed-tag">[02] — Sources</p>
        <h1>Your <em>coverage.</em></h1>
        <p className="feed-hero-lede">Company boards, synchronization health, and recent ingestion runs.</p>
      </div></section>
      <SourceConsole sources={sources.items} runs={runs.items} />
      <nav className="source-pagination" aria-label="Source pages">
        {page > 1 && <Link className="feed-btn" href={`?page=${page - 1}&runs=${runPage}`}>Previous sources</Link>}
        <span>Sources page {page} · {sources.total} registered</span>
        {page * sources.page_size < sources.total && <Link className="feed-btn" href={`?page=${page + 1}&runs=${runPage}`}>Next sources</Link>}
      </nav>
      <nav className="source-pagination" aria-label="Run pages">
        {runPage > 1 && <Link className="feed-btn" href={`?page=${page}&runs=${runPage - 1}`}>Previous runs</Link>}
        <span>Runs page {runPage} · {runs.total} total</span>
        {runPage * runs.page_size < runs.total && <Link className="feed-btn" href={`?page=${page}&runs=${runPage + 1}`}>Next runs</Link>}
      </nav>
    </>;
  } catch (error) {
    return <FeedOffline message={error instanceof ApiError ? error.message : "Sources could not be loaded."}
      status={error instanceof ApiError ? error.status : 0} />;
  }
}
