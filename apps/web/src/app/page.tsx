import Link from "next/link";
import { HeroObject } from "@/components/landing/hero-object";
import { LandingMotion } from "@/components/landing/landing-motion";
import "./landing.css";

const GITHUB = "https://github.com/wurtz-codez/applyr";

export const metadata = {
  title: "Applyr — Less noise. More signal.",
  description:
    "A self-hosted workspace for multi-source job aggregation, eligibility filters and application tracking.",
};

const marqueeItems = [
  "Multi-source aggregation",
  "Deduplicated feeds",
  "Eligibility gates",
  "Dashboard filters",
  "Relevance scores",
  "Application tracker",
  "Self-hosted",
];

export default function Home() {
  return (
    <LandingMotion>
      <div className="lp">
        <div className="lp-grain" aria-hidden="true" />

        <header className="lp-nav">
          <a href="#top" className="lp-brand" aria-label="Applyr home">
            <span className="lp-brand-mark" aria-hidden="true">a</span>
            <span className="lp-brand-word">applyr</span>
            <span className="lp-brand-sup">/ jobpilot</span>
          </a>
          <nav className="lp-nav-links" aria-label="Landing navigation">
            <a href="#system">The system</a>
            <a href="#signal">The signal</a>
            <a href={GITHUB} target="_blank" rel="noopener noreferrer">
              GitHub ↗
            </a>
            <Link href="/jobs" className="lp-btn lp-btn--nav">
              Open the feed <span className="lp-btn-arrow" aria-hidden="true">↗</span>
            </Link>
          </nav>
        </header>

        <main id="top">
          <section className="lp-hero" aria-labelledby="hero-title">
            <span className="lp-rail" aria-hidden="true">
              Aggregate · Filter · Track
            </span>

            <div className="lp-hero-copy">
              <p className="lp-eyebrow">
                <span className="lp-dot" />
                Self-hosted job aggregation — backend-first · v0.1
              </p>
              <h1 className="lp-hero-title" id="hero-title">
                <span className="lp-line"><span>Job search,</span></span>
                <span className="lp-line lp-line--indent">
                  <span>on <em>autopilot.</em></span>
                </span>
              </h1>
              <p className="lp-hero-sub">
                One quiet feed for multi-source discovery, eligibility filters
                and the applications you actually send.
              </p>
              <div className="lp-hero-actions">
                <Link href="/jobs" className="lp-btn">
                  Open the feed <span className="lp-btn-arrow" aria-hidden="true">↗</span>
                </Link>
                <a href="#system" className="lp-link">
                  See the system <span aria-hidden="true">↓</span>
                </a>
              </div>
              <p className="lp-micro">No auto-apply · You stay in control</p>
            </div>

            <div className="lp-hero-visual">
              <div className="lp-visual-meta">
                <span><i className="lp-live-dot" /> Aggregation engine</span>
                <span>SYS / 001</span>
              </div>

              <div className="lp-canvas-wrap">
                <div className="lp-canvas-halo" aria-hidden="true" />
                <HeroObject />
              </div>

              <span className="lp-chip lp-chip--a">
                <i className="lp-chip-dot" /> Sources <b>03</b>
              </span>
              <span className="lp-chip lp-chip--b">Remote · India</span>
              <span className="lp-chip lp-chip--c">0–2 yrs</span>
              <span className="lp-chip lp-chip--d">Filters ✓</span>

              <div className="lp-scroll-note">
                <span>Scroll to scan</span>
                <i aria-hidden="true" />
              </div>
            </div>
          </section>

          <div className="lp-marquee" aria-hidden="true">
            <div className="lp-marquee-track">
              {[0, 1].map((group) => (
                <div className="lp-marquee-group" key={group}>
                  {marqueeItems.map((item) => (
                    <span key={`${group}-${item}`}>
                      <span className="lp-marquee-word">{item}</span>
                      <span className="lp-marquee-star">✳</span>
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>

          <section className="lp-system" id="system" aria-labelledby="system-title">
            <div className="lp-system-head" data-reveal>
              <p className="lp-tag">[01] — The system</p>
              <div className="lp-system-title-row">
                <h2 id="system-title">
                  Three quiet <em>moves.</em>
                </h2>
                <p className="lp-note">
                  Aggregation, filters and tracking. No noise. No auto-apply.
                </p>
              </div>
            </div>

            <div className="lp-track">
              <article className="lp-step">
                <div className="lp-step-meta">
                  <span className="lp-step-num">01</span>
                  <span>Aggregate</span>
                </div>
                <div className="lp-step-copy">
                  <h3>One quiet <em>feed.</em></h3>
                  <p>Multi-source discovery, deduped and gated.</p>
                </div>
                <div className="lp-visual lp-visual--rows">
                  <div className="lp-list-head">
                    <span>Role · source</span>
                    <span>Score</span>
                  </div>
                  <div className="lp-row">
                    <span className="lp-row-num">01</span>
                    <span className="lp-row-main">
                      <b>Backend Engineer</b>
                      <small>Northwind · Remote</small>
                    </span>
                    <span className="lp-pill lp-pill--lime">92</span>
                  </div>
                  <div className="lp-row">
                    <span className="lp-row-num">02</span>
                    <span className="lp-row-main">
                      <b>Frontend Engineer</b>
                      <small>Lumen Studio · Bengaluru</small>
                    </span>
                    <span className="lp-pill">88</span>
                  </div>
                  <div className="lp-row">
                    <span className="lp-row-num">03</span>
                    <span className="lp-row-main">
                      <b>New Grad SWE</b>
                      <small>Orbit · Hyderabad</small>
                    </span>
                    <span className="lp-pill">84</span>
                  </div>
                  <div className="lp-row lp-row--dim">
                    <span className="lp-row-num">04</span>
                    <span className="lp-row-main">
                      <b>Platform Engineer</b>
                      <small>Cedar · Remote</small>
                    </span>
                    <span className="lp-pill">76</span>
                  </div>
                  <div className="lp-row lp-row--dim">
                    <span className="lp-row-num">05</span>
                    <span className="lp-row-main">
                      <b>Data Engineer</b>
                      <small>Willow · Remote</small>
                    </span>
                    <span className="lp-pill">71</span>
                  </div>
                  <div className="lp-row lp-row--dim">
                    <span className="lp-row-num">06</span>
                    <span className="lp-row-main">
                      <b>Senior Staff Engineer</b>
                      <small>Filtered · 8+ years</small>
                    </span>
                    <span className="lp-pill lp-pill--ghost">—</span>
                  </div>
                  <div className="lp-list-foot">
                    <span>06 sources</span>
                    <span>128 fetched · 41 gated</span>
                  </div>
                </div>
              </article>

              <article className="lp-step">
                <div className="lp-step-meta">
                  <span className="lp-step-num">02</span>
                  <span>Filter</span>
                </div>
                <div className="lp-step-copy">
                  <h3>Keep the <em>signal.</em></h3>
                  <p>Eligibility gates and dashboard filters.</p>
                </div>
                <div className="lp-visual lp-visual--gates">
                  <div className="lp-gate">
                    <span>Experience · 0–2 years</span>
                    <span className="lp-verdict lp-verdict--pass">Pass</span>
                  </div>
                  <div className="lp-gate">
                    <span>India-eligible remote</span>
                    <span className="lp-verdict lp-verdict--pass">Pass</span>
                  </div>
                  <div className="lp-gate">
                    <span>Seniority requirement</span>
                    <span className="lp-verdict lp-verdict--review">Review</span>
                  </div>
                  <div className="lp-filter-set">
                    <span className="lp-mini-label">Active dashboard filters</span>
                    <div className="lp-chip-row">
                      <span className="lp-chip-small">Backend</span>
                      <span className="lp-chip-small">Remote · IN</span>
                      <span className="lp-chip-small">0–2 yrs</span>
                      <span className="lp-chip-small">+ 3 more</span>
                    </div>
                  </div>
                  <div className="lp-evidence">
                    <span className="lp-mini-label lp-mini-label--light">Filter reason / 001</span>
                    <p>“Backend · remote in India · 0–2 years · Python.”</p>
                    <span className="lp-source">Source · Title · Location</span>
                  </div>
                </div>
              </article>

              <article className="lp-step">
                <div className="lp-step-meta">
                  <span className="lp-step-num">03</span>
                  <span>Track</span>
                </div>
                <div className="lp-step-copy">
                  <h3>Own the <em>thread.</em></h3>
                  <p>Your applications, your call.</p>
                </div>
                <div className="lp-visual lp-visual--track">
                  <div className="lp-timeline">
                    <span className="lp-tl lp-tl--done">Applied</span>
                    <span className="lp-tl lp-tl--active">Interview</span>
                    <span className="lp-tl">Offer</span>
                    <span className="lp-tl">Closed</span>
                  </div>
                  <div className="lp-track-note">
                    <span>Source</span>
                    <span>Company board</span>
                  </div>
                  <div className="lp-track-note">
                    <span>Last update</span>
                    <span>Today, 09:41</span>
                  </div>
                  <div className="lp-track-note">
                    <span>Submitted by</span>
                    <span>You</span>
                  </div>
                  <div className="lp-trace">
                    <span className="lp-mini-label">Latest note</span>
                    <p>“Recruiter screen booked. Prep system design.”</p>
                  </div>
                  <p className="lp-micro">
                    Recording an application never submits anything.
                  </p>
                </div>
              </article>
            </div>
          </section>

          <section className="lp-signal" id="signal" aria-labelledby="signal-title">
            <div className="lp-signal-copy" data-reveal>
              <p className="lp-tag">[02] — The signal</p>
              <h2 id="signal-title">
                Fit, with <em>receipts.</em>
              </h2>
              <p className="lp-signal-lede">
                Every score shows its work — filter gates, weighted components
                and the profile facts behind it. Doubt stays visible.
              </p>
              <div className="lp-weights" aria-label="Match weighting">
                <span>Skills <b>40</b></span>
                <span>Role <b>25</b></span>
                <span>Experience <b>20</b></span>
                <span>Projects <b>15</b></span>
              </div>
              <p className="lp-micro">
                Scores estimate relative fit. They are not hiring probabilities.
              </p>
            </div>

            <div className="lp-match-wrap">
              <div className="lp-match-card">
                <div className="lp-match-top">
                  <span className="lp-live"><i /> Relevance match</span>
                  <span className="lp-mini-label">Example / 001</span>
                </div>

                <div className="lp-match-head">
                  <div>
                    <p className="lp-match-company">Northwind Labs · Remote, India</p>
                    <h3>Backend Engineer</h3>
                    <p className="lp-match-meta">Full-time · 0–2 years · Python / FastAPI</p>
                  </div>
                  <div className="lp-score">
                    <span data-score>92</span>
                    <small>/100</small>
                  </div>
                </div>

                <div className="lp-chip-row">
                  <span className="lp-chip-small">0–2 yrs ✓</span>
                  <span className="lp-chip-small">India eligible ✓</span>
                  <span className="lp-chip-small">No seniority req ✓</span>
                </div>

                <div className="lp-bars">
                  <div className="lp-bar-row">
                    <span>Skills</span>
                    <span className="lp-bar"><span className="lp-bar-fill" style={{ width: "94%" }} /></span>
                    <b>94</b>
                  </div>
                  <div className="lp-bar-row">
                    <span>Role</span>
                    <span className="lp-bar"><span className="lp-bar-fill" style={{ width: "88%" }} /></span>
                    <b>88</b>
                  </div>
                  <div className="lp-bar-row">
                    <span>Experience</span>
                    <span className="lp-bar"><span className="lp-bar-fill" style={{ width: "90%" }} /></span>
                    <b>90</b>
                  </div>
                  <div className="lp-bar-row">
                    <span>Projects</span>
                    <span className="lp-bar"><span className="lp-bar-fill" style={{ width: "82%" }} /></span>
                    <b>82</b>
                  </div>
                </div>

                <div className="lp-evidence-box">
                  <span className="lp-mini-label lp-mini-label--light">Supporting evidence</span>
                  <p>“Designed a FastAPI ingestion pipeline handling 50k records/day.”</p>
                  <span className="lp-source">Profile · Projects · verified</span>
                </div>

                <div className="lp-match-foot">
                  <span>Rule-based · refreshed now</span>
                  <span>Not a hiring probability</span>
                </div>
              </div>

              <div className="lp-seal" aria-hidden="true">
                <svg viewBox="0 0 120 120">
                  <defs>
                    <path
                      id="lp-seal-path"
                      d="M60,60 m-43,0 a43,43 0 1,1 86,0 a43,43 0 1,1 -86,0"
                    />
                  </defs>
                  <text>
                    <textPath href="#lp-seal-path" startOffset="0">
                      Evidence first · No auto-submit ·&nbsp;
                    </textPath>
                  </text>
                </svg>
                <span className="lp-seal-star">✳</span>
              </div>
            </div>
          </section>

          <section className="lp-close" aria-labelledby="close-title">
            <div className="lp-close-mark" aria-hidden="true">✳</div>
            <div className="lp-close-copy" data-reveal>
              <p className="lp-tag lp-tag--light">[03] — Ready when you are</p>
              <h2 id="close-title">
                <span className="lp-line"><span>Stop searching.</span></span>
                <span className="lp-line"><span><em>Start steering.</em></span></span>
              </h2>
              <div className="lp-close-actions">
                <Link href="/jobs" className="lp-btn lp-btn--lime">
                  Open the feed <span className="lp-btn-arrow" aria-hidden="true">↗</span>
                </Link>
                <p className="lp-micro lp-micro--light">
                  Self-hosted. Human-controlled.
                  <br />
                  You approve every move.
                </p>
              </div>
            </div>
          </section>
        </main>

        <footer className="lp-footer">
          <span>Applyr — multi-source job search</span>
          <a href={GITHUB} target="_blank" rel="noopener noreferrer">
            GitHub ↗
          </a>
          <span>Self-hosted · MIT · © 2026</span>
        </footer>
      </div>
    </LandingMotion>
  );
}
