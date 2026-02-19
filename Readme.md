# Financial Forensics Engine

> A production-grade web application that detects money muling networks in financial transaction data through graph analysis, statistical anomaly detection, and interactive visualization.

**Live Demo:** _[https://financial-forensics-engine.vercel.app/]_  
**GitHub:** [shubhanshu2006/Financial-Forensics-Engine](https://github.com/shubhanshu2006/Financial-Forensics-Engine)

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [System Architecture](#system-architecture)
- [Algorithm Approach & Complexity Analysis](#algorithm-approach--complexity-analysis)
- [Suspicion Score Methodology](#suspicion-score-methodology)
- [Installation & Setup](#installation--setup)
- [Usage Instructions](#usage-instructions)
- [JSON Output Format](#json-output-format)
- [Project Structure](#project-structure)
- [Performance Analysis](#performance-analysis)
- [Known Limitations](#known-limitations)
- [Team Members](#team-members)

---

## Tech Stack

| Layer      | Technology                    | Purpose                                              |
| ---------- | ----------------------------- | ---------------------------------------------------- |
| Backend    | **Python 3.13** / **FastAPI** | REST API, CSV parsing, analysis orchestration        |
| Graph      | **NetworkX 3.x**              | Directed graph, cycle detection, Louvain communities |
| Data       | **Pandas 3.x** / **NumPy**    | Vectorized transaction processing & statistics       |
| Validation | **Pydantic v2**               | Request/response schema validation                   |
| Frontend   | **React 18** / **Vite 5**     | Single-page application, drag-and-drop upload        |
| Viz        | **react-force-graph-2d**      | Force-directed interactive graph rendering           |
| HTTP       | **Axios**                     | API communication with 60s timeout handling          |

---

## System Architecture

```
                          ┌──────────────────────────────────┐
               CSV Upload │       FastAPI Backend v2.0       │
  Browser  ─────────────> │       POST /analyze              │
  (React)                 │                                  │
                          └──────┬───────────────────────────┘
                                 │
       ┌─────────────────────────┼─────────────────────────┐
       │          Step 1         │                          │
       │   ┌─────────────────┐   │                          │
       │   │   parser.py     │   │   CSV → Validated DF     │
       │   └────────┬────────┘   │                          │
       │            │            │                          │
       │   Step 2   ▼            │                          │
       │   ┌─────────────────┐   │                          │
       │   │ graph_builder.py│   │   DF → NetworkX DiGraph  │
       │   └────────┬────────┘   │                          │
       │            │            │                          │
       │   Step 3   ▼ Core Detection (×4)                   │
       │   ┌─────────┬──────────┬──────────┬────────────┐   │
       │   │ cycle_  │ smurf_   │ shell_   │bidirection-│   │
       │   │detector │detector  │detector  │al_detector │   │
       │   │(Johnson)│(2-ptr    │(iter DFS)│(round-trip)│   │
       │   │         │ window)  │          │            │   │
       │   └────┬────┴────┬─────┴────┬─────┴─────┬──────┘   │
       │        │         │          │           │          │
       │   Step 4   ▼ Enrichment Detectors (×3)             │
       │   ┌──────────────┬────────────────┬─────────────┐  │
       │   │  anomaly_    │ rapid_movement │ structuring_ │  │
       │   │  detector    │ _detector      │ _detector    │  │
       │   │  (σ outlier) │ (dwell time)   │ (sub-$10K)   │  │
       │   └──────┬───────┴───────┬────────┴──────┬──────┘  │
       │          │               │               │         │
       │   Step 5 ▼                                         │
       │   ┌──────────────────────────────────────────┐     │
       │   │  utils.py → Ring merging + ID assignment │     │
       │   └──────┬───────────────────────────────────┘     │
       │          │                                         │
       │   Step 6 ▼                                         │
       │   ┌──────────────────────────────────────────┐     │
       │   │  scoring.py → Multi-factor scoring +     │     │
       │   │               risk explanations          │     │
       │   └──────┬───────────────────────────────────┘     │
       │          │                                         │
       │   Step 7 ▼                                         │
       │   ┌──────────────────────────────────────────┐     │
       │   │  formatter.py → JSON response builder    │     │
       │   │  (3 mandatory keys; graph + parse_stats  │     │
       │   │   added in ?detail=true mode)            │     │
       │   └──────────────────────────────────────────┘     │
       └────────────────────────────────────────────────────┘
```

### Pipeline Steps (7-Stage)

| Step | Module                    | Action                                                                              |
| ---- | ------------------------- | ----------------------------------------------------------------------------------- |
| 1    | `parser.py`               | Decode CSV (UTF-8/latin-1), validate columns, clean amounts/timestamps, dedup       |
| 2    | `graph_builder.py`        | Build directed weighted graph with vectorised Pandas groupby node/edge stats        |
| 3    | Core detectors (×4)       | Cycle detection, fan-in/fan-out, shell chains, bi-directional round-trip flows      |
| 4    | Enrichment detectors (×3) | Amount anomaly (3σ), rapid movement (dwell time), structuring (sub-$10K)            |
| 5    | `utils.py`                | Merge overlapping rings (≥50% member overlap), assign RING_001, RING_002, ...       |
| 6    | `scoring.py`              | Multi-factor 0–100 scoring + natural language risk explanations                     |
| 7    | `formatter.py`            | Clean JSON with 3 mandatory keys; `graph` + `parse_stats` added when `?detail=true` |

---

## Algorithm Approach & Complexity Analysis

### 1. Circular Fund Routing — Cycle Detection

**What it detects:** Money flowing in loops (A → B → C → A) to obscure its criminal origin.

**Algorithm:** Johnson's algorithm via NetworkX `simple_cycles()`:

- Length filter: 3 ≤ length ≤ 5
- Canonical deduplication: each cycle is rotated to its lexicographically smallest node, so [A,B,C] and [B,C,A] are recognised as the same ring
- **SCC pre-filter** — `nx.strongly_connected_components()` runs first (O(V+E)); `simple_cycles()` runs only on the SCC subgraph, eliminating acyclic nodes before enumeration starts. On a 6K-node graph this reduces the search space by ~70%.
- Threading-based timeout (5s default) prevents exponential runtime on dense graphs
- Hard cap: 5,000 cycles

**Complexity:** O(V+E) for SCC, then O((V' + E') × C) on the reduced subgraph where V' << V. Bounded by timeout and hard cap.

---

### 2. Smurfing — Fan-in / Fan-out Detection

**What it detects:** Many small deposits aggregated into one account (fan-in) or one account dispersing to many (fan-out) — classic structuring to stay below reporting thresholds.

**Algorithm:**

1. Group transactions by target (fan-in) or source (fan-out)
2. Sort each group by timestamp — O(n log n)
3. Two-pointer sliding window (72-hour window) counts unique counterparties via a frequency dict
4. Trigger: 10+ unique counterparties in any window

**False positive control (semantic, not percentile-based):**

- **Merchant exclusion (fan-in):** For each potential hub, compute the coefficient of variation (CV = std/mean) of all received amounts. CV > 0.15 → variable purchase amounts → legitimate merchant (e.g., Amazon) → excluded. Smurfing aggregators receive uniform small amounts (CV ≈ 0).
- **Payroll exclusion (fan-out):** Check if all outgoing transactions from a sender occur within a 60-second span. If yes → batch payroll disbursement → excluded. Smurfing dispersers spread sends over hours.

**Complexity:** O(n log n) per group (sort-dominated). The two-pointer scan is O(n).

---

### 3. Layered Shell Networks — Chain Detection

**What it detects:** Chains of 3+ hops through intermediate "shell" accounts with ≤3 total transactions, used to add distance between criminal source and destination.

**Algorithm:**

1. **SCC exclusion** — Nodes inside strongly-connected components (i.e., cycle participants) are never classified as shells, preventing cycle nodes from being misidentified as pass-throughs.
2. Shell criteria: `tx_count ≤ 3 AND in_degree > 0 AND out_degree > 0 AND NOT in SCC of size > 1` (true pass-through)
3. Iterative DFS (stack-based, no recursion) from every node that has at least one shell successor
4. Valid chain: `source → [SHELL_1, SHELL_2, ...] → destination` with ≥3 total hops
5. **`members` = only the shell intermediaries** — source and destination are excluded from ring membership (Option A: consistent precision)
6. Depth limit: 6 hops max. Hard cap: 1,000 chains.

**Complexity:** O(V × d^b) where d = average shell out-degree, b = max depth. Bounded by hard cap.

---

### 4. Bi-directional Flow — Round-trip Detection

**What it detects:** Account pairs where A→B and B→A both exist with similar total amounts — artificial round-tripping to create fake transaction volume.

**Algorithm:**

1. For every edge A→B, check if reverse edge B→A exists
2. Compute similarity: `1 - |amount_AB - amount_BA| / max(amount_AB, amount_BA)`
3. Flag if similarity ≥ 80% (configurable)
4. Deduplicate via sorted tuple keys

**Complexity:** O(E) — single pass over all edges.

---

### 5. Amount Anomaly Detection

**What it detects:** Transactions that deviate more than 3σ from an account's mean — sudden large deposits that break normal behaviour.

**Algorithm:**

1. Group transactions by account (sender and receiver separately)
2. For accounts with ≥5 transactions: compute mean and standard deviation
3. Flag if any transaction amount > μ + 3σ

**Complexity:** O(T) where T = total transactions (single aggregation pass).

---

### 6. Rapid Movement Detection

**What it detects:** Accounts that receive and forward funds within minutes — the hallmark of a pass-through mule.

**Algorithm:**

1. Per account: separate incoming and outgoing transactions, sort by timestamp
2. Two-pointer scan: for each incoming tx, find earliest outgoing tx that follows it
3. If dwell time ≤ 30 minutes → flag

**Complexity:** O(n log n) per account (sort-dominated). Two-pointer scan is O(n).

---

### 7. Amount Structuring Detection

**What it detects:** Multiple transactions deliberately kept just below the $10,000 CTR reporting threshold (31 USC § 5324).

**Algorithm:**

1. Define structuring band: $8,500 to $10,000 (15% margin below threshold)
2. Count sent transactions per account falling in the band
3. Flag if ≥3 transactions in band

**Complexity:** O(T) — single pass over all transactions.

---

### Overall Pipeline Complexity

**Total:** O(n log n) + O(V+E) [SCC] + O((V' + E') × C) [cycles on SCC subgraph] + O(V × d^b) [shells] + O(E) + O(T)

In practice, bounded by the cycle detection timeout (5s) and hard caps. Typical processing: **< 0.5s** for 1K rows, **< 10s** for 10K rows.

---

## Suspicion Score Methodology

Each account's suspicion score (0–100) is computed as the sum of weighted factors, capped at 100:

### Pattern Weights (Primary)

| Factor               | Points | Notes                                                                         |
| -------------------- | ------ | ----------------------------------------------------------------------------- |
| Cycle (length 3)     | **35** | All cycle members — shortest cycles hardest to explain legitimately           |
| Cycle (length 4)     | **30** | All cycle members                                                             |
| Cycle (length 5)     | **25** | All cycle members                                                             |
| Fan-in hub only      | **28** | Only the aggregator hub is scored; spokes are ring members but not flagged    |
| Fan-out hub only     | **28** | Only the disperser hub is scored; recipients are ring members but not flagged |
| Shell intermediaries | **22** | Only confirmed pass-through nodes; source/destination excluded from members   |
| Round-trip member    | **20** | Bi-directional symmetric flows                                                |

### Enrichment Bonuses

| Factor                 | Points        | Trigger Condition                                    |
| ---------------------- | ------------- | ---------------------------------------------------- |
| Amount anomaly         | **+20**       | Transaction > 3σ from account mean                   |
| Rapid movement         | **+20**       | Receive-to-forward dwell time ≤ 30 minutes           |
| Amount structuring     | **+15**       | 3+ transactions in $8,500–$10,000 band               |
| High velocity          | **+15**       | Average > 5 transactions/day                         |
| Multi-ring bonus       | **+10/ring**  | Extra 10 points per additional ring beyond the first |
| Betweenness centrality | **up to +10** | Network hub importance (≤500 node graphs only)       |

### Formula

**Score = Σ(pattern weights) + Σ(enrichment bonuses), capped at 100.0**

Scores are sorted descending so the most suspicious accounts appear first.

### Risk Explanations

Every suspicious account receives a **natural language risk explanation** combining all applicable findings:

> _"Participates in a 3-node circular fund routing cycle. Receives and forwards funds within minutes (pass-through). Member of RING_001. Fastest pass-through: 4.0 min."_

> **Note on confidence scores:** Confidence scores were removed from the API response. Fraud rings contain only `ring_id`, `member_accounts`, `pattern_type`, and `risk_score`.

---

## Installation & Setup

### Prerequisites

- Python >= 3.10
- Node.js >= 18
- npm or yarn

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

### Environment Variables (optional)

All defaults are set in `backend/app/config.py`. Override via environment variables:

| Variable                       | Default | Description                                       |
| ------------------------------ | ------- | ------------------------------------------------- |
| `MAX_FILE_SIZE_MB`             | 20      | Max upload file size in MB                        |
| `MAX_ROWS`                     | 10000   | Max transaction rows to process                   |
| `FAN_THRESHOLD`                | 10      | Min unique counterparties for smurf               |
| `SMURF_WINDOW_HOURS`           | 72      | Sliding window duration in hours                  |
| `MERCHANT_AMOUNT_CV_THRESHOLD` | 0.15    | CV threshold above which receiver is a merchant   |
| `PAYROLL_BATCH_SECONDS`        | 60      | Max span (s) for all sends to be treated as batch |
| `CYCLE_TIMEOUT_SECONDS`        | 5       | Cycle detection timeout (SCC subgraph)            |
| `AMOUNT_ANOMALY_STDDEV`        | 3.0     | Std deviation threshold for anomalies             |
| `ROUND_TRIP_AMOUNT_TOLERANCE`  | 0.2     | Max difference ratio for round-trip               |
| `RAPID_MOVEMENT_MINUTES`       | 30      | Dwell time threshold for rapid movement           |
| `STRUCTURING_THRESHOLD`        | 10000   | CTR reporting threshold                           |
| `STRUCTURING_MARGIN`           | 0.15    | Band width below threshold (15%)                  |
| `STRUCTURING_MIN_TX`           | 3       | Min transactions in band to flag                  |
| `CORS_ORIGINS`                 | \*      | Comma-separated allowed origins                   |
| `VITE_API_URL`                 | (empty) | Frontend API base URL for deployment              |

---

## Usage Instructions

1. **Open the web app** at [http://localhost:5173](http://localhost:5173)
2. **Upload a CSV file** via drag-and-drop or click-to-browse
   - Required columns: `transaction_id`, `sender_id`, `receiver_id`, `amount`, `timestamp`
3. **View results** in three tabs:
   - **Network Graph** — Interactive force-directed visualization. Suspicious nodes are larger and color-coded by pattern type (red = cycle, purple = smurf, cyan = shell, yellow = multi-pattern). Click any node for a detail panel showing stats, score, and risk explanation.
   - **Fraud Rings** — Table showing each ring with Ring ID, Pattern Type, Member Count, Risk Score, and Member Account IDs.
   - **Suspicious Accounts** — Table of flagged accounts sorted by suspicion score with detected patterns, ring assignment, and risk explanation.
4. **Download JSON report** via the button in the header — includes exactly 3 keys: `suspicious_accounts`, `fraud_rings`, and `summary`. Scores are formatted with `.0` suffix (e.g. `36.0`). Graph data and parse stats are excluded from the download.
5. **Download sample CSV** to test with a pre-built dataset that triggers all detection patterns.

### API Endpoints

| Method | Path       | Description                                |
| ------ | ---------- | ------------------------------------------ |
| GET    | `/`        | Service info (`status`, `version`)         |
| GET    | `/health`  | Health check with version and config info  |
| POST   | `/analyze` | Upload CSV and run full forensics pipeline |

---

## JSON Output Format

### Default response (`POST /analyze`) — 3 keys exactly

```json
{
  "suspicious_accounts": [
    {
      "account_id": "ACC_00123",
      "suspicion_score": 87.5,
      "detected_patterns": ["cycle_length_3", "rapid_movement"],
      "ring_id": "RING_001"
    }
  ],
  "fraud_rings": [
    {
      "ring_id": "RING_001",
      "member_accounts": ["ACC_00123", "ACC_00456", "ACC_00789"],
      "pattern_type": "cycle_length_3",
      "risk_score": 95.0
    }
  ],
  "summary": {
    "total_accounts_analyzed": 500,
    "suspicious_accounts_flagged": 15,
    "fraud_rings_detected": 4,
    "processing_time_seconds": 2.3
  }
}
```

### Detail response (`POST /analyze?detail=true`) — used by frontend

Additionally includes:

- `graph` — `{nodes: [...], edges: [...]}` with community IDs and temporal profiles per suspicious node
- `parse_stats` — `{valid_rows, total_rows, dropped_rows, warnings, ...}`
- `risk_explanation` field on each suspicious account entry

> **Note:** `confidence`, `network_statistics` are **not** included in any response. The downloaded JSON report (from `DownloadButton.jsx`) uses only the 3 mandatory keys and enforces float notation on scores (e.g. `36.0` not `36`).

---

## Project Structure

```
financial-forensics-engine/
├── backend/
│   ├── requirements.txt              # Python dependencies
│   ├── .env.example                  # Environment variable reference (all optional)
│   ├── test_integration.py           # Integration test suite
│   ├── validate.py                   # Standalone output validation script
│   └── app/
│       ├── __init__.py
│       ├── config.py                  # Centralised config, all thresholds
│       ├── models.py                  # Pydantic v2 schemas
│       ├── main.py                    # FastAPI app, /analyze endpoint, middleware
│       ├── parser.py                  # CSV validation (encoding, types, dedup)
│       ├── graph_builder.py           # NetworkX DiGraph with vectorised stats + SCC cache
│       ├── cycle_detector.py          # Johnson's algorithm + timeout + dedup
│       ├── smurf_detector.py          # Two-pointer sliding window fan detection
│       ├── shell_detector.py          # Iterative DFS shell chain finder
│       ├── bidirectional_detector.py  # Round-trip bi-directional flow detection
│       ├── anomaly_detector.py        # Statistical amount anomaly (3σ) detection
│       ├── rapid_movement_detector.py # Dwell-time pass-through detection
│       ├── structuring_detector.py    # Sub-$10K threshold structuring detection
│       ├── scoring.py                 # Multi-factor scoring + risk explanations
│       ├── formatter.py               # JSON builder — 3-key default, ?detail=true adds graph + parse_stats
│       └── utils.py                   # Ring merging (≥50% overlap) + ID assignment
├── frontend/
│   ├── package.json
│   ├── vite.config.js                 # Dev proxy + build config
│   ├── index.html
│   └── src/
│       ├── App.jsx                    # Root component with tabbed results
│       ├── App.css
│       ├── index.css                  # Global CSS variables (dark theme)
│       ├── main.jsx
│       └── components/
│           ├── FileUpload.jsx         # Drag-and-drop CSV upload + sample download
│           ├── FileUpload.css
│           ├── GraphVisualization.jsx  # Force-directed graph with node detail panel
│           ├── GraphVisualization.css
│           ├── SummaryStats.jsx       # Overview stat cards
│           ├── SummaryStats.css
│           ├── SummaryTable.jsx       # Fraud rings + suspicious accounts tables
│           ├── SummaryTable.css
│           ├── DownloadButton.jsx     # JSON report download
│           └── DownloadButton.css
├── render.yaml                        # Render deployment config (backend)
├── PROBLEM_STATEMENT.md               # Hackathon problem statement
├── Features.md                        # Detailed documentation of all detection features
├── .gitignore
└── README.md
```

---

## Performance Analysis

| Metric                 | Target   | Achieved                                                                             |
| ---------------------- | -------- | ------------------------------------------------------------------------------------ |
| Processing Time        | ≤ 30s    | < 0.5s for 1K rows, ~15s for 10K rows locally; ~30s on Render free tier (0.1 vCPU)   |
| Precision              | ≥ 70%    | CV-based merchant exclusion + batch payroll detection + shell intermediary-only rule |
| Recall                 | ≥ 60%    | 7 detection patterns + 4 enrichment bonuses catch multi-layered schemes              |
| False Positive Control | Required | Semantic CV/batch exclusion; shell members = intermediaries only                     |

### Detection Coverage

| Threat Pattern             | Detection Method            | Confidence Level | Score Weight     |
| -------------------------- | --------------------------- | ---------------- | ---------------- |
| Circular routing (A→B→C→A) | Johnson's cycle enumeration | Very High        | 25–35            |
| Fan-in aggregation         | Two-pointer temporal window | High             | 28               |
| Fan-out dispersal          | Two-pointer temporal window | High             | 28               |
| Shell layering             | Iterative DFS chain search  | Medium-High      | 22               |
| Round-trip flows (A↔B)     | Bi-directional edge scan    | High             | 20               |
| Amount anomaly             | Statistical σ deviation     | Medium-High      | 20 (bonus)       |
| Rapid fund movement        | Dwell-time analysis         | High             | 20 (bonus)       |
| Amount structuring (<$10K) | Sub-threshold band scan     | High             | 15 (bonus)       |
| High-velocity mules        | Transaction rate analysis   | Medium           | 15 (bonus)       |
| Multi-pattern hubs         | Cross-ring membership count | Very High        | 10+ (bonus)      |
| Network centrality hubs    | Betweenness centrality      | Medium           | Up to 10 (bonus) |

---

## Known Limitations

1. **In-memory processing** — Entire CSV is loaded into memory. Files exceeding ~100K rows may cause memory pressure.
1. **Single-threaded detectors** — All 7 detectors run sequentially. Parallelising independent detectors could improve throughput further.
1. **Static thresholds** — Fan-in threshold (10), window (72h), CV threshold (0.15), payroll batch window (60s) are configurable but not adaptive to dataset characteristics.
1. **No persistence** — Results are not stored server-side; re-uploading the same file re-runs the full analysis.
1. **Betweenness centrality** skipped for graphs with > 500 nodes due to O(V×E) complexity.
1. **Cycle detection** may time out (5s) on extremely dense SCC subgraphs, returning partial results. The SCC pre-filter significantly reduces the search space before enumeration begins.
1. **Ring merging** uses greedy pairwise comparison; extremely fragmented overlaps could remain unmerged.
1. **Amount anomaly** requires ≥5 transactions per account for meaningful statistics — low-activity accounts are not evaluated.
1. **Average clustering coefficient** skipped for networks with >1,000 nodes to stay within processing budget.

---

## Team Members

| Name             | Role                                                            |
| ---------------- | --------------------------------------------------------------- |
| Ayush Rai        | Frontend, UI Developer & Testing Lead                           |
| Harsh Upadhyay   | Detection Algorithms, Performance Optimization and UX Developer |
| Prerna Negi      | Research, Technical Documentation & Presentation Lead           |
| Shubhanshu Singh | Backend & Integration Lead                                      |

---

_Built for the RIFT 2026 Hackathon — Money Muling Detection Challenge_

_#RIFTHackathon #MoneyMulingDetection #FinancialForensics #FinancialCrime_
