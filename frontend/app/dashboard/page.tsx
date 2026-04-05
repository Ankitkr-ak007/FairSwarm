"use client";

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { BookOpenText, FileText, FlaskConical, Plus, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { DatasetUpload } from "@/components/dashboard/DatasetUpload";
import { MobileBottomNav } from "@/components/dashboard/MobileBottomNav";
import { SidebarNav } from "@/components/dashboard/SidebarNav";
import { useToast } from "@/components/providers/ToastProvider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { analysisApi, datasetsApi, normalizeApiError, reportsApi, startAnalysis } from "@/lib/api";
import type { FairnessGrade } from "@/types";

function gradeFromScore(score: number): FairnessGrade {
  if (score >= 80) return "A";
  if (score >= 65) return "B";
  if (score >= 50) return "C";
  if (score >= 35) return "D";
  return "F";
}

function AnimatedStat({ value }: { value: number }) {
  const motionValue = useMotionValue(0);
  const springValue = useSpring(motionValue, { duration: 900 });
  const rounded = useTransform(springValue, (current) => Math.round(current));

  useEffect(() => {
    motionValue.set(value);
  }, [value, motionValue]);

  return <motion.span>{rounded}</motion.span>;
}

export default function DashboardPage() {
  const router = useRouter();
  const { notify } = useToast();
  const [isStarting, setIsStarting] = useState(false);

  const analysesQuery = useQuery({ queryKey: ["analysis-list"], queryFn: () => analysisApi.list() });
  const datasetsQuery = useQuery({ queryKey: ["dataset-list"], queryFn: () => datasetsApi.list() });
  const reportsQuery = useQuery({ queryKey: ["report-list"], queryFn: () => reportsApi.list() });

  const analyses = analysesQuery.data?.data.items ?? [];
  const datasets = datasetsQuery.data?.data.items ?? [];
  const reports = reportsQuery.data?.data.items ?? [];

  const reportGradeByAnalysis = useMemo(() => {
    const map = new Map<string, FairnessGrade>();
    reports.forEach((report) => {
      map.set(report.analysis_id, gradeFromScore(report.overall_score ?? 0));
    });
    return map;
  }, [reports]);

  const datasetNameById = useMemo(() => {
    const map = new Map<string, string>();
    datasets.forEach((dataset) => map.set(dataset.id, dataset.name));
    return map;
  }, [datasets]);

  const stats = useMemo(() => {
    const fairnessScores = reports.map((report) => report.overall_score ?? 0);
    const avgScore = fairnessScores.length
      ? fairnessScores.reduce((sum, score) => sum + score, 0) / fairnessScores.length
      : 0;
    const biasedCount = fairnessScores.filter((score) => score < 50).length;

    return {
      totalAnalyses: analyses.length,
      datasetsUploaded: datasets.length,
      avgFairnessScore: avgScore,
      biasedModelsFound: biasedCount,
    };
  }, [analyses, datasets, reports]);

  const recentAnalyses = analyses.slice(0, 8);

  const handleAnalysisStart = async (payload: {
    datasetId: string;
    sensitiveColumns: string[];
    targetColumn?: string | null;
  }) => {
    if (!payload.targetColumn) {
      notify({
        title: "Target column required",
        description: "Auto-detection failed. Please include a target column in your dataset.",
        variant: "error",
      });
      return;
    }

    if (!payload.sensitiveColumns.length) {
      notify({
        title: "Sensitive columns required",
        description: "Select at least one sensitive column before starting analysis.",
        variant: "error",
      });
      return;
    }

    try {
      setIsStarting(true);
      const started = await startAnalysis({
        dataset_id: payload.datasetId,
        sensitive_columns: payload.sensitiveColumns,
        target_column: payload.targetColumn,
        analysis_name: `Analysis ${new Date().toLocaleString()}`,
      });

      notify({ title: "Analysis started", description: "Redirecting to live progress view.", variant: "success" });
      router.push(`/analysis/${started.analysis_id}`);
    } catch (error) {
      notify({ title: "Start failed", description: normalizeApiError(error), variant: "error" });
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-background">
      <SidebarNav />

      <div className="w-full pb-20 lg:pb-0">
        <div className="fs-shell space-y-6 py-6">
          <header className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="fs-section-title">FairSwarm Dashboard</p>
              <h1 className="mt-1 text-3xl font-semibold text-white">Bias Intelligence Command Center</h1>
            </div>

            <Button onClick={() => document.getElementById("upload")?.scrollIntoView({ behavior: "smooth" })}>
              <Plus className="mr-2 h-4 w-4" />
              New Analysis
            </Button>
          </header>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Total Analyses", value: stats.totalAnalyses },
              { label: "Datasets Uploaded", value: stats.datasetsUploaded },
              { label: "Avg Fairness Score", value: Number(stats.avgFairnessScore.toFixed(0)) },
              { label: "Biased Models Found", value: stats.biasedModelsFound },
            ].map((card, index) => (
              <motion.div
                key={card.label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.08 }}
              >
                <Card>
                  <p className="text-xs uppercase tracking-[0.14em] text-slate-400">{card.label}</p>
                  <p className="mt-2 text-3xl font-bold text-white">
                    <AnimatedStat value={card.value} />
                  </p>
                </Card>
              </motion.div>
            ))}
          </section>

          <section id="analysis" className="grid gap-6 xl:grid-cols-[2fr_1fr]">
            <Card className="overflow-x-auto">
              <div className="mb-4 flex items-center justify-between">
                <p className="fs-section-title">Recent Analyses</p>
                <span className="text-xs text-slate-500">Latest 8 runs</span>
              </div>

              <table className="min-w-full text-left text-sm text-slate-300">
                <thead className="text-xs uppercase tracking-[0.14em] text-slate-400">
                  <tr>
                    <th className="pb-3">Name</th>
                    <th className="pb-3">Dataset</th>
                    <th className="pb-3">Grade</th>
                    <th className="pb-3">Date</th>
                    <th className="pb-3">Status</th>
                    <th className="pb-3">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {recentAnalyses.map((analysis) => {
                    const grade = reportGradeByAnalysis.get(analysis.id) ?? "C";
                    return (
                      <tr key={analysis.id} className="border-t border-border/70">
                        <td className="py-3 font-medium text-white">
                          {String((analysis.swarm_config as { analysis_name?: string })?.analysis_name ?? analysis.id).slice(0, 36)}
                        </td>
                        <td className="py-3 text-slate-300">
                          {datasetNameById.get(analysis.dataset_id) ?? analysis.dataset_id}
                        </td>
                        <td className="py-3">
                          <span className="rounded border border-primary px-2 py-1 text-xs text-primary">{grade}</span>
                        </td>
                        <td className="py-3 text-slate-400">
                          {new Date(analysis.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 capitalize">{analysis.status}</td>
                        <td className="py-3">
                          <Link href={`/analysis/${analysis.id}`} className="text-secondary hover:text-primary">
                            View
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>

            <div className="space-y-4">
              <Card>
                <p className="fs-section-title">Quick Actions</p>
                <div className="mt-4 space-y-2 text-sm">
                  <Link href="#upload" className="flex items-center gap-2 rounded border border-border bg-surface p-2">
                    <UploadCloud className="h-4 w-4" /> Upload Dataset
                  </Link>
                  <Link href="/reports" className="flex items-center gap-2 rounded border border-border bg-surface p-2">
                    <FileText className="h-4 w-4" /> View Reports
                  </Link>
                  <a
                    href="http://localhost:8000/docs"
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-2 rounded border border-border bg-surface p-2"
                  >
                    <BookOpenText className="h-4 w-4" /> Documentation
                  </a>
                </div>
              </Card>

              <Card>
                <p className="fs-section-title">How FairSwarm Works</p>
                <ol className="mt-4 space-y-3 text-sm text-slate-300">
                  <li className="flex gap-2">
                    <span className="text-primary">1.</span>
                    Upload dataset and confirm sensitive attributes.
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary">2.</span>
                    Swarm agents analyze bias from four perspectives.
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary">3.</span>
                    Get consensus score and actionable mitigation report.
                  </li>
                </ol>
              </Card>
            </div>
          </section>

          <section id="upload" className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <p className="fs-section-title">Start New Analysis</p>
              {isStarting ? (
                <span className="inline-flex items-center gap-2 text-sm text-secondary">
                  <FlaskConical className="h-4 w-4 animate-pulse" /> Initializing analysis...
                </span>
              ) : null}
            </div>
            <DatasetUpload onReadyForAnalysis={handleAnalysisStart} />
          </section>
        </div>
      </div>

      <MobileBottomNav />
    </div>
  );
}
