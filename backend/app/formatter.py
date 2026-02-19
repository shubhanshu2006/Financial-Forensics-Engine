"""
formatter.py – Produce the final API response in exact spec format.

JSON contract (evaluation-spec)
---------------------------------
{
  "suspicious_accounts": [{account_id, suspicion_score, detected_patterns, ring_id,
                            risk_explanation}],
  "fraud_rings":          [{ring_id, member_accounts, pattern_type, risk_score}],
  "summary":             {total_accounts_analyzed, suspicious_accounts_flagged,
                           fraud_rings_detected, processing_time_seconds},
}

When ?detail=true is passed to the /analyze endpoint the response also includes:
  "graph":       {nodes: [...], edges: [...]}
  "parse_stats": {...}

Fields NOT in the evaluation spec (confidence, network_statistics) are omitted
from the default response to keep the schema compliant.

All scores rounded to 1 decimal place. suspicious_accounts sorted descending.
Only accounts with suspicion_score >= MIN_SUSPICION_SCORE appear in the output.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import networkx as nx

from .config import RING_RISK, MIN_SUSPICION_SCORE

log = logging.getLogger(__name__)

# Graph visualisation cap: if > this many nodes, strip edge transaction lists
# to keep the JSON payload manageable and processing fast.
_GRAPH_PAYLOAD_NODE_CAP = 300

# Community detection (Louvain) is O(n²) — skip for large graphs.
# Lowered from 500 to 200 — Louvain takes 2-4s on slow CPUs (Render free tier).
_COMMUNITY_MAX_NODES = 200

# Temporal profile computation cap: iterates all edges of each suspicious node.
# Skip for larger graphs to save ~0.5-1s on slow CPUs.
_TEMPORAL_MAX_NODES = 300


def _risk_score(ring: Dict) -> float:
    """
    Calculate fraud ring risk score.
    Base value from config.RING_RISK, scaled slightly by member count.
    """
    base = RING_RISK.get(ring["pattern"], 65.0)
    n = len(ring["members"])
    return min(round(base + max(n - 3, 0) * 0.5, 1), 100.0)


def _confidence_score(ring: Dict) -> float:
    """
    Calculate a confidence score (0.0–1.0) for a fraud ring based on
    how strongly the pattern evidence supports the detection.

    Higher confidence for:
    - Cycle patterns (mathematically certain)
    - Smaller, tighter rings
    - Round-trips with high amount similarity
    - Multiple merged patterns confirming the same ring
    """
    pattern = ring["pattern"]
    n = len(ring["members"])

    # Base confidence by pattern type
    base_conf = {
        "cycle_length_3": 0.95,
        "cycle_length_4": 0.90,
        "cycle_length_5": 0.82,
        "fan_in": 0.78,
        "fan_out": 0.78,
        "shell_chain": 0.65,
        "round_trip": 0.80,
    }.get(pattern, 0.60)

    # Size penalty: very large rings are slightly less confident
    if n > 10:
        base_conf -= min((n - 10) * 0.01, 0.15)

    # Bonus for merged patterns (multiple independent detections)
    merged = ring.get("merged_patterns", [])
    if len(merged) > 1:
        base_conf = min(base_conf + 0.08, 1.0)

    # Round-trips: use amount similarity if available
    if pattern == "round_trip" and "similarity" in ring:
        base_conf = max(base_conf, ring["similarity"])

    return round(min(max(base_conf, 0.0), 1.0), 3)


def _network_statistics(G: nx.DiGraph) -> Dict[str, Any]:
    """Compute graph-level network statistics for the summary."""
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()

    stats: Dict[str, Any] = {
        "total_nodes": n_nodes,
        "total_edges": n_edges,
        "graph_density": round(nx.density(G), 6) if n_nodes > 0 else 0.0,
        "avg_degree": round((2 * n_edges) / n_nodes, 2) if n_nodes > 0 else 0.0,
    }

    # Connected components (on undirected view)
    try:
        undirected = G.to_undirected()
        stats["connected_components"] = nx.number_connected_components(undirected)
    except Exception:
        stats["connected_components"] = 0

    # Average clustering coefficient (skip for large graphs)
    if n_nodes <= 1000:
        try:
            stats["avg_clustering"] = round(
                nx.average_clustering(G.to_undirected()), 4
            )
        except Exception:
            stats["avg_clustering"] = 0.0
    else:
        stats["avg_clustering"] = None

    return stats


def _compute_community_ids(G: nx.DiGraph) -> Dict[str, int]:
    """
    Detect communities using Louvain method.
    Returns mapping of node_id → community_id.
    Skipped for large graphs (Louvain is O(n²) and can take 5-8 s on 1k+ nodes).
    """
    if G.number_of_nodes() == 0:
        return {}
    if G.number_of_nodes() > _COMMUNITY_MAX_NODES:
        log.info(
            "Community detection skipped: graph has %d nodes (limit %d)",
            G.number_of_nodes(), _COMMUNITY_MAX_NODES,
        )
        return {}
    try:
        undirected = G.to_undirected()
        communities = nx.community.louvain_communities(undirected, seed=42)
        mapping = {}
        for idx, community in enumerate(communities):
            for node in community:
                mapping[node] = idx
        return mapping
    except Exception as exc:
        log.warning("Community detection failed: %s", exc)
        return {}


def _temporal_profile(G: nx.DiGraph, node: str) -> Dict[str, Any] | None:
    """
    Build a temporal activity profile for a node based on edge timestamps.
    Returns hourly activity distribution.
    """
    try:
        attrs = G.nodes[node]
        first_tx = attrs.get("first_tx", "")
        last_tx = attrs.get("last_tx", "")
        if not first_tx or not last_tx:
            return None

        # Collect all transaction timestamps from edges
        hours: list = []
        for _, _, edata in G.edges(node, data=True):
            for tx in edata.get("transactions", []):
                ts_str = tx.get("timestamp", "")
                if ts_str and len(ts_str) >= 13:
                    try:
                        hour = int(ts_str[11:13])
                        hours.append(hour)
                    except (ValueError, IndexError):
                        pass
        for u, _, edata in G.in_edges(node, data=True):
            for tx in edata.get("transactions", []):
                ts_str = tx.get("timestamp", "")
                if ts_str and len(ts_str) >= 13:
                    try:
                        hour = int(ts_str[11:13])
                        hours.append(hour)
                    except (ValueError, IndexError):
                        pass

        if not hours:
            return None

        # Build hourly distribution
        hourly = [0] * 24
        for h in hours:
            hourly[h] += 1

        peak_hour = hourly.index(max(hourly))

        return {
            "hourly_distribution": hourly,
            "peak_hour": peak_hour,
            "active_hours": sum(1 for h in hourly if h > 0),
        }
    except Exception:
        return None


def format_output(
    rings: List[Dict],
    account_scores: Dict[str, Dict],
    G: nx.DiGraph,
    processing_time: float,
    total_accounts: int,
    parse_stats: dict | None = None,
    detail: bool = False,
) -> Dict[str, Any]:
    """
    Build the complete API response.

    Parameters
    ----------
    rings           : merged ring list (each has ring_id, members, pattern)
    account_scores  : output of scoring.calculate_scores()
    G               : NetworkX DiGraph
    processing_time : elapsed wall-clock seconds
    total_accounts  : unique account count from the raw CSV
    parse_stats     : optional parse diagnostic info
    detail          : when True, include ``graph`` and ``parse_stats`` in the
                      response (used by the frontend, omitted for evaluation)
    """
    # 1. Fraud rings (spec fields only: ring_id, member_accounts, pattern_type, risk_score)
    fraud_rings: List[Dict] = []
    for ring in rings:
        fraud_rings.append({
            "ring_id":         ring["ring_id"],
            "member_accounts": ring["members"],
            "pattern_type":    ring["pattern"],
            "risk_score":      float(_risk_score(ring)),  # explicit float for JSON
        })
    fraud_rings.sort(key=lambda r: r["risk_score"], reverse=True)

    # 2. Suspicious accounts
    # Spec-required fields only: account_id, suspicion_score (float), detected_patterns, ring_id
    # risk_explanation is included only in detail mode (frontend); omitted for evaluation.
    suspicious_accounts: List[Dict] = []
    for acc_id, d in account_scores.items():
        if d["score"] < MIN_SUSPICION_SCORE:
            continue
        ring_ids = d.get("ring_ids", [])
        primary_ring = ring_ids[0] if ring_ids else "UNASSIGNED"
        entry: Dict[str, Any] = {
            "account_id":        acc_id,
            "suspicion_score":   float(d["score"]),  # explicit float
            "detected_patterns": d["patterns"],
            "ring_id":           primary_ring,
        }
        if detail:
            entry["risk_explanation"] = d.get("risk_explanation", "")
        suspicious_accounts.append(entry)
    suspicious_accounts.sort(key=lambda x: x["suspicion_score"], reverse=True)

    # 3. Graph payload (with community_id and temporal_profile) — detail mode only
    suspicious_ids = {a["account_id"] for a in suspicious_accounts}
    if detail:
        large_graph = G.number_of_nodes() > _GRAPH_PAYLOAD_NODE_CAP
        community_map = _compute_community_ids(G)

        nodes: List[Dict] = []
        for node, attrs in G.nodes(data=True):
            nd: Dict[str, Any] = {
                "id":             node,
                "label":          node,
                "suspicious":     node in suspicious_ids,
                "tx_count":       attrs.get("tx_count", 0),
                "total_sent":     attrs.get("total_sent", 0.0),
                "total_received": attrs.get("total_received", 0.0),
                "net_flow":       attrs.get("net_flow", 0.0),
                "sent_count":     attrs.get("sent_count", 0),
                "received_count": attrs.get("received_count", 0),
                "first_tx":       attrs.get("first_tx", ""),
                "last_tx":        attrs.get("last_tx", ""),
                "community_id":   community_map.get(node),
            }
            if node in suspicious_ids:
                acc_info = account_scores.get(node, {})
                nd["suspicion_score"]   = acc_info.get("score", 0.0)
                nd["detected_patterns"] = acc_info.get("patterns", [])
                nd["ring_id"]           = (acc_info.get("ring_ids") or [""])[0]
                nd["ring_ids"]          = acc_info.get("ring_ids", [])
                nd["risk_explanation"]  = acc_info.get("risk_explanation", "")

                # Temporal profiles are expensive on slow CPUs — skip for larger graphs
                if G.number_of_nodes() <= _TEMPORAL_MAX_NODES:
                    tp = _temporal_profile(G, node)
                    if tp:
                        nd["temporal_profile"] = tp
            nodes.append(nd)

        edges: List[Dict] = []
        for u, v, attrs in G.edges(data=True):
            ed: Dict[str, Any] = {
                "source":       u,
                "target":       v,
                "total_amount": attrs.get("total_amount", 0.0),
                "avg_amount":   attrs.get("avg_amount", 0.0),
                "tx_count":     attrs.get("tx_count", 0),
                "first_tx":     attrs.get("first_tx", ""),
                "last_tx":      attrs.get("last_tx", ""),
            }
            if not large_graph:
                ed["transactions"] = attrs.get("transactions", [])
            edges.append(ed)

    # 4. Summary (spec-compliant — no network_statistics)
    summary: Dict[str, Any] = {
        "total_accounts_analyzed":     total_accounts,
        "suspicious_accounts_flagged": len(suspicious_accounts),
        "fraud_rings_detected":        len(fraud_rings),
        "processing_time_seconds":     round(processing_time, 3),
    }

    response: Dict[str, Any] = {
        "suspicious_accounts": suspicious_accounts,
        "fraud_rings":         fraud_rings,
        "summary":             summary,
    }
    if detail:
        response["graph"] = {"nodes": nodes, "edges": edges}
        if parse_stats:
            response["parse_stats"] = parse_stats

    log.info(
        "Format complete: %d suspicious accounts, %d fraud rings",
        len(suspicious_accounts),
        len(fraud_rings),
    )
    return response
