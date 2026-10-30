import { saveProfile } from "@/app/actions";
import { getProfile } from "@/lib/api";

export default async function ProfilePage({ searchParams }: {
  searchParams: Promise<{ saved?: string; error?: string }>
}) {
  const profile = await getProfile();
  const params = await searchParams;
  const facts = [...(profile?.facts ?? []), ...Array.from({ length: Math.min(3, 200 - (profile?.facts.length ?? 0)) }, () => null)];
  return <div className="space-y-6">
    <h1 className="text-3xl font-semibold">Your verified profile</h1>
    <p className="text-slate-600">Only add facts you can support. Leave unused rows blank. Clear a statement to remove a fact; save to add more rows.</p>
    {params.saved && <p role="status" className="text-emerald-800">Profile saved.</p>}
    {params.error && <p role="alert" className="text-red-700">Check your name, fact statements, and evidence sources, then confirm that your facts are accurate.</p>}
    <form action={saveProfile} className="space-y-6">
      <div className="panel space-y-3"><label htmlFor="full_name">Full name</label>
        <input id="full_name" name="full_name" defaultValue={profile?.full_name} required maxLength={200} />
        {profile && <p className="text-sm text-slate-500">Profile version {profile.current_version}</p>}
      </div>
      <input type="hidden" name="fact_count" value={facts.length} />
      {facts.map((fact, i) => <fieldset className="panel space-y-4" key={fact?.id ?? `new-${i}`}>
        <legend className="px-2 font-semibold">Fact {i + 1}</legend>
        <input type="hidden" name={`id_${i}`} value={fact?.id ?? `new-${crypto.randomUUID()}`} />
        <label htmlFor={`category_${i}`}>Category</label>
        <select id={`category_${i}`} name={`category_${i}`} defaultValue={fact?.category ?? "skill"}>
          <option value="skill">Skill</option><option value="project">Project</option><option value="experience">Experience</option><option value="education">Education</option>
        </select>
        <label htmlFor={`statement_${i}`}>Statement</label>
        <textarea id={`statement_${i}`} name={`statement_${i}`} defaultValue={fact?.statement} rows={2} maxLength={2000} />
        <label htmlFor={`evidence_${i}`}>Evidence source</label>
        <input id={`evidence_${i}`} name={`evidence_${i}`} defaultValue={fact?.evidence_source} maxLength={500} placeholder="Project link, certificate, or your own confirmation" />
      </fieldset>)}
      <label className="flex items-start gap-3"><input type="checkbox" name="verified" required />I confirm that every fact above is accurate and verified by me.</label>
      <button type="submit">Save verified profile</button>
    </form>
  </div>;
}
