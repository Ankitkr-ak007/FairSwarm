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

import { Card } from "@/components/ui/card";

type DisparateImpactRow = {
  group: string;
  favorable: number;
  unfavorable: number;
};

export function DisparateImpactChart({ data }: { data: DisparateImpactRow[] }) {
  return (
    <Card className="h-[340px]">
      <p className="mb-3 text-sm uppercase tracking-[0.18em] text-slate-400">Outcomes by Group</p>
      <ResponsiveContainer width="100%" height="86%">
        <BarChart data={data}>
          <CartesianGrid stroke="#1A3050" strokeDasharray="3 3" />
          <XAxis dataKey="group" stroke="#94A3B8" tick={{ fontSize: 11 }} />
          <YAxis stroke="#94A3B8" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: "#0F1F38",
              border: "1px solid #1A3050",
              borderRadius: 8,
              color: "#e2e8f0",
            }}
          />
          <Bar dataKey="favorable" name="Favorable" fill="#00FF88" radius={[4, 4, 0, 0]} />
          <Bar dataKey="unfavorable" name="Unfavorable" fill="#FF3B3B" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
