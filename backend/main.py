"""
spendsense — spidey sense, but for your money.

Not a tracker. An analyst.
Upload transactions (CSV, screenshot, manual) → ask questions → get answers.

Run: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import pdfplumber
import json
import base64
import uuid
from datetime import datetime, date
from typing import Optional

import anthropic
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline.extractor import (
    extract_regex, extract_llm, merge_results,
    normalize_merchant, parse_csv_transactions,
    compute_dedup_key,
)
from agent.analyst import ask_agent, build_analysis

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="spendsense", version="2.0.0", description="spidey sense, but for your money")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
transactions: list[dict] = []      # all normalized transactions
seen_dedup_keys: set[str] = set()  # for duplicate detection
# Initialize client — handle missing API key gracefully
try:
    client = anthropic.Anthropic()
except Exception:
    client = None


def check_api_available():
    """Check if the Anthropic client is configured."""
    if client is None:
        raise HTTPException(
            503,
            detail={
                "error": "api_not_configured",
                "message": "ANTHROPIC_API_KEY is not set. Set it with: export ANTHROPIC_API_KEY='sk-ant-...'",
            }
        )


def handle_api_error(e: Exception) -> dict:
    """
    Parse Anthropic API errors into user-friendly messages.
    Handles: rate limits, credit exhaustion, auth failures, overload.
    """
    error_str = str(e).lower()
    error_type = type(e).__name__

    if "credit" in error_str or "billing" in error_str or "402" in error_str or "insufficient" in error_str:
        return {
            "error": "credits_exhausted",
            "message": "Your Anthropic API credits have run out. Add more at console.anthropic.com/settings/plans",
            "fallback": True,
        }

    if "rate" in error_str or "429" in error_str or "too many" in error_str:
        return {
            "error": "rate_limited",
            "message": "Too many requests — wait a minute and try again.",
            "fallback": True,
        }

    if "auth" in error_str or "401" in error_str or "invalid.*key" in error_str or "permission" in error_str:
        return {
            "error": "auth_failed",
            "message": "Your API key is invalid or expired. Check it at console.anthropic.com/settings/keys",
            "fallback": False,
        }

    if "overloaded" in error_str or "529" in error_str or "503" in error_str:
        return {
            "error": "api_overloaded",
            "message": "Anthropic API is temporarily overloaded. Try again in a few seconds.",
            "fallback": True,
        }

    return {
        "error": "api_error",
        "message": f"API call failed: {error_type} — {str(e)[:200]}",
        "fallback": True,
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ManualEntry(BaseModel):
    merchant: str
    amount: float
    category: str = "other"
    date: Optional[str] = None
    notes: Optional[str] = None


class AskRequest(BaseModel):
    question: str


class BulkManualEntry(BaseModel):
    entries: list[ManualEntry]


# ---------------------------------------------------------------------------
# INGESTION ROUTES
# ---------------------------------------------------------------------------

@app.get("/")
def health():
    api_status = "configured" if client else "not_configured"
    return {
        "status": "ok",
        "transactions": len(transactions),
        "version": "2.0",
        "api_status": api_status,
        "note": None if client else "Set ANTHROPIC_API_KEY for AI features. CSV import, manual entry, and dashboard work without it.",
    }


@app.post("/ingest/csv")
async def ingest_csv(file: UploadFile = File(...)):
    """
    Upload a bank/credit card CSV statement.
    Auto-detects columns, normalizes merchants, categorizes, deduplicates.
    """
    content = (await file.read()).decode("utf-8", errors="replace")
    parsed = parse_csv_transactions(content, client=client)

    added = 0
    skipped = 0
    for t in parsed:
        key = compute_dedup_key(t["merchant"], t["amount"], t["date"])
        if key in seen_dedup_keys:
            skipped += 1
            continue
        seen_dedup_keys.add(key)

        t["id"] = str(uuid.uuid4())[:8]
        t["created_at"] = datetime.utcnow().isoformat()
        t["idempotency_key"] = key
        transactions.append(t)
        added += 1

    return {
        "imported": added,
        "duplicates_skipped": skipped,
        "total_in_system": len(transactions),
        "sample": parsed[:3] if parsed else [],
    }


@app.post("/ingest/screenshot")
async def ingest_screenshot(file: UploadFile = File(...)):
    """
    Upload a screenshot of a bank notification, payment app, or receipt.
    Hybrid extraction: regex first, LLM fills gaps.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Must be an image file")
    
    check_api_available() 

    image_bytes = await file.read()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    media_type = file.content_type or "image/jpeg"

    # For screenshots, we need vision — go straight to LLM
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system="""Extract transaction from this image. Return ONLY JSON:
{"merchant":"name","amount":14.03,"date":"YYYY-MM-DD","currency":"USD",
"items":[{"name":"x","price":4.99}],"payment_method":"or null",
"category":"food|transport|shopping|groceries|entertainment|health|utilities|subscriptions|other"}""",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "Parse this receipt/notification."},
                ],
            }],
        )
        raw = resp.content[0].text
        parsed = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
    except anthropic.APIStatusError as e:
        err = handle_api_error(e)
        raise HTTPException(e.status_code, detail=err)
    except anthropic.APIConnectionError:
        raise HTTPException(503, detail={"error": "connection_failed", "message": "Cannot reach the Anthropic API. Check your internet connection."})
    except json.JSONDecodeError:
        raise HTTPException(502, detail={"error": "parse_failed", "message": "AI returned invalid JSON. Try uploading a clearer image."})
    except Exception as e:
        err = handle_api_error(e)
        raise HTTPException(502, detail=err)

    # Normalize merchant
    merchant_raw = parsed.get("merchant", "Unknown")
    merchant_clean, category = normalize_merchant(merchant_raw)

    t = {
        "id": str(uuid.uuid4())[:8],
        "merchant": merchant_clean,
        "merchant_raw": merchant_raw,
        "amount": round(parsed.get("amount", 0), 2),
        "date": parsed.get("date", date.today().isoformat()),
        "category": parsed.get("category") or category,
        "currency": parsed.get("currency", "USD"),
        "items": parsed.get("items"),
        "payment_method": parsed.get("payment_method"),
        "source": "screenshot",
        "extraction_method": "llm",
        "confidence": 0.85,
        "notes": None,
        "created_at": datetime.utcnow().isoformat(),
    }

    # Dedup
    key = compute_dedup_key(t["merchant"], t["amount"], t["date"])
    if key in seen_dedup_keys:
        return {"status": "duplicate", "transaction": t}
    seen_dedup_keys.add(key)
    t["idempotency_key"] = key

    transactions.append(t)
    return {"status": "added", "transaction": t}


@app.post("/ingest/manual")
def ingest_manual(entry: ManualEntry):
    """Quick manual entry — merchant + amount + category."""
    merchant_clean, auto_cat = normalize_merchant(entry.merchant)

    t = {
        "id": str(uuid.uuid4())[:8],
        "merchant": merchant_clean,
        "merchant_raw": entry.merchant,
        "amount": round(entry.amount, 2),
        "date": entry.date or date.today().isoformat(),
        "category": entry.category if entry.category != "other" else auto_cat,
        "currency": "USD",
        "items": None,
        "payment_method": None,
        "source": "manual",
        "extraction_method": "manual",
        "confidence": 1.0,
        "notes": entry.notes,
        "created_at": datetime.utcnow().isoformat(),
    }
    key = compute_dedup_key(t["merchant"], t["amount"], t["date"])
    t["idempotency_key"] = key
    seen_dedup_keys.add(key)
    transactions.append(t)
    return t


@app.post("/ingest/manual/bulk")
def ingest_bulk(data: BulkManualEntry):
    """Batch manual entry."""
    results = []
    for entry in data.entries:
        results.append(ingest_manual(entry))
    return {"imported": len(results), "transactions": results}


# ---------------------------------------------------------------------------
# AGENT ROUTES — The actual value
# ---------------------------------------------------------------------------

@app.post("/ask")
def ask_question(req: AskRequest):
    """
    Ask the financial insight agent a question about your spending.

    If the API key is missing or credits are exhausted, falls back to
    template-based answers using only pandas analysis (no LLM).
    """
    if not transactions:
        return {
            "answer": "No transactions loaded yet. Upload a CSV or add some entries first!",
            "context": {},
        }

    if client:
        try:
            return ask_agent(req.question, transactions, client=client)
        except Exception as e:
            err = handle_api_error(e)
            result = ask_agent(req.question, transactions, client=None)
            result["api_warning"] = err["message"]
            result["answer"] = f"[Answered without AI — {err['message']}]\n\n{result['answer']}"
            return result
    else:
        result = ask_agent(req.question, transactions, client=None)
        result["api_warning"] = "No API key configured. Using basic analysis only. Set ANTHROPIC_API_KEY for AI-powered insights."
        return result

@app.get("/analysis")
def get_analysis():
    """
    Get the full pre-computed analysis context without asking a question.
    Useful for dashboards and charts.
    """
    if not transactions:
        return {"error": "No transactions loaded"}

    ctx = build_analysis(transactions)
    return {
        "total_spent": ctx.total_spent,
        "transaction_count": ctx.transaction_count,
        "date_range": ctx.date_range,
        "daily_average": ctx.daily_average,
        "by_category": ctx.by_category,
        "category_percentages": ctx.category_percentages,
        "top_merchants": ctx.top_merchants[:15],
        "monthly_trend": ctx.monthly_trend,
        "weekly_trend": ctx.weekly_trend,
        "anomalies": ctx.anomalies,
        "recurring": ctx.recurring,
        "forecast_next_month": ctx.forecast_next_month,
        "biggest_single": ctx.biggest_single,
    }


# ---------------------------------------------------------------------------
# DATA ROUTES — View/manage transactions
# ---------------------------------------------------------------------------

@app.get("/transactions")
def list_transactions(
    category: Optional[str] = None,
    merchant: Optional[str] = None,
    limit: int = Query(100, le=500),
):
    """List transactions with optional filters."""
    result = sorted(transactions, key=lambda x: x.get("date", ""), reverse=True)
    if category:
        result = [t for t in result if t.get("category") == category]
    if merchant:
        result = [t for t in result if merchant.lower() in t.get("merchant", "").lower()]
    return result[:limit]


@app.get("/transactions/summary")
def transaction_summary():
    """Quick summary: count by source and category."""
    by_source = {}
    by_category = {}
    for t in transactions:
        src = t.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
        cat = t.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": len(transactions),
        "by_source": by_source,
        "by_category": by_category,
    }


@app.delete("/transactions/{txn_id}")
def delete_transaction(txn_id: str):
    """Delete a transaction by ID."""
    global transactions
    before = len(transactions)
    transactions = [t for t in transactions if t.get("id") != txn_id]
    if len(transactions) == before:
        raise HTTPException(404, "Transaction not found")
    return {"deleted": txn_id}


@app.delete("/transactions")
def clear_all():
    """Clear all transactions."""
    transactions.clear()
    seen_dedup_keys.clear()
    return {"cleared": True}
