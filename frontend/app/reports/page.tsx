"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { MobileBottomNav } from "@/components/dashboard/MobileBottomNav";
import { SidebarNav } from "@/components/dashboard/SidebarNav";
import { Card } from "@/components/ui/card";
import { reportsApi } from "@/lib/api";

function gradeFromScore(score: number): string {
  if (score >= 80) return "A";
  if (score >= 65) return "B";
  if (score >= 50) return "C";
  if (score >= 35) return "D";
  return "F";
}

export default function ReportsPage() {
  const query = useQuery({
    queryKey: ["reports-list"],
    queryFn: () => reportsApi.list(),
  });

  const items = query.data?.data.items ?? [];

  return (
    <div className="flex min-h-screen bg-background">
      <SidebarNav />
      <div className="w-full pb-20 lg:pb-0">
        <div className="fs-shell space-y-6 py-6">
          <header>
            <p className="fs-section-title">Reports</p>
            <h1 className="mt-1 text-3xl font-semibold text-white">Bias Report Archive</h1>
          </header>

          <Card className="overflow-x-auto">
            <table className="min-w-full text-left text-sm text-slate-300">
              <thead className="text-xs uppercase tracking-[0.14em] text-slate-400">
                <tr>
                  <th className="pb-3">Analysis</th>
                  <th className="pb-3">Score</th>
                  <th className="pb-3">Grade</th>
                  <th className="pb-3">Sensitive Attributes</th>
                  <th className="pb-3">Date</th>
                  <th className="pb-3">View</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t border-border/70">
                    <td className="py-3">{item.analysis_id}</td>
                    <td className="py-3">{item.overall_score?.toFixed(1)}</td>
                    <td className="py-3">
                      <span className="rounded border border-primary px-2 py-1 text-xs text-primary">
                        {gradeFromScore(item.overall_score)}
                      </span>
                    </td>
                    <td className="py-3">{item.sensitive_attribute}</td>
                    <td className="py-3">{new Date(item.created_at).toLocaleDateString()}</td>
                    <td className="py-3">
                      <Link href={`/analysis/${item.analysis_id}`} className="text-secondary hover:text-primary">
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>

      <MobileBottomNav />
    </div>
  );
}
