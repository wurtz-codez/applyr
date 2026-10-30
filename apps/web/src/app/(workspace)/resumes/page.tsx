import { apiGet } from "@/lib/api";
import type { Resume } from "@/lib/types";
import { uploadResume, chooseDefaultResume } from "@/app/mvp-actions";
import { SubmitButton } from "@/components/submit-button";
import { Notice } from "@/components/notice";
import { dateTime } from "@/lib/format";

export default async function Resumes({ searchParams }: { searchParams: Promise<{ error?: string; success?: string }> }) {
  const [resumes, messages] = await Promise.all([apiGet<Resume[]>("/api/v1/resumes"), searchParams]);
  return <div className="space-y-6"><div><p className="eyebrow">Application documents</p><h1 className="text-3xl font-semibold">Your resumes</h1><p className="mt-3 max-w-3xl text-slate-600">Upload your existing PDF and choose a default for future applications. Files are stored privately and remain unchanged. Matching uses your verified profile facts.</p></div>
    <Notice {...messages} />
    <section className="panel space-y-5"><h2 className="text-xl font-semibold">Upload a resume</h2><form action={uploadResume} className="flex flex-wrap items-end gap-4"><div className="min-w-0 flex-1"><label htmlFor="resume">PDF document · up to 5 MiB</label><input id="resume" name="resume" type="file" accept="application/pdf,.pdf" required className="mt-2" /></div><SubmitButton pendingText="Uploading…">Upload resume</SubmitButton></form><p className="text-sm text-slate-500">Your first upload becomes the default. Uploading an identical file reuses its existing version. New uploads do not replace the default automatically.</p></section>
    {!resumes.length ? <section className="panel"><p>No resumes uploaded yet.</p></section> : <div className="space-y-4">{resumes.map((resume) => <article key={resume.id} className="panel flex flex-wrap items-start justify-between gap-4"><div className="min-w-0 space-y-2"><h2 className="break-words text-lg font-semibold">{resume.original_filename} {resume.is_default && <span className="ml-2 rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-800">Default</span>}</h2><p className="text-sm text-slate-500">Version {resume.version} · {(resume.size_bytes / 1024).toFixed(1)} KiB · {dateTime(resume.created_at)}</p><p className="max-w-xl break-all text-xs text-slate-400">SHA-256: {resume.sha256}</p></div><div className="flex items-center gap-4"><a href={`/resumes/${resume.id}/download`}>Download</a>{!resume.is_default && <form action={chooseDefaultResume}><input type="hidden" name="resume_id" value={resume.id} /><SubmitButton className="secondary">Set as default</SubmitButton></form>}</div></article>)}</div>}
    <p className="text-sm text-slate-500">Existing application records keep the resume version selected when you recorded them. Changing your default affects future records. No application is submitted by uploading a resume.</p>
  </div>;
}
