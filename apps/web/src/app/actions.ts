"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { apiBase, apiFetch, getProfile, type Fact } from "@/lib/api";

export async function login(data: FormData) {
  const token = String(data.get("token") ?? "").trim();
  if (token.length < 32 || token.length > 512) redirect("/login?error=invalid");
  let valid = false;
  try {
    const response = await fetch(`${apiBase}/api/v1/auth/check`, {
      headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    valid = response.ok;
  } catch {
    redirect("/login?error=unavailable");
  }
  if (!valid) redirect("/login?error=invalid");
  (await cookies()).set("jobpilot_session", token, {
    httpOnly: true, sameSite: "strict", secure: process.env.NODE_ENV === "production",
    path: "/", maxAge: 60 * 60 * 8,
  });
  redirect("/dashboard");
}

export async function logout() {
  (await cookies()).delete("jobpilot_session");
  redirect("/login");
}

export async function saveProfile(data: FormData) {
  if (data.get("verified") !== "on") redirect("/profile?error=verification");
  const previous = await getProfile();
  const count = Number(data.get("fact_count"));
  if (!Number.isInteger(count) || count < 0 || count > 200) redirect("/profile?error=invalid");
  const facts: Fact[] = [];
  for (let i = 0; i < count; i++) {
    const statement = String(data.get(`statement_${i}`) ?? "").trim();
    if (!statement) continue;
    facts.push({
      id: String(data.get(`id_${i}`) ?? `fact-${i}`),
      category: String(data.get(`category_${i}`)) as Fact["category"],
      statement,
      evidence_source: String(data.get(`evidence_${i}`) ?? "").trim(),
      is_verified: true,
    });
  }
  const response = await apiFetch("/api/v1/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      full_name: String(data.get("full_name") ?? "").trim(),
      facts,
      ...(previous ? { preferences: previous.preferences } : {}),
    }),
  });
  if (!response.ok) redirect("/profile?error=invalid");
  revalidatePath("/profile");
  revalidatePath("/dashboard");
  redirect("/profile?saved=true");
}
