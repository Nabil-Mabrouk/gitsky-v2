"""Logique d'évaluation `kill_check` (Chap 20) — PURE, auditable, reproductible.

Chaque tier retourne un verdict parmi healthy | pending_kill | kill_now |
manual_review. **T2 ne se kill jamais automatiquement** (manual_review au pire).
Fidèle au pseudo-code du Chap 20 §Règles d'Évaluation.
"""

from dataclasses import dataclass

HEALTHY = "healthy"
PENDING_KILL = "pending_kill"
KILL_NOW = "kill_now"
MANUAL_REVIEW = "manual_review"


@dataclass
class Metrics:
    days_since_deploy: int = 0
    # T0
    signup_count: int = 0
    visit_count: int = 0
    conversion_rate: float = 0.0
    qualitative_feedback_count: int = 0
    total_cost: float = 0.0
    # T1
    active_users_last_7d: int = 0
    retention_d7: float = 0.0
    paid_users_count: int = 0
    wtp_declarations: int = 0
    # T2
    mrr: float = 0.0
    churn_rate_3m: float = 0.0
    days_below_mrr_threshold: int = 0


def evaluate_t0(m: Metrics) -> str:
    if m.days_since_deploy < 19:
        return HEALTHY
    if (
        m.signup_count >= 30
        or (m.visit_count >= 500 and m.conversion_rate >= 0.03)
        or m.qualitative_feedback_count >= 3
    ):
        return HEALTHY  # promotion T1 recommandée
    if m.days_since_deploy >= 21 or m.total_cost >= 100:
        return KILL_NOW
    return PENDING_KILL  # zone J+19 à J+21 sans signal


def evaluate_t1(m: Metrics) -> str:
    if m.days_since_deploy < 30:
        return HEALTHY
    if (
        m.retention_d7 >= 0.30
        and (m.paid_users_count >= 1 or m.wtp_declarations >= 3)
        and m.active_users_last_7d >= 10
    ):
        return HEALTHY  # promotion T2 recommandée
    if m.retention_d7 < 0.15 and m.days_since_deploy >= 30:
        return KILL_NOW
    if m.days_since_deploy >= 45 and m.wtp_declarations == 0:
        return KILL_NOW
    if m.total_cost >= 500:
        return KILL_NOW
    return PENDING_KILL


def evaluate_t2(m: Metrics) -> str:
    # T2 ne se kill jamais automatiquement : au pire une revue manuelle.
    if m.churn_rate_3m > 0.20 and m.days_below_mrr_threshold >= 90:
        return MANUAL_REVIEW
    if m.days_below_mrr_threshold >= 90 and m.mrr < 100:
        return MANUAL_REVIEW
    return HEALTHY


_EVALUATORS = {"t0": evaluate_t0, "t1": evaluate_t1, "t2": evaluate_t2}


def evaluate(tier: str, m: Metrics) -> str:
    evaluator = _EVALUATORS.get(tier)
    return evaluator(m) if evaluator else HEALTHY
