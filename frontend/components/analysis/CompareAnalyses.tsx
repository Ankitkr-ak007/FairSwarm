"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";

import { analysisApi, getAnalysis, normalizeApiError } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import type { AnalysisDetailResponse, MetricResult } from "@/types";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type CompareAnalysesProps = {
  defaultLeftId?: string;
};

type MetricDeltaRow = {
  metric: string;
  left: number;
  right: number;
  delta: number;
};

function fairnessScore(detail?: AnalysisDetailResponse): number {
  return Number(detail?.bias_report?.overall_score ?? 0);
}

function agreementScore(detail?: AnalysisDetailResponse): number {
  return Number(detail?.bias_report?.swarm_consensus?.agreement_score ?? 0) * 100;
}

function metricRows(detail?: AnalysisDetailResponse): MetricResult[] {
  const byAttr = detail?.bias_report?.fairness_metrics?.metrics_by_sensitive_attribute;
  if (!byAttr) return [];
  return Object.values(byAttr).flatMap((group) => group.metrics || []);
}

export function CompareAnalyses({ defaultLeftId }: CompareAnalysesProps) {
  const analysesQuery = useQuery({
    queryKey: ["analysis-list-for-compare"],
    queryFn: () => analysisApi.list(),
  });

  const analyses = analysesQuery.data?.data.items ?? [];

  const [leftId, setLeftId] = useState(defaultLeftId ?? "");
  const [rightId, setRightId] = useState("");

  const leftQuery = useQuery({
    queryKey: ["compare-left", leftId],
    queryFn: () => getAnalysis(leftId),
    enabled: Boolean(leftId),
  });

  const rightQuery = useQuery({
    queryKey: ["compare-right", rightId],
    queryFn: () => getAnalysis(rightId),
    enabled: Boolean(rightId),
  });

  const left = leftQuery.data;
  const right = rightQuery.data;

  const deltaRows = useMemo<MetricDeltaRow[]>(() => {
    if (!left || !right) return [];

    const leftMap = new Map(metricRows(left).map((metric) => [metric.metric_name, metric.value]));
    const rightMap = new Map(metricRows(right).map((metric) => [metric.metric_name, metric.value]));

    const names = Array.from(new Set([...Array.from(leftMap.keys()), ...Array.from(rightMap.keys())]));
    return names.map((metric) => {
      const l = Number(leftMap.get(metric) ?? 0);
      const r = Number(rightMap.get(metric) ?? 0);
      return {
        metric,
        left: l,
        right: r,
        delta: r - l,
      };
    });
  }, [left, right]);

  const recommendationDiff = useMemo(() => {
    if (!left || !right) return { added: [] as string[], removed: [] as string[] };

    const leftSet = new Set((left.bias_report?.model_recommendations ?? []).map((item) => item.strategy));
    const rightSet = new Set((right.bias_report?.model_recommendations ?? []).map((item) => item.strategy));

    return {
      added: Array.from(rightSet).filter((item) => !leftSet.has(item)),
      removed: Array.from(leftSet).filter((item) => !rightSet.has(item)),
    };
  }, [left, right]);

  const exportPdf = () => {
    if (!left || !right) return;

    const doc = new jsPDF();
    doc.setFontSize(16);
    doc.text("FairSwarm Analysis Comparison", 14, 16);
    doc.setFontSize(10);
    doc.text(`Left: ${left.analysis.id}`, 14, 24);
    doc.text(`Right: ${right.analysis.id}`, 14, 30);
    doc.text(`Fairness Score Delta: ${(fairnessScore(right) - fairnessScore(left)).toFixed(2)}`, 14, 36);

    autoTable(doc, {
      startY: 44,
      head: [["Metric", "Left", "Right", "Delta"]],
      body: deltaRows.map((row) => [
        row.metric,
        row.left.toFixed(4),
        row.right.toFixed(4),
        row.delta.toFixed(4),
      ]),
      styles: {
        fontSize: 8,
      },
    });

    doc.save(`fairswarm-compare-${left.analysis.id}-${right.analysis.id}.pdf`);
  };

  return (
    <Card className="space-y-4 p-5" aria-label="Compare two analyses">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="fs-section-title">Compare Analyses</p>
          <h3 className="mt-1 text-xl font-semibold text-white">Did your latest model reduce bias?</h3>
        </div>
        <Button onClick={exportPdf} disabled={!left || !right} aria-label="Export analysis comparison as PDF">
          Export Comparison PDF
        </Button>
      </div>

      {analysesQuery.isError ? (
        <p className="text-sm text-danger">{normalizeApiError(analysesQuery.error)}</p>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm text-slate-300">
          Baseline analysis
          <select
            value={leftId}
            onChange={(event) => setLeftId(event.target.value)}
            className="mt-1 h-10 w-full rounded border border-border bg-surface px-3 text-white"
            aria-label="Select baseline analysis"
          >
            <option value="">Select analysis</option>
            {analyses.map((analysis) => (
              <option key={analysis.id} value={analysis.id}>
                {analysis.id.slice(0, 8)} - {new Date(analysis.created_at).toLocaleDateString()}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm text-slate-300">
          Improved analysis
          <select
            value={rightId}
            onChange={(event) => setRightId(event.target.value)}
            className="mt-1 h-10 w-full rounded border border-border bg-surface px-3 text-white"
            aria-label="Select improved analysis"
          >
            <option value="">Select analysis</option>
            {analyses.map((analysis) => (
              <option key={analysis.id} value={analysis.id}>
                {analysis.id.slice(0, 8)} - {new Date(analysis.created_at).toLocaleDateString()}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!left || !right ? (
        <p className="text-sm text-slate-400">Select two analyses to compare fairness progression.</p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border border-border bg-surface p-3" aria-label="Baseline fairness score">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Baseline Fairness Score</p>
              <p className="mt-1 text-2xl font-semibold text-white">{fairnessScore(left).toFixed(2)}</p>
              <p className="text-xs text-slate-400">Swarm agreement: {agreementScore(left).toFixed(0)}%</p>
            </div>
            <div className="rounded border border-border bg-surface p-3" aria-label="Improved fairness score">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Improved Fairness Score</p>
              <p className="mt-1 text-2xl font-semibold text-white">{fairnessScore(right).toFixed(2)}</p>
              <p className="text-xs text-slate-400">Swarm agreement: {agreementScore(right).toFixed(0)}%</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm text-slate-300" aria-label="Metric by metric comparison table">
              <thead className="text-xs uppercase tracking-[0.14em] text-slate-400">
                <tr>
                  <th className="pb-2">Metric</th>
                  <th className="pb-2">Baseline</th>
                  <th className="pb-2">Improved</th>
                  <th className="pb-2">Delta</th>
                </tr>
              </thead>
              <tbody>
                {deltaRows.map((row) => {
                  const improved = row.delta >= 0;
                  return (
                    <tr key={row.metric} className="border-t border-border/70">
                      <td className="py-2 text-slate-200">{sanitizeText(row.metric)}</td>
                      <td className="py-2">{row.left.toFixed(4)}</td>
                      <td className="py-2">{row.right.toFixed(4)}</td>
                      <td className={improved ? "py-2 text-accent" : "py-2 text-danger"}>
                        {improved ? "+" : ""}
                        {row.delta.toFixed(4)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border border-border bg-surface p-3">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Recommendations Added</p>
              <ul className="mt-2 space-y-1 text-sm text-slate-200">
                {recommendationDiff.added.length ? (
                  recommendationDiff.added.map((item) => <li key={item}>+ {sanitizeText(item)}</li>)
                ) : (
                  <li className="text-slate-400">No new recommendations.</li>
                )}
              </ul>
            </div>
            <div className="rounded border border-border bg-surface p-3">
              <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Recommendations Removed</p>
              <ul className="mt-2 space-y-1 text-sm text-slate-200">
                {recommendationDiff.removed.length ? (
                  recommendationDiff.removed.map((item) => <li key={item}>- {sanitizeText(item)}</li>)
                ) : (
                  <li className="text-slate-400">No removed recommendations.</li>
                )}
              </ul>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
