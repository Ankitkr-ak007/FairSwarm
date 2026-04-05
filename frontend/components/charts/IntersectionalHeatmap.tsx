"use client";

import * as d3 from "d3";
import { useEffect, useMemo, useRef } from "react";

import { Card } from "@/components/ui/card";

type HeatmapPoint = {
  label: string;
  disparity: number;
  severity: string;
};

type IntersectionalHeatmapProps = {
  data: Array<{
    combination: string[];
    disparity: number;
    severity: string;
  }>;
};

export function IntersectionalHeatmap({ data }: IntersectionalHeatmapProps) {
  const ref = useRef<SVGSVGElement | null>(null);

  const points = useMemo<HeatmapPoint[]>(() => {
    return data.map((item) => ({
      label: item.combination.join(" + "),
      disparity: item.disparity,
      severity: item.severity,
    }));
  }, [data]);

  useEffect(() => {
    if (!ref.current) return;

    const width = 700;
    const rowHeight = 40;
    const height = Math.max(120, points.length * rowHeight + 50);

    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const maxDisparity = d3.max(points, (d) => d.disparity) ?? 0.1;
    const colorScale = d3
      .scaleLinear<string>()
      .domain([0, maxDisparity / 2, maxDisparity])
      .range(["#00FF88", "#FFAA00", "#FF3B3B"]);

    const g = svg.append("g").attr("transform", "translate(16,16)");

    g.selectAll("rect")
      .data(points)
      .enter()
      .append("rect")
      .attr("x", 220)
      .attr("y", (_d, i) => i * rowHeight)
      .attr("width", 420)
      .attr("height", rowHeight - 8)
      .attr("rx", 4)
      .attr("fill", (d) => colorScale(d.disparity));

    g.selectAll("text.label")
      .data(points)
      .enter()
      .append("text")
      .attr("class", "label")
      .attr("x", 0)
      .attr("y", (_d, i) => i * rowHeight + 20)
      .attr("fill", "#E2E8F0")
      .style("font-size", "12px")
      .text((d) => d.label);

    g.selectAll("text.value")
      .data(points)
      .enter()
      .append("text")
      .attr("class", "value")
      .attr("x", 648)
      .attr("y", (_d, i) => i * rowHeight + 20)
      .attr("fill", "#0B1020")
      .style("font-size", "11px")
      .style("font-weight", "700")
      .style("text-anchor", "end")
      .text((d) => d.disparity.toFixed(3));
  }, [points]);

  return (
    <Card className="overflow-x-auto">
      <p className="mb-4 text-sm uppercase tracking-[0.18em] text-slate-400">Intersectional Bias Heatmap</p>
      <svg ref={ref} className="min-w-[680px]" />
    </Card>
  );
}
