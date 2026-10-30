export function dateTime(value: string): string {
  // SQLite returns naive UTC timestamps; PostgreSQL includes the offset.
  const utc = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata",
  }).format(new Date(utc));
}

export function label(value: string): string {
  return value.toLowerCase().replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}
