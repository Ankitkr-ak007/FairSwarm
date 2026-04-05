from __future__ import annotations

import pytest

from app.models.schemas import BiasIndicator, SwarmAgentResult
from app.services.ai_swarm_engine import AISwarmEngine


def _agent_result(agent_name: str, confidence: float, severity: str = "high") -> SwarmAgentResult:
    return SwarmAgentResult(
        agent_name=agent_name,
        specialty="fairness",
        confidence_score=confidence,
        bias_indicators=[
            BiasIndicator(
                attribute="gender",
                metric_name="Disparate Impact Ratio",
                value=0.45,
                severity=severity,
                plain_explanation="Large disparity between groups.",
            )
        ],
        top_finding="Bias detected",
        recommended_action="Apply reweighing",
        analysis_reasoning="Synthetic result for testing",
    )


@pytest.mark.asyncio
async def test_swarm_parallel_execution_with_partial_failures(monkeypatch: pytest.MonkeyPatch):
    engine = AISwarmEngine()

    async def fake_run_agent(*, agent_name, agent_config, context, user_id, analysis_id):
        if agent_name in {"nvidia_llama", "google_gemini"}:
            return _agent_result(agent_name, confidence=0.8)
        return None

    monkeypatch.setattr(engine, "_run_agent", fake_run_agent)

    consensus = await engine.run_swarm_analysis(
        analysis_id="a1",
        dataset_summary={"rows": 100},
        fairness_metrics={"gender": {"fairness_score": 42}},
        sensitive_attributes=["gender"],
        target_column="approved",
        sample_data={"rows": []},
    )

    assert consensus.agents_completed == 2
    assert consensus.agents_failed == 2
    assert consensus.overall_swarm_score >= 0


@pytest.mark.asyncio
async def test_swarm_raises_when_all_agents_fail(monkeypatch: pytest.MonkeyPatch):
    engine = AISwarmEngine()

    async def fake_run_agent(*, agent_name, agent_config, context, user_id, analysis_id):
        return None

    monkeypatch.setattr(engine, "_run_agent", fake_run_agent)

    with pytest.raises(RuntimeError):
        await engine.run_swarm_analysis(
            analysis_id="a2",
            dataset_summary={},
            fairness_metrics={},
            sensitive_attributes=["gender"],
            target_column="approved",
            sample_data={},
        )


def test_weighted_consensus_calculation():
    engine = AISwarmEngine()
    result = engine._weighted_consensus(
        [
            _agent_result("nvidia_llama", confidence=0.9, severity="critical"),
            _agent_result("google_gemini", confidence=0.8, severity="high"),
        ]
    )

    assert result.agents_completed == 2
    assert result.fairness_grade in {"A", "B", "C", "D", "F"}
    assert result.agreement_score >= 0
    assert result.top_recommendation
