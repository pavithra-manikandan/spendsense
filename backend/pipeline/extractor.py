"""
pipeline/extractor.py — Hybrid extraction pipeline for financial transactions.

Architecture:  Raw Input → Classify → Extract (Regex ∥ LLM) → Normalize → Deduplicate → Store

The hybrid approach runs regex first (fast, free), then LLM only for fields regex missed.
This minimizes API costs while maximizing accuracy.
"""

import re
import json
import hashlib
import logging
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger("spendsense.pipeline")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ExtractionMethod(str, Enum):
    REGEX = "regex"
    LLM = "llm"
    HYBRID = "hybrid"
    MANUAL = "manual"


@dataclass
class Transaction:
    """Normalized transaction — the universal format everything maps to."""
    id: str = ""
    merchant: str = ""
    merchant_raw: str = ""          # original before normalization
    amount: float = 0.0
    date: str = ""                  # YYYY-MM-DD
    category: str = "other"
    currency: str = "USD"
    items: list = field(default_factory=list)
    payment_method: Optional[str] = None
    order_id: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"          # csv | screenshot | email | manual
    extraction_method: str = "manual"
    confidence: float = 1.0
    idempotency_key: str = ""
    created_at: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ExtractionResult:
    """Raw output from an extraction method before normalization."""
    merchant: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    currency: Optional[str] = None
    items: Optional[list] = None
    order_id: Optional[str] = None
    payment_method: Optional[str] = None
    category: Optional[str] = None
    confidence: float = 0.0
    fields_found: int = 0


# ---------------------------------------------------------------------------
# MERCHANT NORMALIZATION — The "wow" piece for resume
# ---------------------------------------------------------------------------
# Maps cryptic bank codes to clean names. In production you'd build this
# from embeddings + a feedback loop. For now, curated rules + fuzzy matching.

MERCHANT_NORM_MAP = {
    # Amazon variants
    "AMZN MKTP":        "Amazon",
    "AMZN MKTPL":       "Amazon",
    "AMZN Mktp US":     "Amazon",
    "AMAZON.COM":        "Amazon",
    "AMZN DIGITAL":      "Amazon Digital",
    "AMAZON PRIME":      "Amazon Prime",
    "PRIME VIDEO":       "Amazon Prime Video",
    # Uber variants
    "UBER   *EATS":      "Uber Eats",
    "UBER *EATS":        "Uber Eats",
    "UBEREATS":          "Uber Eats",
    "UBER   *TRIP":      "Uber",
    "UBER *PENDING":     "Uber",
    "UBER *TRIP":        "Uber",
    # Food delivery
    "DD *DOORDASH":      "DoorDash",
    "DOORDASH DASHER":   "DoorDash",
    "DOORDASH*":         "DoorDash",
    "GRUBHUB*":          "Grubhub",
    "GRUBHUB":           "Grubhub",
    "INSTACART":         "Instacart",
    # POS prefixes (strip these, keep the rest)
    "TST*":              "",     # Toast
    "SQ *":              "",     # Square
    "PP*":               "",     # PayPal merchant
    "PAYPAL *":          "",
    # Tech/subscriptions
    "GOOGLE*YOUTUBE":    "YouTube Premium",
    "GOOGLE *YOUTUBE":   "YouTube Premium",
    "GOOGLE *":          "Google",
    "GOOG*":             "Google",
    "APL* ITUNES":       "Apple",
    "APPLE.COM/BILL":    "Apple",
    "SPOTIFY":           "Spotify",
    "NETFLIX":           "Netflix",
    "HULU":              "Hulu",
    "DISNEY PLUS":       "Disney+",
    "DISNEYPLUS":        "Disney+",
    "ADOBE":             "Adobe",
    "DROPBOX":           "Dropbox",
    "MICROSOFT":         "Microsoft",
    # Grocery
    "WHOLEFDS":          "Whole Foods",
    "WHOLE FOODS":       "Whole Foods",
    "TRADER JOE":        "Trader Joe's",
    "TJ MAXX":           "TJ Maxx",
    "ALDI":              "Aldi",
    "COSTCO WHSE":       "Costco",
    "COSTCO":            "Costco",
    "WALMART":           "Walmart",
    "WAL-MART":          "Walmart",
    "TARGET":            "Target",
    # Fast food / coffee
    "STARBUCKS":         "Starbucks",
    "CHICK-FIL":         "Chick-fil-A",
    "MCDONALD":          "McDonald's",
    "DUNKIN":            "Dunkin'",
    "CHIPOTLE":          "Chipotle",
    # Transport
    "LYFT":              "Lyft",
    "LYFT *RIDE":        "Lyft",
    # Health
    "CVS/PHARMACY":      "CVS",
    "WALGREENS":         "Walgreens",
    "RITE AID":          "Rite Aid",
    # Banking / transfers
    "ZELLE PAYMENT TO":  "",     # Strip prefix, keep recipient
    "ZELLE PAYMENT":     "Zelle",
    "PAYMENT TO CHASE":  "Chase Credit Card Payment",
    "PAYMENT TO":        "",     # Strip prefix for other card payments
    "EVO AT CIRA":       "Evo at Cira Centre",
    "WEALTHFRONT":       "Wealthfront",
    "IRS TREAS":         "IRS",
    "Kiwi Yogurt": "Kiwi Yogurt",

}

# Auto-categorization from normalized merchant
MERCHANT_CATEGORY = {
    "Amazon": "shopping", "Amazon Digital": "shopping", "Amazon Prime": "subscriptions",
    "Amazon Prime Video": "subscriptions",
    "Uber Eats": "food", "DoorDash": "food", "Grubhub": "food", "Instacart": "food",
    "Uber": "transport", "Lyft": "transport",
    "Spotify": "subscriptions", "Netflix": "subscriptions", "Hulu": "subscriptions",
    "Disney+": "subscriptions", "Adobe": "subscriptions", "Dropbox": "subscriptions",
    "YouTube Premium": "subscriptions", "Apple": "subscriptions",
    "Google": "subscriptions", "Microsoft": "subscriptions",
    "Whole Foods": "groceries", "Trader Joe's": "groceries", "Aldi": "groceries",
    "Costco": "groceries", "Walmart": "groceries", "Target": "shopping",
    "Starbucks": "food", "Chick-fil-A": "food", "McDonald's": "food",
    "Dunkin'": "food", "Chipotle": "food",
    "CVS": "health", "Walgreens": "health", "Rite Aid": "health",
    "Chase Credit Card Payment": "other",
    "Zelle": "other",
    "Evo at Cira Centre": "housing",
    "Wealthfront": "savings",
    "IRS": "other", "Kiwi Yogurt" : "food",
}


def normalize_merchant(raw: str) -> tuple[str, str]:
    """
    Normalize a merchant name. Returns (clean_name, category).
    Uses prefix matching against the norm map, then title-case fallback.
    """
    if not raw:
        return "Unknown", "other"

    raw_upper = raw.upper().strip()

    # Try prefix matching (longest match first)
    sorted_keys = sorted(MERCHANT_NORM_MAP.keys(), key=len, reverse=True)
    for pattern in sorted_keys:
        if raw_upper.startswith(pattern.upper()):
            replacement = MERCHANT_NORM_MAP[pattern]
            if replacement == "":
                # Strip prefix, keep the rest
                cleaned = raw[len(pattern):].strip()
                if cleaned:
                    cleaned = cleaned.title()
                    category = MERCHANT_CATEGORY.get(cleaned, "other")
                    return cleaned, category
            else:
                category = MERCHANT_CATEGORY.get(replacement, "other")
                return replacement, category

    # Fallback: title case the raw name
    cleaned = raw.strip()
    if cleaned == cleaned.upper() and len(cleaned) > 3:
        cleaned = cleaned.title()

    # Try category lookup on cleaned name
    for known, cat in MERCHANT_CATEGORY.items():
        if known.lower() in cleaned.lower():
            return cleaned, cat

    return cleaned, "other"


# ---------------------------------------------------------------------------
# REGEX EXTRACTION — Fast, free, handles ~70% of structured data
# ---------------------------------------------------------------------------

AMOUNT_PATTERNS = [
    r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2}))",
    r"(?:total|amount|charge|paid|cost|price)[\s:]*\$?\s?(\d{1,3}(?:,\d{3})*\.\d{2})",
    r"(?:USD|EUR|GBP|CAD|INR)\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2}))",
    r"[£€₹]\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2}))",
]

DATE_PATTERNS = [
    (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", "mdy"),
    (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),
    (r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)\s+(\d{1,2}),?\s+(\d{4})", "month"),
    (r"(\d{1,2})\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*)\s+(\d{4})", "day_month"),
]

ORDER_ID_PATTERNS = [
    r"order\s*(?:#|number|id)[\s:]*([A-Za-z0-9\-]{5,30})",
    r"(?:confirmation|transaction|reference)\s*(?:#|number|id)[\s:]*([A-Za-z0-9\-]{5,30})",
    r"#(\d{3}[\-]\d{3,10}[\-]\d{3,10})",
]

PAYMENT_PATTERNS = [
    r"(?:visa|mastercard|amex|discover)\s*(?:ending\s+in\s+|[*x•.\-]+)(\d{4})",
    r"card\s+(?:ending\s+in\s+|[*x•.\-]+)(\d{4})",
    r"(?:debit|credit)\s+card\s*[*x•.\-]*(\d{4})",
]

CURRENCY_MAP = {
    r"\$|USD": "USD", r"€|EUR": "EUR", r"£|GBP": "GBP",
    r"₹|INR": "INR", r"¥|JPY": "JPY", r"C\$|CAD": "CAD",
}

MERCHANT_PATTERNS = {
    r"amazon\.com|amzn": "Amazon",
    r"uber\s+eats|ubereats": "Uber Eats",
    r"uber\.com|uber\s+(?:trip|ride)": "Uber",
    r"doordash": "DoorDash", r"grubhub": "Grubhub",
    r"netflix": "Netflix", r"spotify": "Spotify",
    r"apple\.com|itunes|app\s+store": "Apple",
    r"walmart": "Walmart", r"target\.com": "Target",
    r"starbucks": "Starbucks", r"venmo": "Venmo",
    r"paypal": "PayPal", r"lyft": "Lyft",
    r"instacart": "Instacart", r"costco": "Costco",
    r"whole\s*foods": "Whole Foods", r"trader\s+joe": "Trader Joe's",
    r"hulu": "Hulu", r"disney": "Disney+", r"adobe": "Adobe",
}


def extract_regex(text: str) -> ExtractionResult:
    """Extract fields using regex. Fast, free, no API calls."""
    result = ExtractionResult()
    text_lower = text.lower()

    # Amount — take the largest (usually total)
    amounts = []
    for pattern in AMOUNT_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            raw = m.group(1) if m.lastindex else m.group()
            try:
                amounts.append(float(raw.replace(",", "").replace("$", "").strip()))
            except ValueError:
                pass
    if amounts:
        result.amount = max(amounts)
        result.fields_found += 1

    # Date
    for pattern, fmt in DATE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                if fmt == "ymd":
                    result.date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                elif fmt == "mdy":
                    result.date = f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
                elif fmt in ("month", "day_month"):
                    from dateutil import parser as dp
                    result.date = dp.parse(m.group()).strftime("%Y-%m-%d")
                result.fields_found += 1
                break
            except Exception:
                continue

    # Merchant
    for pattern, name in MERCHANT_PATTERNS.items():
        if re.search(pattern, text_lower):
            result.merchant = name
            result.fields_found += 1
            break

    # Order ID
    for pattern in ORDER_ID_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result.order_id = m.group(1).strip()
            result.fields_found += 1
            break

    # Payment
    for pattern in PAYMENT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            result.payment_method = f"Card ending {m.group(1)}" if m.lastindex else m.group()
            result.fields_found += 1
            break

    # Currency
    for pattern, cur in CURRENCY_MAP.items():
        if re.search(pattern, text):
            result.currency = cur
            break

    result.confidence = round(min(result.fields_found / 5, 1.0), 2)
    return result


# ---------------------------------------------------------------------------
# LLM EXTRACTION — Handles the ~30% regex misses
# ---------------------------------------------------------------------------

LLM_EXTRACT_PROMPT = """Extract transaction details from this text. Return ONLY valid JSON:
{"merchant":"name","amount":14.03,"date":"YYYY-MM-DD","currency":"USD",
"items":[{"name":"x","price":4.99}],"order_id":"or null","payment_method":"or null",
"category":"food|transport|shopping|groceries|entertainment|health|utilities|subscriptions|other"}
Rules: amount=positive float, date=ISO, items can be []. ONLY JSON, no explanation."""


def extract_llm(text: str, client) -> ExtractionResult:
    """Extract using Claude. Called only when regex is incomplete."""
    result = ExtractionResult()
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=LLM_EXTRACT_PROMPT,
            messages=[{"role": "user", "content": text[:5000]}],
        )
        raw = resp.content[0].text
        parsed = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())

        result.merchant = parsed.get("merchant")
        result.amount = parsed.get("amount")
        result.date = parsed.get("date")
        result.currency = parsed.get("currency", "USD")
        result.items = parsed.get("items")
        result.order_id = parsed.get("order_id")
        result.payment_method = parsed.get("payment_method")
        result.category = parsed.get("category")
        result.fields_found = sum(1 for v in [result.merchant, result.amount, result.date,
                                                result.category, result.payment_method] if v)
        result.confidence = round(min(result.fields_found / 5, 1.0), 2)
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
    return result


# ---------------------------------------------------------------------------
# HYBRID MERGE — Best of both
# ---------------------------------------------------------------------------

def merge_results(regex: ExtractionResult, llm: ExtractionResult) -> ExtractionResult:
    """
    Merge regex + LLM: regex wins for structured fields (amount, date),
    LLM wins for semantic fields (merchant, category).
    """
    merged = ExtractionResult()
    merged.amount = regex.amount or llm.amount
    merged.date = regex.date or llm.date
    merged.merchant = llm.merchant or regex.merchant  # LLM better at merchant names
    merged.category = llm.category or regex.category
    merged.items = llm.items
    merged.order_id = regex.order_id or llm.order_id
    merged.payment_method = regex.payment_method or llm.payment_method
    merged.currency = regex.currency or llm.currency or "USD"

    fields = [merged.merchant, merged.amount, merged.date, merged.category, merged.payment_method]
    merged.fields_found = sum(1 for f in fields if f)
    merged.confidence = round(min(
        0.4 * regex.confidence + 0.6 * llm.confidence + (0.1 if regex.confidence > 0 and llm.confidence > 0 else 0),
        1.0
    ), 2)
    return merged


# ---------------------------------------------------------------------------
# DEDUPLICATION
# ---------------------------------------------------------------------------

def compute_dedup_key(merchant: str, amount: float, date: str) -> str:
    """Hash of (merchant, amount, date) for duplicate detection."""
    raw = f"{merchant.lower().strip()}|{amount:.2f}|{date}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CSV PARSING — The main ingestion path
# ---------------------------------------------------------------------------

def parse_csv_transactions(content: str, client=None) -> list[dict]:
    """
    Parse a bank CSV into normalized transactions.
    Auto-detects column layout using first-row heuristics.
    Normalizes merchants and categorizes in batch.
    """
    import csv, io

    reader = csv.DictReader(io.StringIO(content))
    rows = [dict(r) for i, r in enumerate(reader) if i < 500]
    if not rows:
        return []

    columns = list(rows[0].keys())
    col_lower = {c: c.lower().strip() for c in columns}

    # Auto-detect columns
    date_col = _find_col(col_lower, ["date", "trans date", "transaction date", "posted", "posting date"])
    merchant_col = _find_col(col_lower, ["description", "merchant", "name", "payee", "memo", "transaction"])
    amount_col = _find_col(col_lower, ["amount", "debit", "charge", "total"])
    credit_col = _find_col(col_lower, ["credit", "payment", "deposit"])

    if not merchant_col:
        merchant_col = columns[1] if len(columns) > 1 else columns[0]
    if not amount_col:
        amount_col = columns[-1]

    transactions = []
    for row in rows:
        # Parse amount
        raw_amt = row.get(amount_col, "0")
        amt = _parse_amount(raw_amt)
        if amt is None or amt == 0:
            # Try credit column for negative/refund
            if credit_col and row.get(credit_col, "").strip():
                continue  # skip income/credits
            continue

        # Skip obvious income
        raw_merchant = row.get(merchant_col, "Unknown").strip()
        if any(kw in raw_merchant.lower() for kw in ["payroll", "direct dep", "salary", "interest paid"]):
            continue

        # Parse date
        raw_date = row.get(date_col, "") if date_col else ""
        parsed_date = _parse_date_str(raw_date)

        # Normalize merchant
        clean_merchant, category = normalize_merchant(raw_merchant)

        transactions.append({
            "merchant": clean_merchant,
            "merchant_raw": raw_merchant,
            "amount": round(abs(amt), 2),
            "date": parsed_date,
            "category": category,
            "currency": "USD",
            "source": "csv",
            "extraction_method": "regex",
            "confidence": 0.85,
        })

    return transactions


def _find_col(col_map: dict, candidates: list) -> Optional[str]:
    for orig, lower in col_map.items():
        for c in candidates:
            if c in lower:
                return orig
    return None


def _parse_amount(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = raw.replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date_str(raw: str) -> str:
    if not raw:
        return date.today().isoformat()
    raw = raw.strip()
    try:
        from dateutil import parser as dp
        return dp.parse(raw).strftime("%Y-%m-%d")
    except Exception:
        return raw
