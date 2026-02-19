
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import MAX_FILE_SIZE_BYTES
from .parser import parse_csv
from .graph_builder import build_graph
from .cycle_detector import detect_cycles
from .smurf_detector import detect_smurfing
from .shell_detector import detect_shell_networks
from .bidirectional_detector import detect_round_trips
from .anomaly_detector import detect_amount_anomalies
from .rapid_movement_detector import detect_rapid_movements
from .structuring_detector import detect_structuring
from .scoring import calculate_scores
from .formatter import format_output
from .utils import assign_ring_ids

__version__ = "2.0.0"


# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s │ %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Financial Forensics Engine v%s starting up", __version__)
    yield
    log.info("Financial Forensics Engine shutting down")


# App
_raw_origins = os.getenv("CORS_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",")]
_credentials_ok = ALLOWED_ORIGINS != ["*"]

app = FastAPI(
    title="Financial Forensics Engine",
    description="Detect money-muling networks through graph analysis",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=_credentials_ok,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request-ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Routes
@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok", "service": "Financial Forensics Engine", "version": __version__}


@app.get("/health")
def health():
    """Liveness / readiness probe."""
    return {
        "status": "healthy",
        "version": __version__,
        "max_file_size_mb": MAX_FILE_SIZE_BYTES // (1024 * 1024),
    }


@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    detail: bool = Query(
        default=False,
        description="When true, include graph and parse_stats in the response (used by the frontend).",
    ),
):
    """
    Upload a CSV of financial transactions and receive a forensic analysis.

    Expected CSV columns: transaction_id, sender_id, receiver_id, amount, timestamp
    """
    # basic validation 
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
        )

    start_time = time.perf_counter()

    #  Parse 
    try:
        df, parse_stats = parse_csv(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if parse_stats.get("warnings"):
        log.warning("Parse warnings for %s: %s", file.filename, parse_stats["warnings"])

    total_accounts = len(
        set(df["sender_id"].tolist()) | set(df["receiver_id"].tolist())
    )
    log.info(
        "Parsed %s: %d valid rows, %d accounts",
        file.filename,
        parse_stats.get("valid_rows", len(df)),
        total_accounts,
    )

    #  Build graph
    # Always skip per-edge transaction lists — they are only used for temporal
    # profiles and graph payload "transactions" arrays, both of which are now
    # skipped for large graphs.  Saves ~1-2s on slow CPUs (Render free tier).
    t0 = time.perf_counter()
    G = build_graph(df, include_transactions=False)
    log.info("build_graph: %.3fs", time.perf_counter() - t0)

    # ── Run all detectors concurrently ────────────────────────────────────────
    # All detectors are read-only on G / df and fully independent of each other.
    # asyncio.to_thread dispatches each to the default ThreadPoolExecutor so they
    # overlap on I/O waits and GIL-releasing pandas/numpy internals.
    t0 = time.perf_counter()
    (
        cycle_rings,
        smurf_rings,
        shell_rings,
        roundtrip_rings,
        anomaly_accounts,
        rapid_accounts,
        structuring_accounts,
    ) = await asyncio.gather(
        asyncio.to_thread(detect_cycles,           G),
        asyncio.to_thread(detect_smurfing,         df),
        asyncio.to_thread(detect_shell_networks,   G),
        asyncio.to_thread(detect_round_trips,      G),
        asyncio.to_thread(detect_amount_anomalies, df),
        asyncio.to_thread(detect_rapid_movements,  df),
        asyncio.to_thread(detect_structuring,      df),
    )
    log.info(
        "all detectors (parallel): %.3fs → cycles=%d smurf=%d shell=%d rt=%d",
        time.perf_counter() - t0,
        len(cycle_rings), len(smurf_rings), len(shell_rings), len(roundtrip_rings),
    )

    # Assign ring IDs 
    all_rings = assign_ring_ids(
        cycle_rings, smurf_rings, shell_rings, roundtrip_rings, merge=True
    )

    # Score accounts (with all enrichments)
    account_scores = calculate_scores(
        all_rings, df, G,
        anomaly_accounts=anomaly_accounts,
        rapid_accounts=rapid_accounts,
        structuring_accounts=structuring_accounts,
    )

    # Format & return
    elapsed = time.perf_counter() - start_time
    result = format_output(
        all_rings, account_scores, G, elapsed, total_accounts, parse_stats, detail=detail
    )

    log.info(
        "Analysis complete for %s in %.2fs: %d rings, %d flagged accounts",
        file.filename,
        elapsed,
        len(all_rings),
        result["summary"]["suspicious_accounts_flagged"],
    )

    return JSONResponse(content=result)
