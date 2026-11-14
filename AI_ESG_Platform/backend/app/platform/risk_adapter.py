"""ISO 31000 Risk Engine Adapter for Member 5 Supplier Intelligence.

Adheres strictly to Member 2's deterministic ISO 31000:2018 5x5 screening matrix:
    risk score = round(((likelihood * impact) / 25.0) * 100.0, 2)
    Levels:
        >= 68: CRITICAL
        >= 40: HIGH
        >= 20: MODERATE
        < 20:  LOW

Calculates category subscores as (100 - average_category_risk) and overall as arithmetic mean.
Provides local calculation with Member 2 /api/risk-report integration and graceful fallback.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from fastapi import HTTPException, status

from app.platform.config import MEMBER2_API_URL

logger = logging.getLogger(__name__)

LEVELS = (
    (68.0, "CRITICAL"),
    (40.0, "HIGH"),
    (20.0, "MODERATE"),
    (0.0, "LOW"),
)


def clamp5(value: int | float) -> int:
    """Clamp integer or float to the 1..5 range."""
    return max(1, min(5, int(round(float(value)))))


def risk_level(score: float) -> str:
    """Classify a 0-100 score into ISO 31000 tier."""
    for minimum, label in LEVELS:
        if score >= minimum:
            return label
    return "LOW"


def calculate_risk_score(
    likelihood: int | float,
    impact: int | float,
    severity: Optional[int | float] = None,
) -> float:
    """Calculate 0-100 risk display score from 1-5 likelihood and 1-5 impact.

    Derived from Member 2's ISO 31000 5x5 matrix formula.
    """
    l, i = clamp5(likelihood), clamp5(impact)
    return round(((l * i) / 25.0) * 100.0, 2)


def evaluate_supplier_findings_risk(
    findings: List[Dict[str, Any]],
    member2_api_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate supplier ESG performance and risk metrics across all active findings.

    Returns:
        {
            "risk_score": float,
            "risk_level": str,
            "environmental": float,
            "social": float,
            "governance": float,
            "overall": float,
            "methodology": str,
            "evaluation_mode": str,
            "service_status": str,
            "evaluated_by": str,
            "remote_endpoint": Optional[str],
            "fallback_reason": Optional[str],
        }
    """
    # Attempt remote call to Member 2 API if URL is provided and accessible
    if member2_api_url:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.post(f"{member2_api_url.rstrip('/')}/api/risk/evaluate", json={"findings": findings})
                if resp.status_code == 200:
                    data = resp.json()
                    logger.info("Successfully evaluated risk via Member 2 API")
                    data.setdefault("evaluation_mode", "MEMBER2_REMOTE_API")
                    data.setdefault("service_status", "ONLINE")
                    data.setdefault("evaluated_by", "Member 2 Remote Risk Service")
                    return data
        except Exception as exc:
            logger.debug(f"Member 2 remote service unreachable ({exc}), using deterministic local engine")

    # Local calculation adhering to Member 2's exact ISO 31000 logic
    buckets: Dict[str, List[float]] = {
        "ENVIRONMENTAL": [],
        "SOCIAL": [],
        "GOVERNANCE": [],
    }

    all_scores: List[float] = []

    for f in findings:
        cat = str(f.get("category", "")).strip().upper()
        score = float(f.get("risk_score", 0.0))
        all_scores.append(score)
        if cat in buckets:
            buckets[cat].append(score)

    scores: Dict[str, float] = {}
    for cat, values in buckets.items():
        if values:
            avg_risk = sum(values) / len(values)
            # Higher risk finding decreases the compliance ESG subscore
            scores[cat] = round(max(0.0, min(100.0, 100.0 - avg_risk)), 2)
        else:
            # Baseline benchmark when no adverse findings exist in this category
            scores[cat] = 88.0

    overall = round(sum(scores.values()) / 3.0, 2)

    if all_scores:
        avg_risk = round(sum(all_scores) / len(all_scores), 2)
        r_level = risk_level(avg_risk)
    else:
        avg_risk = None
        r_level = "NOT_ASSESSED"

    return {
        "risk_score": avg_risk,
        "risk_level": r_level,
        "environmental": scores["ENVIRONMENTAL"],
        "social": scores["SOCIAL"],
        "governance": scores["GOVERNANCE"],
        "overall": overall,
        "methodology": "ISO 31000:2018-aligned 5x5 likelihood-impact screening matrix (Member 2 standard).",
        "evaluation_mode": "LOCAL_ISO31000_ADAPTER",
        "service_status": "OFFLINE",
        "evaluated_by": "Member 5 ISO 31000:2018 Adapter",
        "remote_endpoint": None,
        "fallback_reason": None,
    }


def evaluate_via_member2_api(
    old_policy_path: str,
    new_policy_path: str,
    member2_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute policy comparison risk assessment via Member 2's POST /api/risk-report.

    Contract with Member 2:
        Input: Multipart form with 'old_policy' (baseline PDF) and 'new_policy' (supplier policy PDF).
        Output: RiskReportResponse with 'risks: List[RiskItem]' and 'esg_scores: ESGScores'.

    Graceful Fallback Policy:
        - Transport/Availability failure (ConnectError, ConnectTimeout, ReadTimeout):
          Engages deterministic local fallback with evaluation_mode='LOCAL_ISO31000_ADAPTER_FALLBACK'.
        - Remote HTTP 400/422 or HTTP 500 or schema violation:
          DOES NOT fall back. Raises clear HTTPException(400/502).
    """
    url = (member2_url or MEMBER2_API_URL).rstrip("/")
    endpoint = f"{url}/api/risk-report"

    old_p = Path(old_policy_path)
    new_p = Path(new_policy_path)

    if not old_p.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Enterprise baseline policy file not found: {old_p.name}",
        )
    if not new_p.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supplier policy document file not found: {new_p.name}",
        )

    try:
        with open(old_p, "rb") as f_old, open(new_p, "rb") as f_new:
            old_bytes = f_old.read()
            new_bytes = f_new.read()

        files = {
            "old_policy": (old_p.name, old_bytes, "application/pdf"),
            "new_policy": (new_p.name, new_bytes, "application/pdf"),
        }

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(endpoint, files=files)

    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        logger.warning(
            f"Member 2 risk engine connection failed ({type(exc).__name__}: {exc}). Engaging local ISO 31000 fallback."
        )
        return {
            "evaluation_mode": "LOCAL_ISO31000_ADAPTER_FALLBACK",
            "service_status": "OFFLINE",
            "evaluated_by": "Member 5 ISO 31000 Fallback Adapter",
            "remote_endpoint": endpoint,
            "fallback_reason": f"Connection to Member 2 service failed ({type(exc).__name__}). Using local fallback engine.",
            "methodology": "ISO 31000:2018 Local Deterministic Matrix (Offline Fallback)",
            "risk_score": None,
            "risk_level": "NOT_ASSESSED",
            "environmental": 80.0,
            "social": 80.0,
            "governance": 80.0,
            "overall": 80.0,
            "risks": [],
            "risk_count": 0,
            "high_or_critical_count": 0,
        }
    except Exception as exc:
        logger.error(f"Unexpected transport error contacting Member 2: {exc}")
        return {
            "evaluation_mode": "LOCAL_ISO31000_ADAPTER_FALLBACK",
            "service_status": "OFFLINE",
            "evaluated_by": "Member 5 ISO 31000 Fallback Adapter",
            "remote_endpoint": endpoint,
            "fallback_reason": f"Transport error contacting Member 2 ({type(exc).__name__}: {str(exc)})",
            "methodology": "ISO 31000:2018 Local Deterministic Matrix (Offline Fallback)",
            "risk_score": None,
            "risk_level": "NOT_ASSESSED",
            "environmental": 80.0,
            "social": 80.0,
            "governance": 80.0,
            "overall": 80.0,
            "risks": [],
            "risk_count": 0,
            "high_or_critical_count": 0,
        }

    # Inspect HTTP response status from Member 2
    if resp.status_code in (400, 422):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Member 2 risk engine rejected policy comparison ({resp.status_code}): {resp.text}",
        )
    if resp.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Member 2 risk engine returned server error ({resp.status_code}): {resp.text}",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Member 2 risk engine returned unexpected status code ({resp.status_code}): {resp.text}",
        )

    # Validate JSON payload and response schema
    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Member 2 returned non-JSON response: {resp.text[:200]}",
        )

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Member 2 returned invalid payload structure (expected JSON object).",
        )

    esg_scores = data.get("esg_scores")
    risks = data.get("risks")

    if esg_scores is None or risks is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Member 2 response is missing required contract fields ('esg_scores' or 'risks').",
        )

    # Compute supplier-level risk score from risks[] exactly matching Member 2's ISO 31000 logic
    risk_scores = [float(r.get("risk_score", 0.0)) for r in risks if isinstance(r, dict)]
    if risk_scores:
        avg_risk = round(sum(risk_scores) / len(risk_scores), 2)
        r_level = risk_level(avg_risk)
    else:
        avg_risk = None
        r_level = "NOT_ASSESSED"

    return {
        "evaluation_mode": "MEMBER2_REMOTE_API",
        "service_status": "ONLINE",
        "evaluated_by": "Member 2 Policy Risk Engine (/api/risk-report)",
        "remote_endpoint": endpoint,
        "fallback_reason": None,
        "methodology": "ISO 31000:2018-aligned Risk Engine (Member 2 Remote API)",
        "risk_score": avg_risk,
        "risk_level": r_level,
        "environmental": float(esg_scores.get("environmental", 80.0)),
        "social": float(esg_scores.get("social", 80.0)),
        "governance": float(esg_scores.get("governance", 80.0)),
        "overall": float(esg_scores.get("overall", 80.0)),
        "risks": risks,
        "risk_count": data.get("risk_count", len(risks)),
        "high_or_critical_count": data.get("high_or_critical_count", 0),
    }
