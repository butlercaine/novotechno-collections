# TASK: PDF Parsing Confidence Validation
**Task ID:** TASK_QA_002
**Owner:** qa-engineer-novotechno
**Type:** validation
**Priority:** P0
**Status:** PENDING
**Created:** 2026-02-11 08:00 GMT-5

## Context
Validate PDF parsing confidence on 5 diverse invoice templates. Target: >90% field extraction accuracy. (C-009)

## Requirements

### 1. Test Invoice Samples
Must test 5 diverse invoice templates representing real-world diversity:

**Sample Set:**
1. **Template A:** Standard Colombian invoice (novotechno-collections/fixtures/invoices/colombian-standard.pdf)
   - Format: A4, Spanish text, COP currency
   - Fields: invoice_number, client_name, amount, due_date, items

2. **Template B:** Mexican invoice (novotechno-collections/fixtures/invoices/mexican-regional.pdf)
   - Format: Letter, MXN currency, Mexican Spanish
   - Fields: invoice_number, client_name, amount, due_date, items

3. **Template C:** Spanish invoice (novotechno-collections/fixtures/invoices/spanish-eu.pdf)
   - Format: A4, EUR currency, EU compliance
   - Fields: invoice_number, client_name, amount, due_date, items

4. **Template D:** Minimal/compact invoice (novotechno-collections/fixtures/invoices/minimal-quick.pdf)
   - Format: Half-page, minimal fields
   - Fields: invoice_number, amount, due_date

5. **Template E:** Complex multi-page invoice (novotechno-collections/fixtures/invoices/complex-multi-page.pdf)
   - Format: Multi-page, 15+ line items, header/footer spread
   - Fields: invoice_number, client_name, amount, due_date, items (15+)

### 2. Test Script
**File:** `novotechno-collections/scripts/run_pdf_validation.py`

```python
#!/usr/bin/env python3
"""
PDF Parsing Confidence Validation Script

Usage:
    python scripts/run_pdf_validation.py --fixtures fixtures/invoices/ --output results.json
"""
import click
import json
from pathlib import Path
from src.collections.pdf_parser import InvoiceParser

@click.command()
@click.option("--fixtures", type=click.Path(), required=True, help="Directory with test PDF fixtures")
@click.option("--output", type=click.Path(), help="Output file for results")
@click.option("--threshold", default=0.85, help="Minimum confidence threshold")
def main(fixtures: str, output: str, threshold: float):
    """Run PDF parsing confidence validation"""
    
    results = {
        "test_name": "PDF Parsing Confidence",
        "timestamp": datetime.utcnow().isoformat(),
        "threshold": threshold,
        "invoices": []
    }
    
    parser = InvoiceParser()
    fixtures_dir = Path(fixtures)
    
    click.echo(f"📄 PDF Validation ({threshold} threshold)")
    click.echo(f"📁 Fixtures: {fixtures_dir}\n")
    
    total_fields = 0
    correct_fields = 0
    
    for pdf_file in sorted(fixtures_dir.glob("*.pdf")):
        click.echo(f"Processing: {pdf_file.name}")
        
        try:
            # Parse invoice
            result = parser.parse(str(pdf_file))
            
            # Get ground truth (from separate JSON file)
            ground_truth = _load_ground_truth(pdf_file)
            
            # Calculate accuracy
            field_accuracy = _calculate_field_accuracy(result, ground_truth)
            
            invoice_result = {
                "file": pdf_file.name,
                "confidence": result.confidence,
                "field_accuracy": field_accuracy,
                "passed": result.confidence >= threshold,
                "fields": {
                    "invoice_number": {
                        "parsed": result.invoice_number,
                        "expected": ground_truth.get("invoice_number"),
                        "correct": result.invoice_number == ground_truth.get("invoice_number")
                    },
                    "amount": {
                        "parsed": result.amount,
                        "expected": ground_truth.get("amount"),
                        "correct": result.amount == ground_truth.get("amount")
                    },
                    "due_date": {
                        "parsed": str(result.due_date),
                        "expected": str(ground_truth.get("due_date")),
                        "correct": str(result.due_date) == str(ground_truth.get("due_date"))
                    }
                }
            }
            
            results["invoices"].append(invoice_result)
            
            # Track totals
            for field, data in invoice_result["fields"].items():
                total_fields += 1
                if data["correct"]:
                    correct_fields += 1
            
            status = "✅" if invoice_result["passed"] else "❌"
            click.echo(f"  {status} Confidence: {result.confidence:.2f}")
            
        except Exception as e:
            click.echo(f"  ❌ ERROR: {e}")
            results["invoices"].append({
                "file": pdf_file.name,
                "error": str(e),
                "passed": False
            })
    
    # Calculate overall results
    overall_accuracy = (correct_fields / total_fields * 100) if total_fields > 0 else 0
    
    results["summary"] = {
        "total_invoices": len(results["invoices"]),
        "passed": sum(1 for i in results["invoices"] if i.get("passed")),
        "failed": sum(1 for i in results["invoices"] if not i.get("passed")),
        "field_accuracy_percent": overall_accuracy,
        "average_confidence": sum(i.get("confidence", 0) for i in results["invoices"]) / len(results["invoices"]) if results["invoices"] else 0
    }
    
    # Output results
    if output:
        with open(output, 'w') as f:
            json.dump(results, f, indent=2)
        click.echo(f"\n📄 Results written to: {output}")
    
    # Summary
    click.echo(f"\n{'✅ VALIDATION PASSED' if overall_accuracy >= 90 else '❌ VALIDATION FAILED'}")
    click.eprint(f"Field Accuracy: {overall_accuracy:.1f}% ({correct_fields}/{total_fields})")
    click.eprint(f"Average Confidence: {results['summary']['average_confidence']:.2f}")
    
    return 0 if overall_accuracy >= 90 else 1

def _load_ground_truth(pdf_file: Path) -> Dict:
    """Load ground truth from JSON sidecar"""
    json_file = pdf_file.with_suffix(".json")
    if json_file.exists():
        with open(json_file) as f:
            return json.load(f)
    return {}

def _calculate_field_accuracy(result, ground_truth) -> float:
    """Calculate field-level accuracy"""
    fields_to_check = ["invoice_number", "amount", "due_date"]
    correct = 0
    total = len(fields_to_check)
    
    for field in fields_to_check:
        if field == "amount":
            # Allow small tolerance for amount
            if abs(getattr(result, field, 0) - ground_truth.get(field, 0)) < 0.01:
                correct += 1
        else:
            if getattr(result, field, None) == ground_truth.get(field):
                correct += 1
    
    return correct / total
```

### 3. Validation Report
**File:** `~/.openclaw/workspace-qa-engineer-novotechno/PDF-CONFIDENCE-RESULTS.md`

```markdown
# PDF Parsing Confidence Validation Report

**Date:** [DATE]
**Test Duration:** 1.5 hours
**Validator:** qa-engineer-novotechno
**Status:** PASSED / FAILED

---

## Test Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Invoices Tested | 5 | 5 | ✅ |
| Overall Field Accuracy | X% | >90% | ✅/❌ |
| Average Confidence | X.XX | >0.9 | ✅/❌ |
| Passed Templates | X/5 | 5/5 | ✅/❌ |
| Failed Templates | X/5 | 0/5 | ✅/❌ |

---

## Per-Template Results

### Template A: Colombian Standard
- **Confidence Score:** X.XX
- **Field Accuracy:** X%
- **Status:** ✅ PASS / ❌ FAIL
- **Notes:** [Observations]

### Template B: Mexican Regional
- **Confidence Score:** X.XX
- **Field Accuracy:** X%
- **Status:** ✅ PASS / ❌ FAIL
- **Notes:** [Observations]

### Template C: Spanish EU
- **Confidence Score:** X.XX
- **Field Accuracy:** X%
- **Status:** ✅ PASS / ❌ FAIL
- **Notes:** [Observations]

### Template D: Minimal Quick
- **Confidence Score:** X.XX
- **Field Accuracy:** X%
- **Status:** ✅ PASS / ❌ FAIL
- **Notes:** [Observations]

### Template E: Complex Multi-Page
- **Confidence Score:** X.XX
- **Field Accuracy:** X%
- **Status:** ✅ PASS / ❌ FAIL
- **Notes:** [Observations]

---

## Confidence Algorithm Analysis

### Field Weights
| Field | Weight | Observed Accuracy | Contribution |
|-------|--------|------------------|--------------|
| invoice_number | 30% | X% | X.X% |
| amount | 30% | X% | X.X% |
| due_date | 25% | X% | X.X% |
| items | 15% | X% | X.X% |

### Distribution
| Confidence Range | Count | Percentage |
|------------------|-------|------------|
| ≥0.95 (Auto) | X | X% |
| 0.85-0.94 (Review) | X | X% |
| <0.85 (Manual) | X | X% |

---

## Review Queue Projection

- **Estimated Auto-Processed:** X% (confidence ≥0.95)
- **Estimated Review Queue:** X% (confidence 0.85-0.94)
- **Estimated Manual:** X% (confidence <0.85)

**Target:** Manual <10% ✅/❌

---

## Recommendations

[Based on results]

### Immediate Actions
- [ ] Fix specific field extraction issues
- [ ] Add template-specific patterns
- [ ] Adjust confidence thresholds

### Long-term Improvements
- [ ] Train ML model on more templates
- [ ] Add template auto-detection
- [ ] Implement ensemble parsing

---

## Test Evidence

- **Test Fixtures:** `novotechno-collections/tests/fixtures/invoices/`
- **Ground Truth:** JSON sidecar files for each PDF
- **Test Script:** `novotechno-collections/scripts/run_pdf_validation.py`
- **Results:** JSON output saved

---

## Conclusion

**Overall Result:** ✅ PASSED / ❌ FAILED

**Key Findings:**
1. [Major observation 1]
2. [Major observation 2]
3. [Major observation 3]

**Next Steps:**
- Proceed to E2E testing / Return to development for fixes
```

## Dependencies
- TASK_PDF_001 (must complete first)
- 5 test PDF fixtures with ground truth JSON files

## Output Files
- `novotechno-collections/tests/fixtures/invoices/` (5 PDFs + 5 JSON ground truth files)
- `novotechno-collections/scripts/run_pdf_validation.py` (150 lines)
- `~/.openclaw/workspace-qa-engineer-novotechno/PDF-CONFIDENCE-RESULTS.md` (validation report)

## Definition of Done
- [ ] All 5 templates tested
- [ ] Field accuracy >90%
- [ ] Manual processing <10%
- [ ] Validation report written
- [ ] RESPONSE file written

## Success Criteria (from PROJECT_SCOPING)
- [ ] >90% fields extracted correctly (C-009)
- [ ] Confidence algorithm validated
- [ ] Manual review queue manageable (<10%)
- [ ] Review queue projection provided

## Previous Task
TASK_PDF_001 (PDF parser) — dependency met

## Next Task
TASK_QA_003 (E2E testing) — depends on CLI tools completion
