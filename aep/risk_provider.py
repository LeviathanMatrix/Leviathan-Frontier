from __future__ import annotations

import copy
import time
from typing import Any

from .brand import IMPLEMENTATION_ID, PROJECT_VERSION


class RiskInputProvider:
    def build_risk_input(self, action_request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class StaticRiskInputProvider(RiskInputProvider):
    def __init__(self, *, risk_score: float = 15.0, decision_confidence: float = 0.75) -> None:
        self.risk_score = float(risk_score)
        self.decision_confidence = float(decision_confidence)

    def build_risk_input(self, action_request: dict[str, Any]) -> dict[str, Any]:
        request = action_request if isinstance(action_request, dict) else {}
        agent = request.get("agent") if isinstance(request.get("agent"), dict) else {}
        agent_id = str(agent.get("agent_id") or "demo-agent").strip() or "demo-agent"
        request_id = str(request.get("request_id") or "stub-request").strip() or "stub-request"
        generated_at = int(time.time())
        return {
            "schema_version": "risk_input.v1",
            "input_id": f"stub-risk-{request_id}",
            "agent_id": agent_id,
            "intent_id": request_id,
            "generated_at": generated_at,
            "source_systems": [
                {
                    "name": f"{IMPLEMENTATION_ID}:static-risk-provider",
                    "version": PROJECT_VERSION,
                    "kind": "scorer",
                }
            ],
            "mcp_scores": {
                "r1_control": self.risk_score,
                "r2_funding": self.risk_score,
                "r3_convergence": self.risk_score,
                "r4_terminal": self.risk_score,
                "r5_history": self.risk_score,
                "r6_lp_behavior": self.risk_score,
                "r7_anomaly": self.risk_score,
                "x_cross_signal": self.risk_score,
                "token_score": {
                    "permission": self.risk_score,
                    "rug": self.risk_score,
                    "history": self.risk_score,
                    "consistency_adjustment": 0.0,
                    "weighted_score": self.risk_score,
                    "grade": "B",
                },
                "advisory_decision": "ALLOW",
                "decision_confidence": self.decision_confidence,
            },
            "aep_context": {
                "counterparty_risk": self.risk_score,
                "execution_complexity_risk": self.risk_score,
                "market_risk": self.risk_score,
                "anomaly_risk": self.risk_score,
                "evidence_gap_risk": max(0.0, 100.0 - self.decision_confidence * 100.0),
                "governance_surface_risk": self.risk_score,
                "agent_reputation_bonus": 0.0,
                "treasury_health_bonus": 0.0,
            },
        }


class UserProvidedRiskInputProvider(RiskInputProvider):
    def __init__(self, risk_input: dict[str, Any]) -> None:
        if not isinstance(risk_input, dict):
            raise ValueError("risk_input must be a dict")
        self._risk_input = copy.deepcopy(risk_input)

    def build_risk_input(self, action_request: dict[str, Any]) -> dict[str, Any]:
        _ = action_request
        return copy.deepcopy(self._risk_input)
