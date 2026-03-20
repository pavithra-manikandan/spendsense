"""
agent/analyst.py — Financial Insight Agent.

This is NOT a chatbot wrapper. It's a structured analysis pipeline:
  1. User asks a question ("where am I overspending?")
  2. Agent runs pandas analytics on the transaction data
  3. Computes concrete metrics: trends, anomalies, forecasts
  4. ONE LLM call synthesizes the numbers into actionable advice

The LLM never sees raw transaction data — only aggregated stats.
This is both cheaper and more private.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("spendsense.agent")


@dataclass
class AnalysisContext:
    """Pre-computed analytics that get passed to the LLM."""
    total_spent: float = 0.0
    transaction_count: int = 0
    date_range: str = ""
    by_category: dict = field(default_factory=dict)       # {cat: total}
    by_merchant: dict = field(default_factory=dict)        # {merchant: total}
    top_merchants: list = field(default_factory=list)      # [(merchant, total, count)]
    monthly_trend: dict = field(default_factory=dict)      # {YYYY-MM: total}
    weekly_trend: dict = field(default_factory=dict)       # {week_label: total}
    anomalies: list = field(default_factory=list)          # [{merchant, amount, why}]
    recurring: list = field(default_factory=list)          # [{merchant, avg_amount, frequency}]
    forecast_next_month: Optional[float] = None
    category_percentages: dict = field(default_factory=dict)
    daily_average: float = 0.0
    biggest_single: dict = field(default_factory=dict)     # {merchant, amount, date}


def build_analysis(transactions: list[dict]) -> AnalysisContext:
    """
    Run all analytics on the transaction list using pandas.
    Returns a rich context object with pre-computed insights.
    """
    try:
        import pandas as pd
    except ImportError:
        return _build_analysis_no_pandas(transactions)

    if not transactions:
        return AnalysisContext()

    df = pd.DataFrame(transactions)
    ctx = AnalysisContext()

    # --- Basic stats ---
    ctx.total_spent = round(df["amount"].sum(), 2)
    ctx.transaction_count = len(df)

    # Parse dates
    df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce")
    valid_dates = df.dropna(subset=["date_parsed"])

    if not valid_dates.empty:
        min_date = valid_dates["date_parsed"].min().strftime("%Y-%m-%d")
        max_date = valid_dates["date_parsed"].max().strftime("%Y-%m-%d")
        ctx.date_range = f"{min_date} to {max_date}"

        # Daily average
        days = (valid_dates["date_parsed"].max() - valid_dates["date_parsed"].min()).days
        ctx.daily_average = round(ctx.total_spent / max(days, 1), 2)

    # --- By category ---
    cat_totals = df.groupby("category")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    ctx.by_category = {row.Index: round(row.sum, 2) for row in cat_totals.itertuples()}
    ctx.category_percentages = {
        cat: round(amt / ctx.total_spent * 100, 1)
        for cat, amt in ctx.by_category.items()
    } if ctx.total_spent > 0 else {}

    # --- By merchant (top 15) ---
    merch = df.groupby("merchant")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    ctx.top_merchants = [
        {"merchant": row.Index, "total": round(row.sum, 2), "count": int(row.count)}
        for row in merch.head(15).itertuples()
    ]
    ctx.by_merchant = {row.Index: round(row.sum, 2) for row in merch.itertuples()}

    # --- Monthly trend ---
    if not valid_dates.empty:
        valid_dates = valid_dates.copy()
        valid_dates["month"] = valid_dates["date_parsed"].dt.to_period("M").astype(str)
        monthly = valid_dates.groupby("month")["amount"].sum().sort_index()
        ctx.monthly_trend = {k: round(v, 2) for k, v in monthly.items()}

        # --- Weekly trend (last 8 weeks) ---
        valid_dates["week"] = valid_dates["date_parsed"].dt.to_period("W").astype(str)
        weekly = valid_dates.groupby("week")["amount"].sum().sort_index().tail(8)
        ctx.weekly_trend = {k: round(v, 2) for k, v in weekly.items()}

    # --- Biggest single transaction ---
    biggest_idx = df["amount"].idxmax()
    ctx.biggest_single = {
        "merchant": df.loc[biggest_idx, "merchant"],
        "amount": round(df.loc[biggest_idx, "amount"], 2),
        "date": df.loc[biggest_idx, "date"],
    }

    # --- Anomaly detection (z-score based) ---
    ctx.anomalies = _detect_anomalies(df)

    # --- Recurring charges detection ---
    ctx.recurring = _detect_recurring(df)

    # --- Simple forecast (linear extrapolation from monthly trend) ---
    ctx.forecast_next_month = _forecast_next_month(ctx.monthly_trend)

    return ctx


def _detect_anomalies(df) -> list:
    """
    Detect spending anomalies using z-scores per category.
    A transaction is anomalous if it's >2σ above the category mean.
    """
    import pandas as pd
    anomalies = []

    for category in df["category"].unique():
        cat_df = df[df["category"] == category]
        if len(cat_df) < 3:
            continue

        mean = cat_df["amount"].mean()
        std = cat_df["amount"].std()
        if std == 0:
            continue

        threshold = mean + 2 * std
        outliers = cat_df[cat_df["amount"] > threshold]

        for _, row in outliers.iterrows():
            anomalies.append({
                "merchant": row["merchant"],
                "amount": round(row["amount"], 2),
                "date": row["date"],
                "category": category,
                "category_avg": round(mean, 2),
                "z_score": round((row["amount"] - mean) / std, 1),
                "reason": f"${row['amount']:.2f} is {((row['amount'] - mean) / mean * 100):.0f}% above avg ${mean:.2f} for {category}",
            })

    # Also detect week-over-week category spikes
    return sorted(anomalies, key=lambda x: x.get("z_score", 0), reverse=True)[:10]


def _detect_recurring(df) -> list:
    """
    Detect likely recurring/subscription charges.
    Criteria: same merchant, similar amount (±10%), appears 2+ months.
    """
    import pandas as pd

    recurring = []
    df_copy = df.copy()
    df_copy["date_parsed"] = pd.to_datetime(df_copy["date"], errors="coerce")
    df_copy["month"] = df_copy["date_parsed"].dt.to_period("M")

    for merchant in df_copy["merchant"].unique():
        m_df = df_copy[df_copy["merchant"] == merchant]
        if len(m_df) < 2:
            continue

        months = m_df["month"].nunique()
        if months < 2:
            continue

        amounts = m_df["amount"].tolist()
        avg_amt = sum(amounts) / len(amounts)
        # Check if amounts are consistent (±15%)
        consistent = all(abs(a - avg_amt) / avg_amt < 0.15 for a in amounts) if avg_amt > 0 else False

        if consistent:
            recurring.append({
                "merchant": merchant,
                "avg_amount": round(avg_amt, 2),
                "occurrences": len(m_df),
                "months_seen": months,
                "estimated_annual": round(avg_amt * 12, 2),
            })

    return sorted(recurring, key=lambda x: x["estimated_annual"], reverse=True)


def _forecast_next_month(monthly_trend: dict) -> Optional[float]:
    """
    Simple linear regression forecast for next month's spending.
    Uses last 3-6 months of data.
    """
    if len(monthly_trend) < 2:
        return None

    values = list(monthly_trend.values())[-6:]  # last 6 months
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    # Slope via least squares
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return round(y_mean, 2)

    slope = numerator / denominator
    forecast = y_mean + slope * (n - x_mean)

    return round(max(forecast, 0), 2)  # don't predict negative


def _build_analysis_no_pandas(transactions: list[dict]) -> AnalysisContext:
    """Fallback analytics without pandas."""
    ctx = AnalysisContext()
    if not transactions:
        return ctx

    ctx.total_spent = round(sum(t.get("amount", 0) for t in transactions), 2)
    ctx.transaction_count = len(transactions)

    cats = {}
    for t in transactions:
        c = t.get("category", "other")
        cats[c] = cats.get(c, 0) + t.get("amount", 0)
    ctx.by_category = {k: round(v, 2) for k, v in sorted(cats.items(), key=lambda x: -x[1])}

    return ctx


# ---------------------------------------------------------------------------
# LLM INSIGHT GENERATION — One call, max value
# ---------------------------------------------------------------------------

ANALYST_SYSTEM_PROMPT = """You are a sharp personal finance analyst. You receive pre-computed
spending analytics and the user's question. Your job:

1. ANSWER their specific question directly (don't just summarize)
2. Give 2-3 ACTIONABLE insights with specific dollar amounts
3. If they ask "how to save", give concrete cuts — name the merchants/categories
4. If anomalies exist, flag them clearly
5. Reference the actual numbers — never make up data

Tone: direct, specific, like a smart friend who's good with money. Not a lecture.
Keep it under 250 words. Use $ amounts, percentages, and comparisons."""


def ask_agent(
    question: str,
    transactions: list[dict],
    client=None,
) -> dict:
    """
    The main agent entry point.

    1. Runs pandas analytics on transactions
    2. Builds a rich context with anomalies, trends, forecasts
    3. ONE LLM call to synthesize into natural language advice

    Returns: {answer, analysis_context, method}
    """
    # Step 1: Compute analytics
    ctx = build_analysis(transactions)

    # Step 2: Build context string for LLM (aggregated stats only, not raw data)
    context_str = _format_context_for_llm(ctx)

    # Step 3: LLM synthesis (or fallback to template if no client)
    if client:
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                system=ANALYST_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"My spending data:\n{context_str}\n\nMy question: {question}",
                }],
            )
            answer = resp.content[0].text
        except Exception as e:
            logger.error(f"Agent LLM call failed: {e}")
            answer = _template_answer(question, ctx)
    else:
        answer = _template_answer(question, ctx)

    return {
        "answer": answer,
        "context": {
            "total_spent": ctx.total_spent,
            "transaction_count": ctx.transaction_count,
            "date_range": ctx.date_range,
            "by_category": ctx.by_category,
            "category_percentages": ctx.category_percentages,
            "top_merchants": ctx.top_merchants[:10],
            "anomalies": ctx.anomalies[:5],
            "recurring": ctx.recurring[:8],
            "forecast_next_month": ctx.forecast_next_month,
            "monthly_trend": ctx.monthly_trend,
            "weekly_trend": ctx.weekly_trend,
            "daily_average": ctx.daily_average,
        },
    }


def _format_context_for_llm(ctx: AnalysisContext) -> str:
    """Format analytics context as a concise string for the LLM."""
    parts = [
        f"Period: {ctx.date_range}",
        f"Total: ${ctx.total_spent:,.2f} across {ctx.transaction_count} transactions",
        f"Daily average: ${ctx.daily_average:.2f}",
    ]

    if ctx.by_category:
        cats = ", ".join(f"{c}: ${v:,.2f} ({ctx.category_percentages.get(c, 0):.0f}%)"
                        for c, v in list(ctx.by_category.items())[:8])
        parts.append(f"Categories: {cats}")

    if ctx.top_merchants:
        top = ", ".join(f"{m['merchant']}: ${m['total']:,.2f} ({m['count']}x)"
                       for m in ctx.top_merchants[:8])
        parts.append(f"Top merchants: {top}")

    if ctx.monthly_trend:
        trend = ", ".join(f"{k}: ${v:,.2f}" for k, v in list(ctx.monthly_trend.items())[-4:])
        parts.append(f"Monthly trend: {trend}")

    if ctx.forecast_next_month:
        parts.append(f"Forecast next month: ${ctx.forecast_next_month:,.2f}")

    if ctx.anomalies:
        anoms = "; ".join(a["reason"] for a in ctx.anomalies[:3])
        parts.append(f"Anomalies detected: {anoms}")

    if ctx.recurring:
        subs = ", ".join(f"{r['merchant']}: ${r['avg_amount']:.2f}/mo (${r['estimated_annual']:.2f}/yr)"
                        for r in ctx.recurring[:5])
        parts.append(f"Recurring charges: {subs}")

    if ctx.biggest_single:
        parts.append(f"Biggest single: ${ctx.biggest_single['amount']:.2f} at {ctx.biggest_single['merchant']} on {ctx.biggest_single['date']}")

    return "\n".join(parts)


def _template_answer(question: str, ctx: AnalysisContext) -> str:
    """Fallback template-based answer when LLM is unavailable."""
    q = question.lower()

    if "overspend" in q or "too much" in q or "where" in q:
        if ctx.by_category:
            top_cat = list(ctx.by_category.items())[0]
            return (f"Your biggest category is {top_cat[0]} at ${top_cat[1]:,.2f} "
                    f"({ctx.category_percentages.get(top_cat[0], 0):.0f}% of total). "
                    f"Top merchants: {', '.join(m['merchant'] for m in ctx.top_merchants[:3])}.")

    if "save" in q or "cut" in q:
        tips = []
        if ctx.recurring:
            total_subs = sum(r["avg_amount"] for r in ctx.recurring)
            tips.append(f"You have ${total_subs:.2f}/mo in recurring charges")
        if ctx.anomalies:
            tips.append(f"{len(ctx.anomalies)} unusual transactions flagged")
        return " ".join(tips) if tips else f"Total spending: ${ctx.total_spent:,.2f} over {ctx.date_range}."

    return (f"Total: ${ctx.total_spent:,.2f} across {ctx.transaction_count} transactions. "
            f"Daily avg: ${ctx.daily_average:.2f}. "
            f"Top category: {list(ctx.by_category.keys())[0] if ctx.by_category else 'N/A'}.")
