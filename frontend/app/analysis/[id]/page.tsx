"use client";

import { CheckCircle2, Clock3, Download, Sparkles } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";

import { MobileBottomNav } from "@/components/dashboard/MobileBottomNav";
import { SidebarNav } from "@/components/dashboard/SidebarNav";
import { useToast } from "@/components/providers/ToastProvider";
import { CompareAnalyses } from "@/components/analysis/CompareAnalyses";
import { MetricTable } from "@/components/analysis/metric-table";
import { SwarmAgentCards } from "@/components/charts/SwarmAgentCards";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress";
import { downloadReport, getAnalysis, normalizeApiError, swarmApi } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import type { AnalysisDetailResponse, FairnessGrade, MetricResult, SwarmAgentResult } from "@/types";

const BiasGauge = dynamic(() => import("@/components/charts/BiasGauge").then((mod) => mod.BiasGauge), {
  ssr: false,
  loading: () => <div className="fs-skeleton h-[320px] w-full" aria-hidden />,
});

const FairnessMetricsBar = dynamic(
  () => import("@/components/charts/FairnessMetricsBar").then((mod) => mod.FairnessMetricsBar),
  {
    ssr: false,
    loading: () => <div className="fs-skeleton h-[360px] w-full" aria-hidden />,
  }
);

const IntersectionalHeatmap = dynamic(
  () => import("@/components/charts/IntersectionalHeatmap").then((mod) => mod.IntersectionalHeatmap),
  {
    ssr: false,
    loading: () => <div className="fs-skeleton h-[300px] w-full" aria-hidden />,
  }
);

const DisparateImpactChart = dynamic(
  () => import("@/components/charts/DisparateImpactChart").then((mod) => mod.DisparateImpactChart),
  {
    ssr: false,
    loading: () => <div className="fs-skeleton h-[340px] w-full" aria-hidden />,
  }
);

type ProgressState = {
  status: string;
  progress: number;
  detail: string;
};

function stepLabel(progress: number): string {
  if (progress < 25) return "Preparing Analysis (Step 1/4)";
  if (progress < 50) return "Running Bias Metrics (Step 2/4)";
  if (progress < 75) return "Intersectional Analysis (Step 3/4)";
  if (progress < 100) return "Building Swarm Consensus (Step 4/4)";
  return "Completed";
}

function gradeFromScore(score: number): FairnessGrade {
  if (score >= 80) return "A";
  if (score >= 65) return "B";
  if (score >= 50) return "C";
  if (score >= 35) return "D";
  return "F";
}

function difficultyFromSeverity(severity: string): "easy" | "moderate" | "complex" {
  if (severity === "low") return "easy";
  if (severity === "medium") return "moderate";
  return "complex";
}

export default function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const analysisId = id;
  const { notify } = useToast();

  const [liveProgress, setLiveProgress] = useState<ProgressState>({
    status: "pending",
    progress: 0,
    detail: "Waiting for analysis updates",
  });
  const [estimatedMinutes, setEstimatedMinutes] = useState<number>(6);
  const [timedOut, setTimedOut] = useState(false);

  const startedAtRef = useRef<number>(Date.now());

  const analysisQuery = useQuery({
    queryKey: ["analysis-detail", analysisId],
    queryFn: () => getAnalysis(analysisId),
    refetchInterval: (query) => {
      const data = query.state.data as AnalysisDetailResponse | undefined;
      const status = data?.analysis?.status;
      return status === "completed" || status === "failed" ? false : 4000;
    },
  });

  const swarmStatusQuery = useQuery({
    queryKey: ["swarm-status", analysisId],
    queryFn: () => swarmApi.status(analysisId),
    refetchInterval: 5000,
  });

  useEffect(() => {
    const wsBase = process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://localhost:8000";
    const socket = new WebSocket(`${wsBase}/ws/analysis/${analysisId}`);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { status?: string; progress?: number; detail?: string };
        const progressValue = payload.progress ?? 0;
        setLiveProgress({
          status: payload.status ?? "running",
          progress: progressValue,
          detail: payload.detail ?? stepLabel(progressValue),
        });

        const elapsedMs = Date.now() - startedAtRef.current;
        const progressRatio = Math.max(progressValue / 100, 0.05);
        const projectedTotalMs = elapsedMs / progressRatio;
        const remainingMs = Math.max(projectedTotalMs - elapsedMs, 0);
        setEstimatedMinutes(Math.max(1, Math.round(remainingMs / 60000)));
      } catch {
        // Ignore malformed websocket payloads.
      }
    };

    return () => {
      socket.close();
    };
  }, [analysisId]);

  const detail = analysisQuery.data;
  const analysisStatus = detail?.analysis?.status ?? "pending";
  const isCompleted = analysisStatus === "completed";
  const report = detail?.bias_report;
  const swarmConsensus = report?.swarm_consensus;
  const swarmAgents = (swarmConsensus?.agent_results as SwarmAgentResult[] | undefined) ?? [];
  const allAgentsFailed = Boolean(
    swarmConsensus && swarmConsensus.agents_failed >= 4 && swarmConsensus.agents_completed === 0
  );

  useEffect(() => {
    if (analysisStatus === "completed" || analysisStatus === "failed") {
      setTimedOut(false);
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setTimedOut(true);
    }, 5 * 60 * 1000);

    return () => window.clearTimeout(timeoutId);
  }, [analysisStatus]);

  const flatMetrics = useMemo<MetricResult[]>(() => {
    if (!report?.fairness_metrics?.metrics_by_sensitive_attribute) return [];
    return Object.values(report.fairness_metrics.metrics_by_sensitive_attribute).flatMap((group) => group.metrics);
  }, [report]);

  const heatmapData = report?.fairness_metrics?.intersectional_bias?.top_disparities ?? [];

  const disparateData = useMemo(() => {
    const top = heatmapData[0];
    if (!top || !Array.isArray(top.groups)) return [];
    return top.groups.slice(0, 8).map((group, idx) => {
      const positiveRate = Number(group.positive_rate ?? 0);
      const count = Number(group.count ?? 100);
      return {
        group: String(group.group ?? group.segment ?? `Group ${idx + 1}`),
        favorable: Math.round(positiveRate * count),
        unfavorable: Math.round((1 - positiveRate) * count),
      };
    });
  }, [heatmapData]);

  const progressValue = Math.max(
    liveProgress.progress,
    detail?.analysis?.progress ?? 0,
    swarmStatusQuery.data?.data.analysis_progress ?? 0
  );

  const downloadPdf = async () => {
    try {
      const blob = await downloadReport(analysisId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `fairswarm-report-${analysisId}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
      notify({ title: "Report downloaded", variant: "success" });
    } catch (error) {
      notify({ title: "Download failed", description: normalizeApiError(error), variant: "error" });
    }
  };

  if (analysisQuery.isLoading) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-5xl items-center px-4">
        <div className="w-full space-y-3">
          <div className="fs-skeleton h-8 w-60" />
          <div className="fs-skeleton h-36 w-full" />
          <div className="fs-skeleton h-72 w-full" />
        </div>
      </div>
    );
  }

  if (analysisQuery.isError || !detail) {
    return (
      <div className="grid min-h-screen place-items-center bg-background px-4">
        <Card className="max-w-lg p-6">
          <p className="text-lg font-semibold text-white">Unable to load analysis</p>
          <p className="mt-2 text-sm text-danger">{normalizeApiError(analysisQuery.error)}</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-background">
      <SidebarNav />

      <div className="w-full pb-20 lg:pb-0">
        <div className="fs-shell space-y-6 py-6">
          <header className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="fs-section-title">Analysis {analysisId.slice(0, 8)}</p>
              <h1 className="mt-1 text-3xl font-semibold text-white">Swarm Bias Intelligence</h1>
            </div>
            <Button onClick={downloadPdf} disabled={!isCompleted}>
              <Download className="mr-2 h-4 w-4" /> Download PDF Report
            </Button>
          </header>

          {!isCompleted ? (
            <section className="space-y-5">
              <Card className="space-y-4 p-5">
                <div className="flex items-center justify-between">
                  <p className="fs-section-title">Progress</p>
                  <span className="text-sm text-slate-400">{Math.round(progressValue)}%</span>
                </div>
                <ProgressBar value={progressValue} className="h-3" label="Analysis progress" />
                <p className="text-sm text-slate-200">{sanitizeText(liveProgress.detail || stepLabel(progressValue))}</p>
                <p className="sr-only" role="status" aria-live="polite">
                  Analysis progress {Math.round(progressValue)} percent. {liveProgress.detail}
                </p>
                <p className="text-xs text-slate-400">
                  <Clock3 className="mr-1 inline h-3 w-3" /> Estimated time remaining: ~{estimatedMinutes} min
                </p>
                {timedOut ? (
                  <div className="rounded border border-warning bg-surface p-3 text-sm text-warning">
                    Analysis is taking longer than 5 minutes. You can retry status checks.
                    <div className="mt-2">
                      <Button
                        variant="ghost"
                        onClick={() => {
                          void analysisQuery.refetch();
                          void swarmStatusQuery.refetch();
                        }}
                        aria-label="Retry analysis status check"
                      >
                        Retry status
                      </Button>
                    </div>
                  </div>
                ) : null}
              </Card>

              <Card>
                <p className="fs-section-title mb-4">Swarm Agent Status</p>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    "nvidia_llama",
                    "google_gemini",
                    "groq_llama",
                    "hf_mixtral",
                  ].map((agentName, index) => {
                    const status =
                      swarmAgents.find((agent) => agent.agent_name === agentName)
                        ? "complete"
                        : progressValue > (index + 1) * 22
                          ? "running"
                          : "pending";

                    return (
                      <div key={agentName} className="rounded-lg border border-border bg-surface p-3">
                        <p className="text-sm font-semibold text-white">{agentName}</p>
                        <p
                          className={
                            status === "complete"
                              ? "mt-1 text-xs text-accent"
                              : status === "running"
                                ? "mt-1 text-xs text-warning"
                                : "mt-1 text-xs text-slate-400"
                          }
                        >
                          {status === "complete" ? "Complete" : status === "running" ? "Running" : "Pending"}
                        </p>
                        {status === "complete" ? <CheckCircle2 className="mt-2 h-4 w-4 text-accent" /> : null}
                      </div>
                    );
                  })}
                </div>
              </Card>
            </section>
          ) : (
            <section className="space-y-6">
              {allAgentsFailed ? (
                <Card className="border-warning p-4 text-sm text-warning" role="status" aria-live="polite">
                  AI analysis unavailable: all swarm agents failed in this run. Showing metric-based results only.
                </Card>
              ) : null}

              <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
                <BiasGauge score={report?.overall_score ?? 0} />

                <Card className="space-y-4 p-5">
                  <p className="fs-section-title">Executive Summary</p>
                  <span className="inline-flex w-fit rounded border border-primary px-3 py-1 text-lg font-semibold text-primary">
                    Grade {swarmConsensus?.fairness_grade ?? gradeFromScore(report?.overall_score ?? 0)}
                  </span>
                  <p className="text-sm text-slate-200">
                    {sanitizeText(
                      swarmConsensus?.executive_summary ??
                      "FairSwarm completed analysis and assembled consensus findings from the AI swarm."
                    )}
                  </p>
                  <p className="text-xs text-slate-400">
                    Agreement Score: {Math.round((swarmConsensus?.agreement_score ?? 0) * 100)}%
                  </p>
                </Card>
              </div>

              <Card className="space-y-4 p-5">
                <p className="fs-section-title">Swarm Consensus</p>
                {swarmAgents.length ? (
                  <SwarmAgentCards agents={swarmAgents} />
                ) : (
                  <p className="text-sm text-slate-400">Swarm agents have not returned consensus cards yet.</p>
                )}
              </Card>

              <FairnessMetricsBar metrics={flatMetrics} />
              <MetricTable metrics={flatMetrics} />
              <IntersectionalHeatmap data={heatmapData.map((item) => ({
                combination: item.combination,
                disparity: item.disparity,
                severity: item.severity,
              }))} />

              <DisparateImpactChart data={disparateData} />

              <Card className="space-y-3 p-5">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-secondary" />
                  <p className="fs-section-title">Mitigation Recommendations</p>
                </div>

                <div className="space-y-3">
                  {(report?.model_recommendations ?? []).map((recommendation) => {
                    const difficulty = difficultyFromSeverity(recommendation.severity);
                    return (
                      <div key={`${recommendation.metric}-${recommendation.strategy}`} className="rounded border border-border bg-surface p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-white">{sanitizeText(recommendation.strategy)}</p>
                          <span
                            className={
                              difficulty === "easy"
                                ? "rounded border border-accent px-2 py-1 text-[11px] uppercase text-accent"
                                : difficulty === "moderate"
                                  ? "rounded border border-warning px-2 py-1 text-[11px] uppercase text-warning"
                                  : "rounded border border-danger px-2 py-1 text-[11px] uppercase text-danger"
                            }
                          >
                            {difficulty}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-slate-300">{sanitizeText(recommendation.description)}</p>
                      </div>
                    );
                  })}
                </div>
              </Card>

              <CompareAnalyses defaultLeftId={analysisId} />
            </section>
          )}
        </div>
      </div>

      <MobileBottomNav />
    </div>
  );
}
