"""
smurf_detector.py – Detect smurfing patterns (fan-in / fan-out).

Smurfing (structuring)
-----------------------
  Fan-in  : FAN_THRESHOLD+ unique senders → 1 receiver within a 72-hour window.
  Fan-out : 1 sender → FAN_THRESHOLD+ unique receivers within a 72-hour window.

False-positive control (semantic approach)
------------------------------------------
Rather than percentile-based exclusion (which breaks on small datasets where
legitimate merchants and mule aggregators have the same transaction count),
we use two semantic signals:

  Fan-in exclusion — MERCHANT pattern:
    Retail merchants receive payments of VARIABLE amounts from many customers.
    Smurfing aggregators receive UNIFORM small deposits from many sources.
    If the coefficient of variation (std/mean) of a receiver's incoming amounts
    exceeds MERCHANT_AMOUNT_CV_THRESHOLD → treat as legitimate merchant → exclude
    from fan-in rings (will NOT be flagged).

  Fan-out exclusion — PAYROLL BATCH pattern:
    Corporate payroll systems push all salary transactions simultaneously
    (within seconds of each other as a single batch job).
    Smurfing dispersers stagger their sends over minutes/hours to stay below
    reporting thresholds.
    If ALL outgoing transactions from a sender occur within PAYROLL_BATCH_SECONDS
    of each other → treat as payroll batch → exclude from fan-out rings.

Performance
-----------
Two-pointer sliding window: O(n) per group instead of O(n²).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import List, Dict, Set

import pandas as pd

from .config import (
    FAN_THRESHOLD,
    SMURF_WINDOW_HOURS,
    MERCHANT_AMOUNT_CV_THRESHOLD,
    PAYROLL_BATCH_SECONDS,
)

log = logging.getLogger(__name__)


def _merchant_receivers(df: pd.DataFrame) -> Set[str]:
    """
    Return receiver IDs that look like legitimate merchants.

    Criterion: coefficient of variation (std / mean) of amounts received
    exceeds MERCHANT_AMOUNT_CV_THRESHOLD.  Retail purchases naturally have
    high price variance; structured smurf deposits do not.

    Fully vectorised — no Python-level for-loop over groups.
    """
    # pandas groupby std() uses ddof=1 (sample std) by default — consistent with
    # the previous per-group amounts.std(ddof=1) calculation.
    stats = df.groupby("receiver_id")["amount"].agg(
        mean_amt="mean",
        std_amt="std",   # ddof=1
        count_amt="count",
    )
    stats = stats[(stats["count_amt"] >= 2) & (stats["mean_amt"] > 0)]
    stats["cv"] = stats["std_amt"] / stats["mean_amt"]
    excluded = set(stats[stats["cv"] > MERCHANT_AMOUNT_CV_THRESHOLD].index)
    if excluded:
        log.info("Fan-in merchant exclusion (high amount CV): %d accounts", len(excluded))
    return excluded


def _payroll_senders(df: pd.DataFrame) -> Set[str]:
    """
    Return sender IDs that look like payroll / batch processors.

    Criterion: ALL outgoing transactions from the sender occur within
    PAYROLL_BATCH_SECONDS of each other (i.e. time span ≤ threshold).
    A payroll system fires all salary debits in a single batch run;
    a smurfing disperser staggers payments to avoid detection.

    Fully vectorised — no Python-level for-loop over groups.
    """
    ts_stats = df.groupby("sender_id")["timestamp"].agg(["min", "max", "count"])
    ts_stats = ts_stats[ts_stats["count"] >= 2]
    # Span in seconds between first and last outgoing tx per sender
    ts_stats["span_s"] = (ts_stats["max"] - ts_stats["min"]).dt.total_seconds()
    excluded = set(ts_stats[ts_stats["span_s"] <= PAYROLL_BATCH_SECONDS].index)
    if excluded:
        log.info("Fan-out payroll exclusion (batch timestamps): %d accounts", len(excluded))
    return excluded


def _sliding_window_unique(
    sorted_times: list,
    sorted_counterparts: list,
    hub: str,
    window_td: timedelta,
    threshold: int,
) -> tuple:
    """
    Two-pointer sliding window to find any window with >= threshold unique
    counterparties (excluding `hub` itself).

    Returns (triggered: bool, unique_counterparts: set)
    """
    n = len(sorted_times)
    if n < threshold:
        return False, set()

    left = 0
    window: dict = {}

    for right in range(n):
        cp = sorted_counterparts[right]
        if cp != hub:
            window[cp] = window.get(cp, 0) + 1

        while sorted_times[right] - sorted_times[left] > window_td:
            lcp = sorted_counterparts[left]
            if lcp != hub:
                window[lcp] -= 1
                if window[lcp] == 0:
                    del window[lcp]
            left += 1

        if len(window) >= threshold:
            return True, set(window.keys())

    return False, set()


def detect_smurfing(df: pd.DataFrame) -> List[Dict]:
    """
    Detect fan-in and fan-out smurfing patterns.

    Returns
    -------
    List of ring dicts with keys:
        members  : list[str]  – all involved accounts
        pattern  : str        – "fan_in" or "fan_out"
        hub      : str        – the central aggregator/disperser
        hub_type : str        – "aggregator" | "disperser"
    """
    rings: List[Dict] = []
    seen_keys: set = set()
    window_td = timedelta(hours=SMURF_WINDOW_HOURS)

    excluded_fan_in = _merchant_receivers(df)
    excluded_fan_out = _payroll_senders(df)

    # Sort once — groupby preserves row order within each group,
    # so per-group re-sort is unnecessary.
    df_s = df.sort_values("timestamp")

    # ── Pre-filter: only iterate groups with enough transactions ───────────
    recv_counts = df_s.groupby("receiver_id").size()
    candidate_recv = set(
        recv_counts[recv_counts >= FAN_THRESHOLD].index
    ) - excluded_fan_in

    send_counts = df_s.groupby("sender_id").size()
    candidate_send = set(
        send_counts[send_counts >= FAN_THRESHOLD].index
    ) - excluded_fan_out

    # ── Fan-in: many senders → one receiver ────────────────────────────────
    fan_in_df = df_s[df_s["receiver_id"].isin(candidate_recv)]
    for receiver, grp in fan_in_df.groupby("receiver_id"):
        times   = grp["timestamp"].tolist()
        senders = grp["sender_id"].tolist()

        triggered, window_senders = _sliding_window_unique(
            times, senders, receiver, window_td, FAN_THRESHOLD
        )
        if triggered:
            key = ("fan_in", receiver)
            if key not in seen_keys:
                seen_keys.add(key)
                members = sorted(window_senders) + [receiver]
                rings.append({
                    "members": members,
                    "pattern": "fan_in",
                    "hub": receiver,
                    "hub_type": "aggregator",
                    "member_count": len(members),
                })

    # ── Fan-out: one sender → many receivers ────────────────────────────────
    fan_out_df = df_s[df_s["sender_id"].isin(candidate_send)]
    for sender, grp in fan_out_df.groupby("sender_id"):
        times     = grp["timestamp"].tolist()
        receivers = grp["receiver_id"].tolist()

        triggered, window_receivers = _sliding_window_unique(
            times, receivers, sender, window_td, FAN_THRESHOLD
        )
        if triggered:
            key = ("fan_out", sender)
            if key not in seen_keys:
                seen_keys.add(key)
                members = [sender] + sorted(window_receivers)
                rings.append({
                    "members": members,
                    "pattern": "fan_out",
                    "hub": sender,
                    "hub_type": "disperser",
                    "member_count": len(members),
                })

    log.info("Smurfing detection: %d rings found (fan-in + fan-out)", len(rings))
    return rings
