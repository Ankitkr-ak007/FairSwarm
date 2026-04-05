import type { MetricResult } from "@/types";

import { Card } from "@/components/ui/card";

type MetricTableProps = {
  metrics: MetricResult[];
};

export function MetricTable({ metrics }: MetricTableProps) {
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-left text-sm text-slate-300">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
            <th className="py-3">Metric</th>
            <th className="py-3">Value</th>
            <th className="py-3">Threshold</th>
            <th className="py-3">Status</th>
            <th className="py-3">Severity</th>
            <th className="py-3">Explanation</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => (
            <tr key={metric.metric_name} className="border-b border-border/60">
              <td className="py-3 font-medium text-slate-200">{metric.metric_name}</td>
              <td className="py-3">{metric.value.toFixed(4)}</td>
              <td className="py-3">[{metric.threshold_min}, {metric.threshold_max}]</td>
              <td className="py-3">
                <span className={metric.is_fair ? "text-accent" : "text-danger"}>
                  {metric.is_fair ? "Pass" : "Fail"}
                </span>
              </td>
              <td className="py-3 capitalize">{metric.severity}</td>
              <td className="py-3 text-xs text-slate-400">{metric.plain_english_explanation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
