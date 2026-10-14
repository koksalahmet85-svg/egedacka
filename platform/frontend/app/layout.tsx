import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ege Alfa — Kulüp Yönetimi",
  description: "Ege Alfa Spor Kulübü yönetim paneli",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="min-h-dvh font-sans antialiased">{children}</body>
    </html>
  );
}
