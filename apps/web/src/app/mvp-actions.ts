"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiFetch, getToken } from "@/lib/api";
import type { Run } from "@/lib/types";

function refreshWorkspace() {
  for (const path of ["/dashboard", "/jobs", "/settings", "/runs", "/resumes", "/applications"]) {
    revalidatePath(path);
  }
}

async function requireSuccess(response: Response, back: string) {
  if (response.ok) return;
  let error = "Something went wrong. Please try again.";
  try {
    const payload = await response.json();
    error = typeof payload.detail === "string" ? payload.detail : "Check the supplied fields and try again.";
  } catch { /* Keep a safe generic error for unexpected responses. */ }
  redirect(`${back}?error=${encodeURIComponent(error)}`);
}

function id(data: FormData, key: string): string {
  return encodeURIComponent(String(data.get(key) ?? ""));
}

export async function discoverJobs(data: FormData) {
  const response = await apiFetch("/api/v1/jobs/discover", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ use_ai: data.get("use_ai") === "on" }),
  });
  await requireSuccess(response, "/jobs");
  const run: Run = await response.json();
  refreshWorkspace();
  redirect(`/runs/${run.id}`);
}

export async function addCompany(data: FormData) {
  const response = await apiFetch("/api/v1/companies", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: String(data.get("name") ?? ""), board_token: String(data.get("board_token") ?? "").trim() }),
  });
  await requireSuccess(response, "/settings");
  refreshWorkspace();
  redirect("/settings?success=Company%20board%20added.");
}

export async function toggleCompany(data: FormData) {
  const response = await apiFetch(`/api/v1/companies/${id(data, "company_id")}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: data.get("enabled") === "true" }),
  });
  await requireSuccess(response, "/settings");
  refreshWorkspace();
}

export async function toggleShortlist(data: FormData) {
  const jobId = id(data, "job_id");
  const response = await apiFetch(`/api/v1/jobs/${jobId}/shortlist`, {
    method: data.get("saved") === "true" ? "DELETE" : "POST",
  });
  await requireSuccess(response, `/jobs/${jobId}`);
  refreshWorkspace();
  revalidatePath(`/jobs/${jobId}`);
}

export async function matchJob(data: FormData) {
  const jobId = id(data, "job_id");
  const response = await apiFetch(`/api/v1/jobs/${jobId}/match`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ use_ai: data.get("use_ai") === "true" }),
  });
  await requireSuccess(response, `/jobs/${jobId}`);
  refreshWorkspace();
  revalidatePath(`/jobs/${jobId}`);
  redirect(`/jobs/${jobId}`);
}

export async function uploadResume(data: FormData) {
  await getToken();
  const file = data.get("resume");
  if (!(file instanceof File) || !file.size || file.size > 5 * 1024 * 1024 || !file.name.toLowerCase().endsWith(".pdf")) {
    redirect("/resumes?error=Choose%20a%20PDF%20resume%20up%20to%205%20MiB.");
  }
  const response = await apiFetch(`/api/v1/resumes?filename=${encodeURIComponent(file.name)}`, {
    method: "POST", headers: { "Content-Type": "application/pdf" }, body: await file.arrayBuffer(),
  });
  await requireSuccess(response, "/resumes");
  refreshWorkspace();
  redirect("/resumes?success=Resume%20saved.%20Identical%20files%20reuse%20their%20existing%20version.");
}

export async function chooseDefaultResume(data: FormData) {
  const response = await apiFetch(`/api/v1/resumes/${id(data, "resume_id")}/default`, { method: "POST" });
  await requireSuccess(response, "/resumes");
  refreshWorkspace();
}

export async function trackApplication(data: FormData) {
  const jobId = id(data, "job_id");
  const response = await apiFetch(`/api/v1/jobs/${jobId}/application`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: String(data.get("status") ?? "APPLIED"), notes: String(data.get("notes") ?? "") }),
  });
  await requireSuccess(response, "/applications");
  refreshWorkspace();
  revalidatePath(`/jobs/${jobId}`);
  redirect("/applications?success=Application%20tracking%20updated.%20No%20application%20was%20submitted%20by%20JobPilot.");
}
