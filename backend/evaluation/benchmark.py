"""
evaluation/benchmark.py — Tests extraction pipeline accuracy.

Run:  cd backend && python -m evaluation.benchmark

Measures:
- Merchant normalization accuracy (cryptic bank codes → clean names)
- Category auto-assignment accuracy
- Regex extraction accuracy across formats
- CSV parsing accuracy
"""

from pipeline.extractor import normalize_merchant, extract_regex, parse_csv_transactions


# ---------------------------------------------------------------------------
# Test 1: Merchant Normalization (the headline metric)
# ---------------------------------------------------------------------------

MERCHANT_NORM_TESTS = [
    # (raw_input, expected_clean, expected_category)
    ("AMZN MKTP US*1A2B3C", "Amazon", "shopping"),
    ("AMZN MKTPL US", "Amazon", "shopping"),
    ("AMAZON.COM*2K9TG1", "Amazon", "shopping"),
    ("AMZN DIGITAL*MG03F", "Amazon Digital", "shopping"),
    ("UBER   *EATS PENDING", "Uber Eats", "food"),
    ("UBER *TRIP HELP.UBER", "Uber", "transport"),
    ("DD *DOORDASH DASHER", "DoorDash", "food"),
    ("DOORDASH DASHER SFO", "DoorDash", "food"),
    ("GRUBHUB* HALAL GUYS", "Grubhub", "food"),
    ("SQ *BLUE BOTTLE COFFEE", "Blue Bottle Coffee", "other"),  # Square POS
    ("TST* SWEETGREEN 123", "Sweetgreen 123", "other"),       # Toast POS
    ("PP*ETSY INC", "Etsy Inc", "other"),                     # PayPal
    ("GOOGLE *YouTubePremium", "YouTube Premium", "subscriptions"),
    ("GOOG*CLOUD STORAGE", "Google", "subscriptions"),
    ("APL* ITUNES 866-712", "Apple", "subscriptions"),
    ("APPLE.COM/BILL", "Apple", "subscriptions"),
    ("SPOTIFY USA", "Spotify", "subscriptions"),
    ("NETFLIX.COM", "Netflix", "subscriptions"),
    ("HULU 877-8244858", "Hulu", "subscriptions"),
    ("DISNEY PLUS 888", "Disney+", "subscriptions"),
    ("WHOLEFDS MKT #10234", "Whole Foods", "groceries"),
    ("TRADER JOE'S #639", "Trader Joe's", "groceries"),
    ("COSTCO WHSE #1234", "Costco", "groceries"),
    ("WAL-MART #3456", "Walmart", "groceries"),
    ("TARGET 00012345", "Target", "shopping"),
    ("STARBUCKS STORE 12345", "Starbucks", "food"),
    ("CHICK-FIL-A #12345", "Chick-fil-A", "food"),
    ("MCDONALD'S F12345", "McDonald's", "food"),
    ("LYFT *RIDE SUN 5PM", "Lyft", "transport"),
    ("CVS/PHARMACY #8432", "CVS", "health"),
    ("WALGREENS #12345", "Walgreens", "health"),
    ("ADOBE *CREATIVE CLD", "Adobe", "subscriptions"),
    ("MICROSOFT *365", "Microsoft", "subscriptions"),
    ("DUNKIN #12345", "Dunkin'", "food"),
    ("CHIPOTLE 1234", "Chipotle", "food"),
    # Edge cases
    ("PAYPAL *FREELANCER", "Freelancer", "other"),
    ("SQ *JOES PIZZA PHI", "Joes Pizza Phi", "other"),
    ("INSTACART HTTPSINSTA", "Instacart", "food"),
]


def test_merchant_normalization():
    """Benchmark merchant normalization accuracy."""
    correct_name = 0
    correct_cat = 0
    total = len(MERCHANT_NORM_TESTS)
    failures = []

    for raw, exp_name, exp_cat in MERCHANT_NORM_TESTS:
        clean, cat = normalize_merchant(raw)

        name_match = clean.lower().strip() == exp_name.lower().strip()
        cat_match = cat == exp_cat

        if name_match:
            correct_name += 1
        if cat_match:
            correct_cat += 1
        if not name_match or not cat_match:
            failures.append({
                "input": raw,
                "expected": f"{exp_name} [{exp_cat}]",
                "got": f"{clean} [{cat}]",
                "name_ok": name_match,
                "cat_ok": cat_match,
            })

    name_acc = correct_name / total
    cat_acc = correct_cat / total

    print(f"\n{'='*60}")
    print(f"  MERCHANT NORMALIZATION BENCHMARK")
    print(f"{'='*60}")
    print(f"  Name accuracy:     {correct_name}/{total} = {name_acc:.1%}")
    print(f"  Category accuracy: {correct_cat}/{total} = {cat_acc:.1%}")

    if failures:
        print(f"\n  Failures ({len(failures)}):")
        for f in failures:
            status = []
            if not f["name_ok"]:
                status.append("NAME")
            if not f["cat_ok"]:
                status.append("CAT")
            print(f"    [{','.join(status)}] '{f['input']}' → got '{f['got']}', expected '{f['expected']}'")

    return name_acc, cat_acc


# ---------------------------------------------------------------------------
# Test 2: Regex Extraction on diverse text formats
# ---------------------------------------------------------------------------

EXTRACTION_TESTS = [
    {
        "text": "Total: $45.67 at Starbucks on 03/15/2026 Visa ending in 4532",
        "expected": {"amount": 45.67, "date": "2026-03-15", "merchant": "Starbucks"},
    },
    {
        "text": "UBER   *EATS PENDING  $28.43  03/18/2026 Card ending in 8821",
        "expected": {"amount": 28.43, "date": "2026-03-18"},
    },
    {
        "text": "Your Netflix subscription renewal. Amount charged: $22.99. Billing date: March 15, 2026.",
        "expected": {"amount": 22.99, "merchant": "Netflix"},
    },
    {
        "text": "Amazon.com order #112-3456789 Total: $215.98 Payment: Visa ending in 4532",
        "expected": {"amount": 215.98, "merchant": "Amazon"},
    },
    {
        "text": "Venmo: You paid $35.00 on March 16, 2026",
        "expected": {"amount": 35.00, "date": "2026-03-16"},
    },
    {
        "text": "Chase Alert: $87.43 transaction on debit card ending in 6291",
        "expected": {"amount": 87.43},
    },
    {
        "text": "Total charged: €342.00 on Visa ending in 4532",
        "expected": {"amount": 342.00, "currency": "EUR"},
    },
    {
        "text": "Starbucks $6.45 03/20",
        "expected": {"amount": 6.45, "merchant": "Starbucks"},
    },
]


def test_regex_extraction():
    """Benchmark regex extraction accuracy."""
    total_fields = 0
    correct = 0
    failures = []

    for test in EXTRACTION_TESTS:
        result = extract_regex(test["text"])

        for field, expected in test["expected"].items():
            total_fields += 1
            actual = getattr(result, field, None)

            if field == "amount":
                if actual is not None and abs(actual - expected) < 0.02:
                    correct += 1
                else:
                    failures.append(f"  amount: got {actual}, expected {expected} — '{test['text'][:50]}...'")
            elif field == "merchant":
                if actual and expected.lower() in actual.lower():
                    correct += 1
                else:
                    failures.append(f"  merchant: got '{actual}', expected '{expected}' — '{test['text'][:50]}...'")
            elif field == "currency":
                if actual == expected:
                    correct += 1
                else:
                    failures.append(f"  currency: got '{actual}', expected '{expected}'")
            else:
                if actual == expected:
                    correct += 1
                else:
                    failures.append(f"  {field}: got '{actual}', expected '{expected}'")

    acc = correct / total_fields if total_fields > 0 else 0
    print(f"\n{'='*60}")
    print(f"  REGEX EXTRACTION BENCHMARK")
    print(f"{'='*60}")
    print(f"  Field accuracy: {correct}/{total_fields} = {acc:.1%}")

    if failures:
        print(f"\n  Failures ({len(failures)}):")
        for f in failures:
            print(f"  {f}")

    return acc


# ---------------------------------------------------------------------------
# Test 3: CSV Parsing
# ---------------------------------------------------------------------------

SAMPLE_CSV = """Date,Description,Amount,Category
03/15/2026,AMZN MKTP US*1A2B3C,-45.67,Shopping
03/16/2026,UBER   *EATS PENDING,-28.43,Food
03/17/2026,WHOLEFDS MKT #10234,-87.43,Groceries
03/18/2026,SPOTIFY USA,-10.99,Entertainment
03/19/2026,DD *DOORDASH DASHER,-24.31,Food
03/19/2026,PAYROLL DIRECT DEP,3500.00,Income
03/20/2026,LYFT *RIDE SUN 5PM,-15.60,Travel
03/20/2026,CVS/PHARMACY #8432,-30.75,Health
"""


def test_csv_parsing():
    """Test CSV parsing with realistic bank statement format."""
    results = parse_csv_transactions(SAMPLE_CSV)

    print(f"\n{'='*60}")
    print(f"  CSV PARSING BENCHMARK")
    print(f"{'='*60}")
    print(f"  Transactions parsed: {len(results)}")
    print(f"  Income filtered:     {7 - len(results)} (expected: 1)")

    for t in results:
        print(f"    {t['merchant_raw'][:30]:<32} → {t['merchant']:<20} [{t['category']:<14}] ${t['amount']:.2f}")

    # Check income was filtered
    income_present = any("payroll" in t.get("merchant", "").lower() for t in results)
    print(f"\n  Income filtered correctly: {'YES' if not income_present else 'NO'}")

    return len(results), not income_present


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  SPENDSENSE PIPELINE BENCHMARK SUITE")
    print("="*60)

    name_acc, cat_acc = test_merchant_normalization()
    regex_acc = test_regex_extraction()
    csv_count, income_filtered = test_csv_parsing()

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Merchant normalization: {name_acc:.1%}")
    print(f"  Category assignment:    {cat_acc:.1%}")
    print(f"  Regex extraction:       {regex_acc:.1%}")
    print(f"  CSV parsing:            {csv_count} txns, income filtered={'YES' if income_filtered else 'NO'}")
    print()

    if name_acc >= 0.85 and cat_acc >= 0.80:
        print("  ✓ Pipeline meets accuracy targets")
    else:
        print("  ✗ Below target — check failures above")
