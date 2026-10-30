import Link from "next/link";
import "../feed.css";

const GITHUB = "https://github.com/wurtz-codez/applyr";

export default function JobsLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="feed">
      <div className="feed-grain" aria-hidden="true" />
      <header className="feed-nav">
        <Link href="/" className="feed-brand" aria-label="Applyr home">
          <span className="feed-brand-mark" aria-hidden="true">a</span>
          <span className="feed-brand-word">applyr</span>
          <span className="feed-brand-sup">/ feed</span>
        </Link>
        <nav className="feed-nav-links" aria-label="Main navigation">
          <Link href="/jobs" aria-current="page">The feed</Link>
          <Link href="/#system">How it works</Link>
          <a href={GITHUB} target="_blank" rel="noopener noreferrer">
            GitHub ↗
          </a>
        </nav>
      </header>
      <main className="feed-main">{children}</main>
      <footer className="feed-footer">
        <span>Applyr — multi-source job search</span>
        <a href={GITHUB} target="_blank" rel="noopener noreferrer">
          GitHub ↗
        </a>
        <span>Self-hosted · MIT · 2026</span>
      </footer>
    </div>
  );
}
