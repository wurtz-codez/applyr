import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { Profile } from "@/lib/types";
export type { Fact, Profile } from "@/lib/types";

export const apiBase = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

export async function getToken(): Promise<string> {
  const token = (await cookies()).get("jobpilot_session")?.value;
  if (!token) redirect("/login");
  return token;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const token = await getToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${apiBase}${path}`, {
    ...init, headers, cache: "no-store",
    signal: init.signal ?? AbortSignal.timeout(45000),
  });
  if (response.status === 401) redirect("/login?error=session");
  return response;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error("Could not load this page. Check the API and try again.");
  return response.json();
}

export async function getProfile(): Promise<Profile | null> {
  const response = await apiFetch("/api/v1/profile");
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("Could not load profile. Check the API and database.");
  return response.json();
}
