from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx

from ..config import settings
from ..core.database import get_supabase_client
from ..models.schemas import BiasIndicator, SwarmAgentResult, SwarmConsensusResult

logger = logging.getLogger("fairswarm.ai_swarm")


class AISwarmEngine:
    AGENTS: dict[str, dict[str, Any]] = {
        "nvidia_llama": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "model": "meta/llama-3.3-70b-instruct",
            "weight": 0.30,
            "specialty": "statistical_bias_analysis",
            "api_key_env": "NVIDIA_API_KEY",
        },
        "google_gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "model": "gemini-2.0-flash",
            "weight": 0.30,
            "specialty": "contextual_fairness_analysis",
            "api_key_env": "GOOGLE_AI_KEY",
        },
        "groq_llama": {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "weight": 0.25,
            "specialty": "historical_discrimination_patterns",
            "api_key_env": "GROQ_API_KEY",
        },
        "hf_mixtral": {
            "base_url": "https://api-inference.huggingface.co/models",
            "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "weight": 0.15,
            "specialty": "intersectional_bias_detection",
            "api_key_env": "HF_TOKEN",
        },
    }

    _SEVERITY_SCORE = {"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}

    async def run_swarm_analysis(
        self,
        analysis_id: str,
        dataset_summary: dict[str, Any],
        fairness_metrics: dict[str, Any],
        sensitive_attributes: list[str],
        target_column: str,
        sample_data: dict[str, Any],
        user_id: str | None = None,
    ) -> SwarmConsensusResult:
        context = {
            "analysis_id": analysis_id,
            "dataset_summary": dataset_summary,
            "fairness_metrics": fairness_metrics,
            "sensitive_attributes": sensitive_attributes,
            "target_column": target_column,
            "sample_data": sample_data,
        }

        tasks = [
            self._run_agent(
                agent_name=agent_name,
                agent_config=agent_config,
                context=context,
                user_id=user_id,
                analysis_id=analysis_id,
            )
            for agent_name, agent_config in self.AGENTS.items()
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        agent_results: list[SwarmAgentResult] = []
        for item in raw_results:
            if isinstance(item, SwarmAgentResult):
                agent_results.append(item)
            elif isinstance(item, Exception):
                logger.warning("Swarm agent task failed: %s", item)

        if not agent_results:
            raise RuntimeError("All AI swarm agents failed. Please try again in a few moments.")

        consensus = self._weighted_consensus(agent_results)
        if len(agent_results) == 1:
            consensus.warnings.append("LOW_CONFIDENCE: only one swarm agent succeeded.")
        return consensus

    async def run(
        self,
        analysis_id: str,
        fairness_results: dict[str, Any],
        intersectional_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Backward-compatible wrapper used by the analysis pipeline."""
        try:
            consensus = await self.run_swarm_analysis(
                analysis_id=analysis_id,
                dataset_summary={"source": "analysis_pipeline"},
                fairness_metrics=fairness_results,
                sensitive_attributes=list(fairness_results.keys()),
                target_column="target",
                sample_data={"intersectional": intersectional_results},
                user_id=None,
            )
            return consensus.model_dump()
        except Exception as exc:
            logger.warning("Swarm wrapper run failed for analysis %s: %s", analysis_id, exc)
            return {
                "overall_swarm_score": 0.0,
                "fairness_grade": "C",
                "agreement_score": 0.0,
                "agents_completed": 0,
                "agents_failed": len(self.AGENTS),
                "consensus_findings": [],
                "contested_findings": [],
                "agent_results": [],
                "top_recommendation": "Retry swarm analysis when model endpoints are available.",
                "executive_summary": "Swarm analysis did not complete due to upstream model failures.",
                "warnings": ["LOW_CONFIDENCE: all swarm agents failed in background run."],
            }

    def _build_agent_prompt(self, agent_name: str, specialty: str, context: dict[str, Any]) -> str:
        specialty_instructions = {
            "statistical_bias_analysis": (
                "Focus on statistical fairness metrics, threshold violations, disparate impact ratios, "
                "and severity quantification."
            ),
            "contextual_fairness_analysis": (
                "Focus on real-world and social context, downstream harms, and practical fairness implications."
            ),
            "historical_discrimination_patterns": (
                "Focus on known historical discrimination patterns across hiring, lending, insurance, and healthcare."
            ),
            "intersectional_bias_detection": (
                "Focus on intersectional harms and compounded disadvantage across multiple protected attributes."
            ),
        }

        payload_preview = {
            "dataset_summary": context.get("dataset_summary"),
            "fairness_metrics": context.get("fairness_metrics"),
            "sensitive_attributes": context.get("sensitive_attributes"),
            "target_column": context.get("target_column"),
            "sample_data": context.get("sample_data"),
        }

        prompt = (
            f"You are agent '{agent_name}' with specialty '{specialty}'. "
            f"{specialty_instructions.get(specialty, 'Perform careful fairness analysis.')}\n\n"
            "Analyze the provided fairness context and identify the most important bias indicators. "
            "Return ONLY valid JSON with this exact schema:\n"
            "{\n"
            "  \"agent_name\": \"string\",\n"
            "  \"specialty\": \"string\",\n"
            "  \"confidence_score\": 0.0,\n"
            "  \"bias_indicators\": [\n"
            "    {\n"
            "      \"attribute\": \"string\",\n"
            "      \"metric_name\": \"string\",\n"
            "      \"value\": 0.0,\n"
            "      \"severity\": \"low|medium|high|critical\",\n"
            "      \"plain_explanation\": \"string\"\n"
            "    }\n"
            "  ],\n"
            "  \"top_finding\": \"string\",\n"
            "  \"recommended_action\": \"string\",\n"
            "  \"analysis_reasoning\": \"string\"\n"
            "}\n\n"
            "Do not include markdown, code fences, or extra commentary.\n\n"
            f"Context JSON:\n{self._safe_json(payload_preview)}"
        )
        return prompt

    async def _run_agent(
        self,
        agent_name: str,
        agent_config: dict[str, Any],
        context: dict[str, Any],
        user_id: str | None,
        analysis_id: str,
    ) -> SwarmAgentResult | None:
        prompt = self._build_agent_prompt(
            agent_name=agent_name,
            specialty=str(agent_config["specialty"]),
            context=context,
        )

        api_key = self._get_api_key(str(agent_config["api_key_env"]))
        masked_key = self._mask_secret(api_key)
        self._audit_log(
            action=f"swarm_agent_started:{agent_name}",
            user_id=user_id,
            analysis_id=analysis_id,
        )
        logger.info("Calling swarm agent=%s key=%s", agent_name, masked_key)

        started = perf_counter()
        try:
            call_map = {
                "nvidia_llama": self._call_nvidia_nim,
                "google_gemini": self._call_google_gemini,
                "groq_llama": self._call_groq,
                "hf_mixtral": self._call_hf_mixtral,
            }
            caller = call_map[agent_name]
            response_payload = await asyncio.wait_for(caller(prompt, agent_config), timeout=60.0)
            if response_payload is None:
                self._audit_log(
                    action=f"swarm_agent_failed:{agent_name}:timeout_or_no_data",
                    user_id=user_id,
                    analysis_id=analysis_id,
                )
                return None

            result = self._normalize_agent_result(agent_name, str(agent_config["specialty"]), response_payload)
            elapsed_ms = int((perf_counter() - started) * 1000)
            self._audit_log(
                action=f"swarm_agent_completed:{agent_name}:{elapsed_ms}ms",
                user_id=user_id,
                analysis_id=analysis_id,
            )
            return result
        except asyncio.TimeoutError:
            self._audit_log(
                action=f"swarm_agent_failed:{agent_name}:timeout",
                user_id=user_id,
                analysis_id=analysis_id,
            )
            return None
        except Exception as exc:
            logger.warning("Agent %s failed (%s)", agent_name, type(exc).__name__)
            self._audit_log(
                action=f"swarm_agent_failed:{agent_name}:exception",
                user_id=user_id,
                analysis_id=analysis_id,
            )
            return None

    async def _call_nvidia_nim(self, prompt: str, agent_config: dict[str, Any]) -> dict[str, Any] | None:
        api_key = self._get_api_key(str(agent_config["api_key_env"]))
        url = f"{agent_config['base_url']}/chat/completions"
        payload = {
            "model": agent_config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": "You are a rigorous fairness auditor. Return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1500,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 429 and attempt < 3:
                    await asyncio.sleep(2**(attempt + 1))
                    continue
                response.raise_for_status()
                response_data = response.json()
                content = (
                    response_data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                return self._parse_model_json(content)
            except httpx.TimeoutException:
                return None
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < 3:
                    await asyncio.sleep(2**(attempt + 1))
                    continue
                logger.warning("NVIDIA request failed with status=%s", exc.response.status_code)
                return None
            except Exception as exc:
                logger.warning("NVIDIA parsing failed (%s)", type(exc).__name__)
                return None
        return None

    async def _call_google_gemini(self, prompt: str, agent_config: dict[str, Any]) -> dict[str, Any] | None:
        api_key = self._get_api_key(str(agent_config["api_key_env"]))
        url = (
            f"{agent_config['base_url']}/models/{agent_config['model']}:generateContent"
            f"?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 1500,
                "temperature": 0.1,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            return self._parse_model_json(text)
        except httpx.TimeoutException:
            return None
        except Exception as exc:
            logger.warning("Gemini call failed (%s)", type(exc).__name__)
            return None

    async def _call_groq(self, prompt: str, agent_config: dict[str, Any]) -> dict[str, Any] | None:
        api_key = self._get_api_key(str(agent_config["api_key_env"]))
        url = f"{agent_config['base_url']}/chat/completions"
        payload = {
            "model": agent_config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": "You are a fairness auditing specialist. Return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1500,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()
            content = (
                response_data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return self._parse_model_json(content)
        except httpx.TimeoutException:
            return None
        except Exception as exc:
            logger.warning("Groq call failed (%s)", type(exc).__name__)
            return None

    async def _call_hf_mixtral(self, prompt: str, agent_config: dict[str, Any]) -> dict[str, Any] | None:
        api_key = self._get_api_key(str(agent_config["api_key_env"]))
        url = f"{agent_config['base_url']}/{agent_config['model']}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": (
                "You are a fairness analysis model. Return JSON only matching the expected schema.\n\n"
                f"{prompt}"
            ),
            "parameters": {
                "max_new_tokens": 1200,
                "temperature": 0.1,
                "return_full_text": False,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=50.0) as client:
                response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            generated_text = ""
            if isinstance(data, list) and data:
                generated_text = str(data[0].get("generated_text", ""))
            elif isinstance(data, dict):
                generated_text = str(data.get("generated_text", ""))

            return self._parse_model_json(generated_text)
        except httpx.TimeoutException:
            return None
        except Exception as exc:
            logger.warning("HuggingFace call failed (%s)", type(exc).__name__)
            return None

    def _weighted_consensus(self, agent_results: list[SwarmAgentResult]) -> SwarmConsensusResult:
        if not agent_results:
            raise ValueError("No successful swarm agent results available for consensus.")

        base_weights = {
            result.agent_name: float(self.AGENTS.get(result.agent_name, {}).get("weight", 0.0))
            for result in agent_results
        }
        weight_sum = sum(base_weights.values())
        normalized_weights = {
            name: (weight / weight_sum if weight_sum > 0 else 0.0)
            for name, weight in base_weights.items()
        }

        indicator_stats: dict[str, dict[str, Any]] = {}
        recommendation_score: dict[str, float] = {}
        agent_top_keys: list[str] = []

        for result in agent_results:
            agent_weight = normalized_weights.get(result.agent_name, 0.0)
            recommendation_score[result.recommended_action] = recommendation_score.get(result.recommended_action, 0.0) + (
                agent_weight * max(0.0, min(1.0, result.confidence_score))
            )

            if result.bias_indicators:
                top_indicator = max(
                    result.bias_indicators,
                    key=lambda indicator: self._SEVERITY_SCORE.get(indicator.severity, 1.0),
                )
                agent_top_keys.append(f"{top_indicator.attribute}|{top_indicator.metric_name}")

            for indicator in result.bias_indicators:
                key = f"{indicator.attribute}|{indicator.metric_name}"
                if key not in indicator_stats:
                    indicator_stats[key] = {
                        "indicator": indicator,
                        "weighted_severity": 0.0,
                        "contributors": 0,
                    }
                severity_score = self._SEVERITY_SCORE.get(indicator.severity, 1.0)
                indicator_stats[key]["weighted_severity"] += agent_weight * severity_score
                indicator_stats[key]["contributors"] += 1

        completed_agents = len(agent_results)
        contested_findings: list[BiasIndicator] = []
        consensus_findings: list[BiasIndicator] = []
        for value in indicator_stats.values():
            support_ratio = value["contributors"] / completed_agents
            if support_ratio > 0.5:
                consensus_findings.append(value["indicator"])
            elif value["contributors"] == 1:
                contested_findings.append(value["indicator"])

        if indicator_stats:
            weighted_indicator_score = (
                sum(item["weighted_severity"] for item in indicator_stats.values())
                / len(indicator_stats)
            )
            overall_swarm_score = round((weighted_indicator_score / 4.0) * 100.0, 2)
        else:
            overall_swarm_score = 0.0

        top_agreement_count = 0
        if agent_top_keys:
            top_agreement_count = max(agent_top_keys.count(key) for key in set(agent_top_keys))
        agreement_score = round(top_agreement_count / max(completed_agents, 1), 4)

        if overall_swarm_score <= 20:
            fairness_grade = "A"
        elif overall_swarm_score <= 40:
            fairness_grade = "B"
        elif overall_swarm_score <= 60:
            fairness_grade = "C"
        elif overall_swarm_score <= 80:
            fairness_grade = "D"
        else:
            fairness_grade = "F"

        top_recommendation = (
            max(recommendation_score.items(), key=lambda item: item[1])[0]
            if recommendation_score
            else "Collect more representative data and rerun fairness analysis."
        )

        executive_summary = (
            f"The AI swarm evaluated bias using {completed_agents} specialist agents and produced an "
            f"overall swarm bias score of {overall_swarm_score:.2f}/100 (grade {fairness_grade}). "
            f"Agent agreement on the top bias pattern is {agreement_score * 100:.1f}%. "
            f"Key recommendation: {top_recommendation}"
        )

        warnings: list[str] = []
        if completed_agents == 1:
            warnings.append("LOW_CONFIDENCE: only one agent contributed to consensus.")

        return SwarmConsensusResult(
            overall_swarm_score=overall_swarm_score,
            fairness_grade=fairness_grade,
            agreement_score=agreement_score,
            agents_completed=completed_agents,
            agents_failed=max(len(self.AGENTS) - completed_agents, 0),
            consensus_findings=consensus_findings,
            contested_findings=contested_findings,
            agent_results=agent_results,
            top_recommendation=top_recommendation,
            executive_summary=executive_summary,
            warnings=warnings,
        )

    def _normalize_agent_result(
        self,
        agent_name: str,
        specialty: str,
        raw_result: dict[str, Any],
    ) -> SwarmAgentResult:
        indicators_raw = raw_result.get("bias_indicators", [])
        indicators: list[BiasIndicator] = []
        if isinstance(indicators_raw, list):
            for item in indicators_raw:
                if not isinstance(item, dict):
                    continue
                severity = str(item.get("severity", "medium")).lower()
                if severity not in self._SEVERITY_SCORE:
                    severity = "medium"
                indicators.append(
                    BiasIndicator(
                        attribute=str(item.get("attribute", "unknown")),
                        metric_name=str(item.get("metric_name", "unknown_metric")),
                        value=float(item.get("value", 0.0)),
                        severity=severity,
                        plain_explanation=str(item.get("plain_explanation", "No explanation provided.")),
                    )
                )

        confidence = raw_result.get("confidence_score", 0.5)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.5
        confidence_value = max(0.0, min(1.0, confidence_value))

        return SwarmAgentResult(
            agent_name=str(raw_result.get("agent_name", agent_name)),
            specialty=str(raw_result.get("specialty", specialty)),
            confidence_score=confidence_value,
            bias_indicators=indicators,
            top_finding=str(raw_result.get("top_finding", "No top finding returned.")),
            recommended_action=str(
                raw_result.get(
                    "recommended_action",
                    "Review high-severity indicators and apply fairness mitigation techniques.",
                )
            ),
            analysis_reasoning=str(raw_result.get("analysis_reasoning", "No reasoning provided.")),
        )

    def _parse_model_json(self, content: Any) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if content is None:
            return {}

        text = str(content).strip()
        if not text:
            return {}

        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        json_candidates = re.findall(r"\{[\s\S]*\}", text)
        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        fixed = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            parsed = json.loads(fixed)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
        return {}

    def _safe_json(self, value: Any, max_chars: int = 12000) -> str:
        try:
            raw = json.dumps(value, ensure_ascii=True, default=str)
        except Exception:
            raw = str(value)
        if len(raw) > max_chars:
            return raw[:max_chars] + "..."
        return raw

    def _get_api_key(self, env_name: str) -> str:
        key = getattr(settings, env_name, None)
        if not key:
            raise RuntimeError(f"Missing required API key: {env_name}")
        return str(key)

    def _mask_secret(self, value: str) -> str:
        if len(value) <= 8:
            return "****"
        return f"{value[:2]}***{value[-4:]}"

    def _audit_log(self, action: str, user_id: str | None, analysis_id: str | None) -> None:
        resource_id: str | None = None
        if analysis_id:
            try:
                resource_id = str(UUID(analysis_id))
            except (ValueError, TypeError):
                resource_id = None

        try:
            supabase = get_supabase_client()
            supabase.table("audit_logs").insert(
                {
                    "user_id": user_id,
                    "action": action,
                    "resource_type": "swarm_agent",
                    "resource_id": resource_id,
                    "ip_address": None,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as exc:
            logger.warning("Failed to write swarm audit log: %s", exc)
