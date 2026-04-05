"use client";

import { useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { FileUp, Loader2, X } from "lucide-react";

import api, { normalizeApiError } from "@/lib/api";
import type { DatasetUploadResponse } from "@/types";

import { useToast } from "@/components/providers/ToastProvider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress";

type DatasetUploadProps = {
  onReadyForAnalysis?: (payload: {
    datasetId: string;
    sensitiveColumns: string[];
    targetColumn?: string | null;
  }) => void;
};

const ACCEPTED_TYPES = {
  "text/csv": [".csv"],
  "application/json": [".json"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};

const MAX_SIZE_BYTES = 50 * 1024 * 1024;

export function DatasetUpload({ onReadyForAnalysis }: DatasetUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploaded, setUploaded] = useState<DatasetUploadResponse | null>(null);
  const [editableSensitiveColumns, setEditableSensitiveColumns] = useState<string[]>([]);
  const [newSensitiveValue, setNewSensitiveValue] = useState("");

  const { notify } = useToast();

  const onDrop = (files: File[]) => {
    const file = files[0];
    if (!file) return;

    setError(null);
    if (file.size > MAX_SIZE_BYTES) {
      setSelectedFile(null);
      setError("File exceeds 50MB limit.");
      return;
    }

    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!extension || !["csv", "xlsx", "json"].includes(extension)) {
      setSelectedFile(null);
      setError("Only CSV, Excel (.xlsx), and JSON files are supported.");
      return;
    }

    setSelectedFile(file);
    setUploaded(null);
    setEditableSensitiveColumns([]);
    setProgress(0);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: ACCEPTED_TYPES,
    maxSize: MAX_SIZE_BYTES,
  });

  const handleUpload = async () => {
    if (!selectedFile) {
      setError("Please select a dataset file.");
      return;
    }

    setError(null);
    setIsUploading(true);
    setProgress(5);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await api.post<DatasetUploadResponse>("/datasets/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (event) => {
          if (!event.total) return;
          const nextProgress = Math.max(5, Math.round((event.loaded / event.total) * 100));
          setProgress(nextProgress);
        },
      });

      setUploaded(response.data);
      setEditableSensitiveColumns(response.data.detected_sensitive_cols);
      setProgress(100);
      notify({ title: "Dataset uploaded", description: "Profiling completed successfully.", variant: "success" });
    } catch (uploadError) {
      setError(normalizeApiError(uploadError));
      notify({ title: "Upload failed", description: normalizeApiError(uploadError), variant: "error" });
    } finally {
      setIsUploading(false);
    }
  };

  const addSensitiveColumn = () => {
    const value = newSensitiveValue.trim();
    if (!value) return;
    if (!editableSensitiveColumns.includes(value)) {
      setEditableSensitiveColumns((current) => [...current, value]);
    }
    setNewSensitiveValue("");
  };

  const removeSensitiveColumn = (column: string) => {
    setEditableSensitiveColumns((current) => current.filter((item) => item !== column));
  };

  const statsRows = useMemo(() => {
    if (!uploaded) return [];
    const profile = uploaded.profile;
    return profile.columns.map((column) => {
      const nullCount = profile.null_counts[column] ?? 0;
      const rowCount = Math.max(profile.row_count, 1);
      const nullPct = ((nullCount / rowCount) * 100).toFixed(1);
      return {
        column,
        dtype: profile.dtypes[column],
        nullPct,
        unique: profile.unique_counts[column] ?? 0,
      };
    });
  }, [uploaded]);

  return (
    <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
      <Card className="space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="fs-section-title">Upload Dataset</p>
            <h3 className="mt-1 text-2xl font-semibold text-white">Bias Analysis Intake</h3>
          </div>
          <FileUp className="h-5 w-5 text-secondary" />
        </div>

        <div
          {...getRootProps()}
          className={
            isDragActive
              ? "cursor-pointer rounded-lg border border-primary bg-surface px-4 py-10 text-center"
              : "cursor-pointer rounded-lg border border-border bg-surface px-4 py-10 text-center"
          }
        >
          <input {...getInputProps()} />
          <p className="text-sm text-slate-300">Drop CSV, XLSX, or JSON here, or click to choose a file</p>
          <p className="mt-2 text-xs text-slate-500">Maximum size: 50MB</p>
        </div>

        {selectedFile ? (
          <div className="rounded-lg border border-border bg-surface/70 p-3 text-sm text-slate-300">
            Selected: {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
          </div>
        ) : null}

        {isUploading ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>Uploading and profiling</span>
              <span>{progress}%</span>
            </div>
            <ProgressBar value={progress} className="h-2" />
          </div>
        ) : null}

        {error ? <p className="text-sm text-danger">{error}</p> : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={handleUpload} disabled={!selectedFile || isUploading}>
            {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Upload & Profile"}
          </Button>
        </div>

        {uploaded ? (
          <div className="space-y-4 rounded-lg border border-border bg-surface/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-semibold text-white">Detected Sensitive Columns</p>
              <div className="flex items-center gap-2">
                <input
                  value={newSensitiveValue}
                  onChange={(event) => setNewSensitiveValue(event.target.value)}
                  placeholder="Add column"
                  className="h-9 rounded border border-border bg-background px-3 text-sm text-white outline-none"
                />
                <Button size="sm" variant="ghost" onClick={addSensitiveColumn}>
                  Add
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {editableSensitiveColumns.map((column) => (
                <span
                  key={column}
                  className="inline-flex items-center gap-2 rounded-full border border-primary px-3 py-1 text-xs text-primary"
                >
                  {column}
                  <button onClick={() => removeSensitiveColumn(column)}>
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>

            <Button
              variant="primary"
              onClick={() => {
                onReadyForAnalysis?.({
                  datasetId: uploaded.dataset_id,
                  sensitiveColumns: editableSensitiveColumns,
                  targetColumn: uploaded.validation.target_column ?? null,
                });
                notify({ title: "Sensitive columns confirmed", variant: "success" });
              }}
            >
              Confirm Sensitive Columns
            </Button>

            <div className="overflow-x-auto rounded border border-border">
              <table className="min-w-full text-left text-xs text-slate-300">
                <thead className="bg-background/60 text-[11px] uppercase tracking-[0.14em] text-slate-400">
                  <tr>
                    {(uploaded.profile.columns || []).map((column) => (
                      <th key={column} className="px-3 py-2">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(uploaded.profile.sample_rows || []).slice(0, 5).map((row, index) => (
                    <tr key={index} className="border-t border-border/60">
                      {uploaded.profile.columns.map((column) => (
                        <td key={column} className="px-3 py-2 text-slate-200">
                          {String(row[column] ?? "-")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </Card>

      <Card className="space-y-3">
        <p className="fs-section-title">Column Statistics</p>
        <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
          {statsRows.length === 0 ? (
            <p className="text-sm text-slate-400">Upload a dataset to see column profile stats.</p>
          ) : (
            statsRows.map((row) => (
              <div key={row.column} className="rounded-md border border-border bg-surface p-3">
                <p className="text-sm font-semibold text-white">{row.column}</p>
                <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-slate-300">
                  <span>Dtype: {row.dtype}</span>
                  <span>Null: {row.nullPct}%</span>
                  <span>Unique: {row.unique}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
