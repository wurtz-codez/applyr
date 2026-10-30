import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Applyr — Less noise. More signal.",
  description:
    "A quiet, self-hosted workspace for multi-source job aggregation, eligibility filters and application tracking.",
  openGraph: {
    title: "Applyr — Less noise. More signal.",
    description:
      "Multi-source job aggregation, eligibility filters and application tracking. Self-hosted and human-controlled.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#ece7dc",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
