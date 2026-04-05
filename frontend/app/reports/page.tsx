"use client";

import { Download, Link2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { List, type RowComponentProps } from "react-window";
import { useQuery } from "@tanstack/react-query";

import { MobileBottomNav } from "@/components/dashboard/MobileBottomNav";
import { SidebarNav } from "@/components/dashboard/SidebarNav";
import { useToast } from "@/components/providers/ToastProvider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { normalizeApiError, reportsApi } from "@/lib/api";
import { sanitizeText } from "@/lib/sanitize";
import type { ReportFilters, ReportListItem } from "@/types";

type SortOption = "newest" | "worst_bias_score" | "best_bias_score";

type FilterState = {
  startDate: string;
  endDate: string;
  grade: "" | "A" | "B" | "C" | "D" | "E" | "F";
  datasetId: string;
  sort: SortOption;
};

type VirtualRowProps = {
  items: ReportListItem[];
  selectedIds: Set<string>;
  toggleSelection: (analysisId: string) => void;
  onDownloadPdf: (analysisId: string) => Promise<void>;
  onShare: (analysisId: string) => Promise<void>;
};

function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);

  return debounced;
}

function gradeClass(grade: string): string {
  if (grade === "A") return "border-accent text-accent";
  if (grade === "B") return "border-secondary text-secondary";
  if (grade === "C") return "border-warning text-warning";
  return "border-danger text-danger";
}

function ReportCard({
  item,
  selected,
  onToggle,
  onDownloadPdf,
  onShare,
}: {
  item: ReportListItem;
  selected: boolean;
  onToggle: () => void;
  onDownloadPdf: () => Promise<void>;
  onShare: () => Promise<void>;
}) {
  return (
    <Card className="space-y-3" aria-label={`Report card for ${item.project_name}`}>
      <div className="flex items-start justify-between gap-3">
        <label className="inline-flex items-center gap-2 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="h-4 w-4 rounded border border-border bg-surface"
            aria-label={`Select report for ${item.project_name}`}
          />
          Select
        </label>
        <span className={`rounded border px-2 py-1 text-xs font-semibold ${gradeClass(item.fairness_grade)}`}>
          Grade {item.fairness_grade}
        </span>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-white">{sanitizeText(item.project_name)}</h3>
        <p className="text-sm text-slate-300">Dataset: {sanitizeText(item.dataset_name)}</p>
        <p className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString()}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="ghost" onClick={onDownloadPdf} aria-label={`Download PDF report for ${item.project_name}`}>
          <Download className="mr-1 h-4 w-4" /> PDF
        </Button>
        <Button variant="ghost" onClick={onShare} aria-label={`Generate share link for ${item.project_name}`}>
          <Link2 className="mr-1 h-4 w-4" /> Share
        </Button>
        <Link href={`/analysis/${item.analysis_id}`} className="rounded border border-border px-3 py-2 text-sm text-secondary">
          Open
        </Link>
      </div>
    </Card>
  );
}

function VirtualRow({
  index,
  style,
  items,
  selectedIds,
  toggleSelection,
  onDownloadPdf,
  onShare,
}: RowComponentProps<VirtualRowProps>) {
  const item = items[index];

  return (
    <div style={style} className="px-1 pb-3">
      <ReportCard
        item={item}
        selected={selectedIds.has(item.analysis_id)}
        onToggle={() => toggleSelection(item.analysis_id)}
        onDownloadPdf={() => onDownloadPdf(item.analysis_id)}
        onShare={() => onShare(item.analysis_id)}
      />
    </div>
  );
}

export default function ReportsPage() {
  const { notify } = useToast();

  const [filters, setFilters] = useState<FilterState>({
    startDate: "",
    endDate: "",
    grade: "",
    datasetId: "",
    sort: "newest",
  });
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [liveMessage, setLiveMessage] = useState("Ready");

  const debouncedFilters = useDebouncedValue(filters, 300);

  const queryParams = useMemo<ReportFilters>(
    () => ({
      start_date: debouncedFilters.startDate || undefined,
      end_date: debouncedFilters.endDate || undefined,
      grade: debouncedFilters.grade || undefined,
      dataset_id: debouncedFilters.datasetId || undefined,
      sort: debouncedFilters.sort,
      page: 1,
      page_size: 300,
    }),
    [debouncedFilters]
  );

  const reportsQuery = useQuery({
    queryKey: ["reports-list", queryParams],
    queryFn: () => reportsApi.list(queryParams),
    staleTime: 5 * 60 * 1000,
  });

  const items = reportsQuery.data?.data.items ?? [];
  const total = reportsQuery.data?.data.total ?? 0;

  const datasetOptions = useMemo(
    () => Array.from(new Set(items.map((item) => `${item.dataset_id}::${item.dataset_name}`))),
    [items]
  );

  const toggleSelection = (analysisId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(analysisId)) {
        next.delete(analysisId);
      } else {
        next.add(analysisId);
      }
      return next;
    });
  };

  const downloadBlob = (blob: Blob, fileName: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const onDownloadPdf = async (analysisId: string) => {
    try {
      const blob = await reportsApi.pdf(analysisId);
      downloadBlob(blob.data, `fairswarm-report-${analysisId}.pdf`);
      setLiveMessage("PDF downloaded.");
      notify({ title: "Report downloaded", variant: "success" });
    } catch (error) {
      const message = normalizeApiError(error);
      setLiveMessage(`Download failed: ${message}`);
      notify({ title: "Download failed", description: message, variant: "error" });
    }
  };

  const onBulkDownload = async () => {
    if (!selectedIds.size) return;

    try {
      const blob = await reportsApi.bulkDownload({ analysis_ids: Array.from(selectedIds) });
      downloadBlob(blob.data, "fairswarm-reports.zip");
      setLiveMessage("ZIP download started.");
      notify({ title: "ZIP download started", variant: "success" });
    } catch (error) {
      const message = normalizeApiError(error);
      setLiveMessage(`Bulk download failed: ${message}`);
      notify({ title: "Bulk download failed", description: message, variant: "error" });
    }
  };

  const onShare = async (analysisId: string) => {
    try {
      const response = await reportsApi.share(analysisId);
      const token = response.data.share_url.split("/").at(-1) ?? "";
      const url = token ? `${window.location.origin}/shared-report/${token}` : response.data.share_url;
      await navigator.clipboard.writeText(url);
      setLiveMessage("Share link copied to clipboard.");
      notify({
        title: "Share link copied",
        description: `Public link valid until ${new Date(response.data.expires_at).toLocaleString()}`,
        variant: "success",
      });
    } catch (error) {
      const message = normalizeApiError(error);
      setLiveMessage(`Share failed: ${message}`);
      notify({ title: "Share failed", description: message, variant: "error" });
    }
  };

  const isVirtualized = items.length > 24;

  return (
    <div className="flex min-h-screen bg-background">
      <SidebarNav />
      <div className="w-full pb-20 lg:pb-0">
        <div className="fs-shell space-y-6 py-6">
          <header className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="fs-section-title">Reports Library</p>
              <h1 className="mt-1 text-3xl font-semibold text-white">Bias Report Archive</h1>
              <p className="mt-2 text-sm text-slate-300">{total} reports available</p>
            </div>
            <Button onClick={onBulkDownload} disabled={!selectedIds.size} aria-label="Bulk download selected reports as ZIP">
              <Download className="mr-2 h-4 w-4" /> Download ZIP ({selectedIds.size})
            </Button>
          </header>

          <Card className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <label className="text-sm text-slate-300">
              Start date
              <input
                type="date"
                value={filters.startDate}
                onChange={(event) => setFilters((current) => ({ ...current, startDate: event.target.value }))}
                className="mt-1 h-10 w-full rounded border border-border bg-surface px-3 text-white"
                aria-label="Filter reports from date"
              />
            </label>

            <label className="text-sm text-slate-300">
              End date
              <input
                type="date"
                value={filters.endDate}
                onChange={(event) => setFilters((current) => ({ ...current, endDate: event.target.value }))}
                className="mt-1 h-10 w-full rounded border border-border bg-surface px-3 text-white"
                aria-label="Filter reports to date"
              />
            </label>

            <label className="text-sm text-slate-300">
              Fairness grade
              <select
                value={filters.grade}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    grade: event.target.value as FilterState["grade"],
                  }))
                }
                className="mt-1 h-10 w-full rounded border border-border bg-surface px-3 text-white"
                aria-label="Filter by fairness grade"
              >
                <option value="">All grades</option>
                {(["A", "B", "C", "D", "E", "F"] as const).map((grade) => (
                  <option key={grade} value={grade}>
                    {grade}
                  </option>
                ))}
              </select>
            </label>

            <label className="text-sm text-slate-300">
              Dataset
              <select
                value={filters.datasetId}
                onChange={(event) => setFilters((current) => ({ ...current, datasetId: event.target.value }))}
                className="mt-1 h-10 w-full rounded border border-border bg-surface px-3 text-white"
                aria-label="Filter by dataset"
              >
                <option value="">All datasets</option>
                {datasetOptions.map((entry) => {
                  const [id, name] = entry.split("::");
                  return (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  );
                })}
              </select>
            </label>

            <label className="text-sm text-slate-300">
              Sort by
              <select
                value={filters.sort}
                onChange={(event) => setFilters((current) => ({ ...current, sort: event.target.value as SortOption }))}
                className="mt-1 h-10 w-full rounded border border-border bg-surface px-3 text-white"
                aria-label="Sort reports"
              >
                <option value="newest">Newest</option>
                <option value="worst_bias_score">Worst bias score</option>
                <option value="best_bias_score">Best bias score</option>
              </select>
            </label>
          </Card>

          <p className="sr-only" role="status" aria-live="polite">
            {liveMessage}
          </p>

          {reportsQuery.isLoading ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="fs-skeleton h-44" />
              ))}
            </div>
          ) : reportsQuery.isError ? (
            <Card>
              <p className="text-sm text-danger">{normalizeApiError(reportsQuery.error)}</p>
            </Card>
          ) : items.length === 0 ? (
            <Card>
              <p className="text-sm text-slate-300">No reports match the current filters.</p>
            </Card>
          ) : isVirtualized ? (
            <Card className="p-2">
              <List
                style={{ height: 680 }}
                defaultHeight={680}
                rowCount={items.length}
                rowHeight={180}
                rowComponent={VirtualRow}
                rowProps={{
                  items,
                  selectedIds,
                  toggleSelection,
                  onDownloadPdf,
                  onShare,
                }}
              />
            </Card>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {items.map((item) => (
                <ReportCard
                  key={item.id}
                  item={item}
                  selected={selectedIds.has(item.analysis_id)}
                  onToggle={() => toggleSelection(item.analysis_id)}
                  onDownloadPdf={() => onDownloadPdf(item.analysis_id)}
                  onShare={() => onShare(item.analysis_id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <MobileBottomNav />
    </div>
  );
}
