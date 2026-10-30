import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

// Replaced by generated contracts as the Phase 1 API expands.
export type Fact = {
  id: string;
  category: "skill" | "project" | "experience" | "education";
  statement: string;
  evidence_source: string;
  is_verified: true;
};
export type Profile = {
  id: string;
  full_name: string;
  facts: Fact[];
  preferences: {
    roles: string[];
    country_codes: "IN"[];
    max_experience_years: number;
    india_eligible_remote: boolean;
    internships: boolean;
  };
  current_version: number;
  updated_at: string;
};

export const apiBase = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function getToken(): Promise<string> {
  const token = (await cookies()).get("jobpilot_session")?.value;
  if (!token) redirect("/login");
  return token;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const token = await getToken();
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (response.status === 401) redirect("/login?error=session");
  return response;
}

export async function getProfile(): Promise<Profile | null> {
  const response = await apiFetch("/api/v1/profile");
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Could not load profile. Check the API and database.");
  return response.json();
}
