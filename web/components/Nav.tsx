"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", ic: "📊", label: "Home" },
  { href: "/backtest", ic: "📈", label: "Backtest" },
  { href: "/journal", ic: "📒", label: "Journal" },
  { href: "/decision", ic: "🧠", label: "Decision" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="nav">
      {ITEMS.map((it) => {
        const active = it.href === "/" ? path === "/" : path.startsWith(it.href);
        return (
          <Link key={it.href} href={it.href} className={active ? "active" : ""}>
            <span className="ic">{it.ic}</span>
            <span>{it.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
