"""Logique kill_check (Phase 4, fleet — évaluation).

Pure et auditable : couvre les verdicts par tier fidèlement au Chap 20, dont la
règle absolue « T2 ne se kill jamais automatiquement ».
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from app.modules.fleet.kill_check import (  # noqa: E402
    HEALTHY,
    KILL_NOW,
    MANUAL_REVIEW,
    PENDING_KILL,
    Metrics,
    evaluate,
)


# --- T0 -------------------------------------------------------------------

def test_t0_healthy_before_window():
    assert evaluate("t0", Metrics(days_since_deploy=10)) == HEALTHY


def test_t0_healthy_with_any_signal():
    assert evaluate("t0", Metrics(days_since_deploy=20, signup_count=30)) == HEALTHY
    assert evaluate("t0", Metrics(days_since_deploy=20, visit_count=500, conversion_rate=0.04)) == HEALTHY
    assert evaluate("t0", Metrics(days_since_deploy=20, qualitative_feedback_count=3)) == HEALTHY


def test_t0_kill_now_at_21_without_signal():
    assert evaluate("t0", Metrics(days_since_deploy=21)) == KILL_NOW


def test_t0_kill_now_on_cost_cap():
    assert evaluate("t0", Metrics(days_since_deploy=20, total_cost=100)) == KILL_NOW


def test_t0_pending_kill_grace_zone():
    assert evaluate("t0", Metrics(days_since_deploy=20, total_cost=50)) == PENDING_KILL


# --- T1 -------------------------------------------------------------------

def test_t1_healthy_before_window():
    assert evaluate("t1", Metrics(days_since_deploy=20)) == HEALTHY


def test_t1_healthy_with_full_signal():
    m = Metrics(days_since_deploy=31, retention_d7=0.35, paid_users_count=1, active_users_last_7d=10)
    assert evaluate("t1", m) == HEALTHY


def test_t1_kill_low_retention():
    assert evaluate("t1", Metrics(days_since_deploy=31, retention_d7=0.10)) == KILL_NOW


def test_t1_kill_no_wtp_at_45():
    assert evaluate("t1", Metrics(days_since_deploy=45, retention_d7=0.2, wtp_declarations=0)) == KILL_NOW


def test_t1_kill_on_cost_cap():
    assert evaluate("t1", Metrics(days_since_deploy=31, retention_d7=0.2, wtp_declarations=1, total_cost=500)) == KILL_NOW


def test_t1_pending_kill():
    m = Metrics(days_since_deploy=31, retention_d7=0.2, wtp_declarations=1, active_users_last_7d=5)
    assert evaluate("t1", m) == PENDING_KILL


# --- T2 (ne se kill jamais automatiquement) -------------------------------

def test_t2_healthy_default():
    assert evaluate("t2", Metrics()) == HEALTHY


def test_t2_manual_review_high_churn():
    assert evaluate("t2", Metrics(churn_rate_3m=0.25, days_below_mrr_threshold=90)) == MANUAL_REVIEW


def test_t2_manual_review_low_mrr():
    assert evaluate("t2", Metrics(days_below_mrr_threshold=90, mrr=50)) == MANUAL_REVIEW


def test_t2_never_kill_now_even_when_terrible():
    verdict = evaluate("t2", Metrics(churn_rate_3m=0.9, days_below_mrr_threshold=200, mrr=0))
    assert verdict == MANUAL_REVIEW
    assert verdict != KILL_NOW
