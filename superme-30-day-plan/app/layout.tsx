import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Making SuperMe Better and the Network Stronger: First 30 Days",
  description:
    "A 30 day operator plan for turning great professionals into a stronger product, stronger network, and stronger GTM loop.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
