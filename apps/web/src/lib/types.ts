import type { components } from "../../../../packages/contracts/src/api";

type Schemas = components["schemas"];
export type Fact = Schemas["Fact"];
export type Preferences = Required<Schemas["Preferences"]>;
export type Profile = Omit<Schemas["ProfileResponse"], "facts" | "preferences"> & {
  facts: Fact[]; preferences: Preferences;
};
export type Company = Schemas["CompanyResponse"];
export type Job = Schemas["JobSummary"];
export type JobDetail = Schemas["JobDetail"];
export type JobsPage = Schemas["JobsResponse"];
export type Match = Schemas["MatchResult"];
export type Run = Schemas["RunResponse"];
export type Resume = Schemas["ResumeResponse"];
export type Settings = Schemas["SettingsSummary"];
export type Stats = Schemas["DashboardStats"];
export type Application = Schemas["ApplicationResponse"];
export type ApplicationsPage = Schemas["ApplicationsResponse"];
