"use client";

import { motion } from "framer-motion";
import { useMemo } from "react";

type BiasGaugeProps = {
  score: number;
  label?: string;
};

function gaugeColor(score: number): string {
  if (score >= 80) return "#00FF88";
  if (score >= 50) return "#FFAA00";
  return "#FF3B3B";
}

export function BiasGauge({ score, label = "FairSwarm Score" }: BiasGaugeProps) {
  const clamped = Math.max(0, Math.min(score, 100));
  const radius = 82;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clamped / 100) * circumference;
  const color = gaugeColor(clamped);

  const grade = useMemo(() => {
    if (clamped >= 80) return "A";
    if (clamped >= 65) return "B";
    if (clamped >= 50) return "C";
    if (clamped >= 35) return "D";
    return "F";
  }, [clamped]);

  return (
    <div className="fs-card flex flex-col items-center gap-4 p-6">
      <p className="fs-section-title">{label}</p>
      <svg width="220" height="220" viewBox="0 0 220 220" role="img" aria-label={`Score ${clamped}`}>
        <circle cx="110" cy="110" r={radius} fill="none" stroke="#1A3050" strokeWidth="14" />
        <motion.circle
          cx="110"
          cy="110"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="14"
          strokeLinecap="round"
          transform="rotate(-90 110 110)"
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.1, ease: "easeOut" }}
          style={{ strokeDasharray: circumference }}
        />
        <text x="110" y="108" textAnchor="middle" className="fill-white text-4xl font-bold">
          {Math.round(clamped)}
        </text>
        <text x="110" y="132" textAnchor="middle" className="fill-slate-400 text-xs tracking-[0.18em]">
          GRADE {grade}
        </text>
      </svg>
    </div>
  );
}
