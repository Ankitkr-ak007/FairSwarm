"use client";

import { Download } from "lucide-react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { normalizeApiError, reportsApi } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";

export default function SharedReportPage() {
  const { token } = useParams<{ token: string }>();

  const reportQuery = useQuery({
    queryKey: ["public-report", token],
    queryFn: () => reportsApi.publicJson(token),
  });

  const downloadPdf = async () => {
    const response = await reportsApi.publicPdf(token);
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "fairswarm-shared-report.pdf";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (reportQuery.isLoading) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-4xl items-center px-4">
        <div className="w-full space-y-3">
          <div className="fs-skeleton h-9 w-64" />
          <div className="fs-skeleton h-36 w-full" />
        </div>
      </div>
    );
  }

  if (reportQuery.isError || !reportQuery.data?.data) {
    return (
      <div className="grid min-h-screen place-items-center px-4">
        <Card className="max-w-xl p-6">
          <h1 className="text-2xl font-semibold text-white">Report unavailable</h1>
          <p className="mt-2 text-sm text-danger">{normalizeApiError(reportQuery.error)}</p>
        </Card>
      </div>
    );
  }

  const payload = reportQuery.data.data;

  return (
    <div className="mx-auto min-h-screen w-full max-w-5xl px-4 py-8">
      <Card className="space-y-4 p-6">
        <p className="fs-section-title">Public FairSwarm Report</p>
        <h1 className="text-3xl font-semibold text-white">{sanitizeText(payload.analysis?.id)}</h1>
        <p className="text-sm text-slate-300">Overall score: {Number(payload.overall_score ?? 0).toFixed(2)}</p>
        <p className="text-sm text-slate-300">Fairness grade: {payload.fairness_grade}</p>

        <div className="rounded border border-border bg-surface p-3 text-sm text-slate-300">
          <p className="font-semibold text-white">Top Findings</p>
          <ul className="mt-2 space-y-1">
            {(payload.top_findings ?? []).map((finding: Record<string, unknown>, index: number) => (
              <li key={index}>
                {sanitizeText(finding.sensitive_attribute)} / {sanitizeText(finding.metric_name)} / {sanitizeText(finding.value)}
              </li>
            ))}
          </ul>
        </div>

        <Button onClick={downloadPdf} aria-label="Download shared report PDF">
          <Download className="mr-2 h-4 w-4" /> Download PDF
        </Button>
      </Card>
    </div>
  );
}
