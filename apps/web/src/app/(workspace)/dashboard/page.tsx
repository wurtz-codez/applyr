import Link from "next/link";
import { getProfile } from "@/lib/api";

export default async function Dashboard() {
  const profile = await getProfile();
  return <div className="space-y-8">
    <div><p className="mb-3 text-sm font-bold uppercase tracking-widest text-emerald-800">Your workspace</p>
      <h1 className="text-4xl font-semibold">{profile ? `Welcome, ${profile.full_name}.` : "Build your job search foundation."}</h1>
      <p className="mt-4 max-w-2xl text-slate-600">Discover better-fit roles. Prepare stronger applications. Stay in control of every submission.</p>
    </div>
    <div className="grid gap-5 sm:grid-cols-3">
      {[ ["Verified facts", String(profile?.facts.length ?? 0)], ["Target location", "India + eligible remote"], ["Experience", "0–2 years"] ].map(([label, value]) =>
        <section className="panel" key={label}><h2 className="text-sm text-slate-600">{label}</h2><p className="mt-3 text-xl font-semibold">{value}</p></section>)}
    </div>
    <section className="panel space-y-4">
      <h2 className="text-2xl font-semibold">Start with what you know.</h2>
      <p className="text-slate-600">Add skills, education, experience, and projects you can verify. These facts will support future matching and application drafts.</p>
      <Link href="/profile" className="inline-block font-semibold">{profile ? "Review your profile →" : "Create your verified profile →"}</Link>
    </section>
    <section className="panel space-y-3">
      <h2 className="text-xl font-semibold">Job discovery is coming next.</h2>
      <p className="text-slate-600">This foundation release supports your profile. Career-board discovery, eligibility checks, matching, and run history are planned next. Applications remain manual.</p>
    </section>
  </div>;
}
