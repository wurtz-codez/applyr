import {
  IBM_Plex_Mono,
  Instrument_Serif,
  Schibsted_Grotesk,
} from "next/font/google";

export const display = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-lp-display",
});

export const sans = Schibsted_Grotesk({
  subsets: ["latin"],
  weight: "variable",
  display: "swap",
  variable: "--font-lp-sans",
});

export const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-lp-mono",
});

export const fontVariables = `${display.variable} ${sans.variable} ${mono.variable}`;
