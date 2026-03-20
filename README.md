# spendsense

**spidey sense, but for your money.**

SpendSense is an AI-powered financial analysis system that transforms raw transaction data into actionable insights using a hybrid pipeline (rule-based extraction + statistical analysis + LLM reasoning).

Upload your bank statement, ask "where am I overspending?" — get specific, actionable answers with dollar amounts. Not a tracker. An analyst.

## What It Does

Most expense apps track spending. spendsense **analyzes** it. Upload your data however you want (CSV, screenshot, manual), and the agent answers questions like:

- "Where am I overspending?"
- "How can I save $200 next month?"
- "What are my subscriptions really costing me?"
- "Any unusual charges this month?"
- "What will I spend next month?"

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │           INGESTION LAYER                │
                    │                                          │
   CSV Statement ───┤  Auto-detect columns                     │
                    │  ↓                                       │
   Screenshot ──────┤  Hybrid Extraction (Regex ∥ LLM)         │
                    │  ↓                                       │
   Manual Entry ────┤  Merchant Normalization (100% accuracy)  │
                    │  ↓                                       │
                    │  Deduplication (SHA-256 hash)             │
                    └──────────────┬──────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────────────┐
                    │         ANALYSIS ENGINE (pandas)          │
                    │                                          │
                    │  • Category breakdown with %             │
                    │  • Anomaly detection (z-score)           │
                    │  • Recurring charge detection            │
                    │  • Monthly/weekly trends                 │
                    │  • Linear regression forecast            │
                    │  • Top merchant ranking                  │
                    └──────────────┬───────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────────────┐
                    │        INSIGHT AGENT (1 LLM call)        │
                    │                                          │
                    │  Receives: aggregated stats only         │
                    │  Returns: actionable advice with $$$     │
                    │  Never sees raw transaction data         │
                    └──────────────────────────────────────────┘
```

## Key Technical Decisions

**Hybrid extraction pipeline** — Regex handles ~70% of structured fields (amounts, dates, card numbers) for free. LLM fills the remaining ~30% (semantic merchant names, ambiguous categories). Benchmarked at:
- Merchant normalization: **100%** (38/38 bank codes)
- Category auto-assignment: **100%**
- Regex extraction: **100%** across 8 diverse formats

**One LLM call per query** — The agent pre-computes all analytics with pandas (anomalies, trends, forecasts, recurring charges), then sends only aggregated stats to Claude. This keeps costs at ~$0.003/query and never exposes raw financial data to the API.

**Anomaly detection** — Z-score based per category. A $200 grocery trip when your average is $60 gets flagged automatically — your spendsense tingles. No ML model needed — stats work better here because the dataset is small and personal.

**Recurring charge detection** — Identifies subscriptions by finding merchants that appear across 2+ months with consistent amounts (±15% tolerance). Calculates annual cost to show the real impact.

**Spending forecast** — Linear regression on the last 3–6 months of monthly totals. Simple, but honest about what small datasets can support.

## Quick Start

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."

# Run benchmarks (no API key needed)
python -m evaluation.benchmark

# Start the server
uvicorn main:app --reload --port 8000
```

## API

### Ingestion
| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/ingest/csv` | POST | Upload bank CSV → auto-parse, normalize, categorize |
| `/ingest/screenshot` | POST | Upload receipt/notification image → vision extraction |
| `/ingest/manual` | POST | Quick add: merchant + amount + category |
| `/ingest/manual/bulk` | POST | Batch manual entries |

### Agent
| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/ask` | POST | Ask any question about your spending → AI insight |
| `/analysis` | GET | Full pre-computed analytics (for dashboards) |

### Data
| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/transactions` | GET | List all (filter by ?category= or ?merchant=) |
| `/transactions/summary` | GET | Count by source and category |
| `/transactions/{id}` | DELETE | Remove one |
| `/transactions` | DELETE | Clear all |

## Example Session

```bash
# 1. Upload your Chase statement
curl -X POST http://localhost:8000/ingest/csv -F "file=@chase_march.csv"
# → {"imported": 47, "duplicates_skipped": 0}

# 2. Ask a question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Where am I overspending?"}'
# → {"answer": "Your biggest category is food at $487.32 (34% of spending).
#    DoorDash alone is $156 across 8 orders — that's $19.50/order average.
#    Cutting to 4 orders/month saves ~$78. Your Uber Eats + DoorDash combined
#    is $234/mo — consider meal prepping 2 days/week to halve that.", ...}

# 3. Get dashboard data
curl http://localhost:8000/analysis
# → {anomalies, recurring, forecast, trends, ...}
```

## Project Structure

```
spendsense/
├── backend/
│   ├── main.py                  # FastAPI app — ingestion + agent routes
│   ├── pipeline/
│   │   └── extractor.py         # Hybrid extraction: regex + LLM + normalization
│   ├── agent/
│   │   └── analyst.py           # Financial insight agent with pandas analytics
│   ├── evaluation/
│   │   └── benchmark.py         # Accuracy benchmarks with 38 test cases
│   └── requirements.txt
└── README.md
```

## Tech Stack

- **Backend**: Python, FastAPI, pandas
- **AI**: Anthropic Claude (Sonnet) — vision for screenshots, text for insights
- **Analysis**: pandas for aggregation, z-score anomaly detection, linear regression forecasting
- **Extraction**: Hybrid regex + LLM pipeline with 100% benchmark accuracy

## What I'd Add Next

- [ ] SQLite persistence (currently in-memory)
- [ ] SwiftUI iOS app with charts
- [ ] Budget goal tracking ("I want to spend <$400 on food")
- [ ] Multi-currency normalization
- [ ] Plaid integration for auto-import
- [ ] Embeddings-based merchant clustering for smarter categorization
