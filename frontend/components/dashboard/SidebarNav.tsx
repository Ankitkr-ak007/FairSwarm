"use client";

import { BarChart3, FileText, Home, Upload } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { FairSwarmLogo } from "@/components/ui/FairSwarmLogo";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/dashboard#upload", label: "Upload", icon: Upload },
  { href: "/dashboard#analysis", label: "Analysis", icon: BarChart3 },
];

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <aside className="hidden h-screen w-64 shrink-0 border-r border-border bg-surface p-5 lg:block">
      <FairSwarmLogo />
      <nav className="mt-8 space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(item.href.split("#")[0]);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active ? "border border-primary bg-card text-white" : "text-slate-300 hover:bg-card"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
