"""
config.py – Centralised configuration via environment variables.
All tunable thresholds live here so nothing is scattered across modules.
"""
import os


# ── File limits ────────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_ROWS: int = int(os.getenv("MAX_ROWS", "10000"))

# ── Cycle detection ────────────────────────────────────────────────────────────
CYCLE_MIN_LEN: int = 3
CYCLE_MAX_LEN: int = 5
MAX_CYCLES: int = int(os.getenv("MAX_CYCLES", "5000"))
CYCLE_TIMEOUT_SECONDS: float = float(os.getenv("CYCLE_TIMEOUT_SECONDS", "3.0"))

# ── Smurfing detection ─────────────────────────────────────────────────────────
FAN_THRESHOLD: int = int(os.getenv("FAN_THRESHOLD", "10"))
SMURF_WINDOW_HOURS: int = int(os.getenv("SMURF_WINDOW_HOURS", "72"))

# Semantic false-positive exclusions (more precise than percentile-based):
#
# MERCHANT detection (fan-in exclusion):
#   Retail merchants receive payments of highly VARIABLE amounts (different products).
#   Legitimate smurfing aggregators receive UNIFORM small amounts from many senders.
#   Coefficient of variation (std/mean) of received amounts > this threshold → merchant.
MERCHANT_AMOUNT_CV_THRESHOLD: float = float(os.getenv("MERCHANT_AMOUNT_CV_THRESHOLD", "0.15"))

# PAYROLL/BATCH detection (fan-out exclusion):
#   Payroll systems disburse all salaries simultaneously (batch at same timestamp).
#   Smurfing dispersers send funds spread out over time to avoid detection.
#   If ALL outgoing transactions from a sender span < this many seconds → payroll batch.
PAYROLL_BATCH_SECONDS: float = float(os.getenv("PAYROLL_BATCH_SECONDS", "60.0"))

# ── Shell detection ────────────────────────────────────────────────────────────
SHELL_MAX_TX: int = int(os.getenv("SHELL_MAX_TX", "3"))
SHELL_MIN_CHAIN: int = 3
SHELL_MAX_CHAIN: int = int(os.getenv("SHELL_MAX_CHAIN", "6"))
MAX_SHELL_CHAINS: int = int(os.getenv("MAX_SHELL_CHAINS", "1000"))

# ── Scoring ────────────────────────────────────────────────────────────────────
# Base pattern contribution scores
SCORE_CYCLE_3: float = 35.0
SCORE_CYCLE_4: float = 30.0
SCORE_CYCLE_5: float = 25.0
SCORE_FAN_IN: float = 28.0
SCORE_FAN_OUT: float = 28.0
SCORE_SHELL: float = 22.0
SCORE_HIGH_VELOCITY: float = 15.0
SCORE_MULTI_RING_BONUS: float = 10.0   # bonus per extra ring membership beyond 1
SCORE_CENTRALITY_MAX: float = 10.0     # max bonus from betweenness centrality
HIGH_VELOCITY_TX_PER_DAY: float = float(os.getenv("HIGH_VELOCITY_TX_PER_DAY", "5.0"))

# New pattern scores
SCORE_AMOUNT_ANOMALY: float = 20.0
SCORE_ROUND_TRIP: float = 20.0
SCORE_RAPID_MOVEMENT: float = 20.0
SCORE_STRUCTURING: float = 15.0

# Minimum suspicion score for an account to appear in suspicious_accounts output.
# Accounts below this threshold are not flagged (reduces false-positive count).
MIN_SUSPICION_SCORE: float = float(os.getenv("MIN_SUSPICION_SCORE", "20.0"))

# ── Amount anomaly detection ───────────────────────────────────────────────────
AMOUNT_ANOMALY_STDDEV: float = float(os.getenv("AMOUNT_ANOMALY_STDDEV", "3.0"))

# ── Bi-directional / round-trip detection ──────────────────────────────────────
ROUND_TRIP_AMOUNT_TOLERANCE: float = float(os.getenv("ROUND_TRIP_AMOUNT_TOLERANCE", "0.2"))

# ── Rapid movement detection ──────────────────────────────────────────────────
RAPID_MOVEMENT_MINUTES: float = float(os.getenv("RAPID_MOVEMENT_MINUTES", "30.0"))

# ── Amount structuring detection ───────────────────────────────────────────────
STRUCTURING_THRESHOLD: float = float(os.getenv("STRUCTURING_THRESHOLD", "10000.0"))
STRUCTURING_MARGIN: float = float(os.getenv("STRUCTURING_MARGIN", "0.15"))
STRUCTURING_MIN_TX: int = int(os.getenv("STRUCTURING_MIN_TX", "3"))

# ── Risk weights for fraud_rings ───────────────────────────────────────────────
RING_RISK: dict = {
    "cycle_length_3": 95.0,
    "cycle_length_4": 88.0,
    "cycle_length_5": 80.0,
    "fan_in":  75.0,
    "fan_out": 75.0,
    "shell_chain": 70.0,
    "round_trip": 82.0,
}
