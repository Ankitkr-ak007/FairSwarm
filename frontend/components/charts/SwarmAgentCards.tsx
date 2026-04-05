"use client";

import type { SwarmAgentResult } from "@/types";

import { Card } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress";

type SwarmAgentCardsProps = {
  agents: SwarmAgentResult[];
};

function agreementBorder(confidence: number): string {
  if (confidence >= 0.8) return "border-accent";
  if (confidence >= 0.55) return "border-warning";
  return "border-danger";
}

export function SwarmAgentCards({ agents }: SwarmAgentCardsProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {agents.map((agent) => (
        <Card key={agent.agent_name} className={`space-y-3 border ${agreementBorder(agent.confidence_score)}`}>
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-slate-400">{agent.specialty}</p>
            <h3 className="mt-1 text-lg font-semibold text-white">{agent.agent_name}</h3>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
              <span>Confidence</span>
              <span>{Math.round(agent.confidence_score * 100)}%</span>
            </div>
            <ProgressBar value={agent.confidence_score * 100} className="h-2" />
          </div>

          <p className="text-sm text-slate-200">{agent.top_finding}</p>
          <p className="text-xs text-slate-400">{agent.recommended_action}</p>
        </Card>
      ))}
    </div>
  );
}
