import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";
import { current_release } from "./data/release";
import "./globals.css";

const title = "The Card — Open E-Paper Badge";
const description =
  "An open ESP32-S3 e-paper badge, documented from schematic to fabrication output.";
const configured_origin = process.env.SITE_ORIGIN ?? "http://localhost:3000";

function siteOrigin() {
  const origin = new URL(configured_origin);
  if (!(["http:", "https:"] as const).includes(origin.protocol as "http:" | "https:")) {
    throw new Error("SITE_ORIGIN must use http or https");
  }
  if (origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash) {
    throw new Error("SITE_ORIGIN must be an origin without credentials, path, query, or hash");
  }
  if (process.env.SITE_ORIGIN && process.env.NODE_ENV === "production" && origin.protocol !== "https:") {
    throw new Error("SITE_ORIGIN must use https in production");
  }
  return new URL(origin.origin);
}

const site_origin = siteOrigin();
const social_image = new URL("/og.png", site_origin).toString();

export const metadata: Metadata = {
  alternates: {
    canonical: "/",
  },
  metadataBase: site_origin,
  title,
  description,
  openGraph: {
    title,
    description,
    type: "website",
    url: site_origin,
    images: [{
      url: social_image,
      width: 1672,
      height: 941,
      alt: `The Card open e-paper badge, Hardware Revision ${current_release.hardware_revision}`,
    }],
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: [social_image],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${GeistSans.variable} ${GeistMono.variable}`}
      >
        {children}
      </body>
    </html>
  );
}
