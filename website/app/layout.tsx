import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";
import {
  normalizeSiteOrigin,
  withPublicBasePath,
} from "../site-config";
import { current_design } from "./data/release";
import "./globals.css";

const title = "The Card — Open E-Paper Badge";
const description =
  "An open ESP32-S3 e-paper badge, documented from schematic to fabrication output.";
const configured_origin = process.env.SITE_ORIGIN ?? "http://localhost:3000";
const site_origin = normalizeSiteOrigin(configured_origin);
if (
  process.env.SITE_ORIGIN &&
  process.env.NODE_ENV === "production" &&
  site_origin.protocol !== "https:"
) {
  throw new Error("SITE_ORIGIN must use https in production");
}
const site_url = new URL(withPublicBasePath("/"), site_origin);
const social_image = new URL(withPublicBasePath("/og.png"), site_origin).toString();

export const metadata: Metadata = {
  alternates: {
    canonical: site_url,
  },
  metadataBase: site_origin,
  title,
  description,
  openGraph: {
    title,
    description,
    type: "website",
    url: site_url,
    images: [{
      url: social_image,
      width: 1672,
      height: 941,
      alt: `The Card open e-paper badge, design v${current_design.design_version}`,
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
