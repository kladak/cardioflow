import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "CardioFlow",
  description: "Synthetic cardiology documentation workflow",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
