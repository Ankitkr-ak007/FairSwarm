"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MetricResult } from "@/types";

import { Card } from "@/components/ui/card";

type ChartRow = {
  metric: string;
  value: number;
  threshold: number;
};

export function FairnessMetricsBar({ metrics }: { metrics: MetricResult[] }) {
  const rows: ChartRow[] = metrics.map((metric) => ({
    metric: metric.metric_name,
    value: Number(metric.value.toFixed(4)),
    threshold: Number(metric.threshold_max.toFixed(4)),
  }));

  return (
    <Card className="h-[360px] overflow-hidden">
      <p className="mb-3 text-sm uppercase tracking-[0.18em] text-slate-400">Metric vs Threshold</p>
      <ResponsiveContainer width="100%" height="88%">
        <BarChart data={rows} layout="vertical" margin={{ left: 24, right: 20 }}>
          <CartesianGrid stroke="#1A3050" strokeDasharray="2 2" />
          <XAxis type="number" stroke="#94A3B8" />
          <YAxis type="category" dataKey="metric" width={170} stroke="#94A3B8" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: "#0F1F38",
              border: "1px solid #1A3050",
              borderRadius: 8,
              color: "#e2e8f0",
            }}
          />
          <Bar dataKey="threshold" fill="#00D4FF" radius={[2, 2, 2, 2]} />
          <Bar dataKey="value" fill="#0066FF" radius={[2, 2, 2, 2]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
