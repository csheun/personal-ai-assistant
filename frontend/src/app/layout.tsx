import type { Metadata, Viewport } from "next";
import { Hanken_Grotesk } from "next/font/google";
import "./globals.css";

const hanken = Hanken_Grotesk({ variable: "--font-hanken", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Personal Assistant",
  description: "Plan and run everyday tasks with an AI assistant.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#edf0f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1218" },
  ],
};

// Runs before first paint so the saved/system theme never flashes.
const themeScript = `(() => {
  try {
    const saved = localStorage.getItem("theme");
    const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch {}
})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${hanken.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="h-full font-sans text-[15px] leading-normal">{children}</body>
    </html>
  );
}
