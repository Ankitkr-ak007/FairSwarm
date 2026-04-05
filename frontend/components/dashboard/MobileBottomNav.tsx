"use client";

import { BarChart3, FileText, Home, Upload } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/dashboard", label: "Home", icon: Home },
  { href: "/dashboard#upload", label: "Upload", icon: Upload },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/dashboard#analysis", label: "Analysis", icon: BarChart3 },
];

export function MobileBottomNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-surface/95 px-4 py-2 backdrop-blur lg:hidden">
      <div className="grid grid-cols-4 gap-2">
        {links.map((link) => {
          const Icon = link.icon;
          const active = pathname === link.href || pathname.startsWith(link.href.split("#")[0]);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "flex flex-col items-center justify-center gap-1 rounded px-2 py-1 text-[11px]",
                active ? "text-primary" : "text-slate-400"
              )}
            >
              <Icon className="h-4 w-4" />
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
