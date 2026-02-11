#!/usr/bin/env python3
"""
PDF Parsing Confidence Validation Script

USAGE:
    python scripts/run_pdf_validation.py --fixtures novotechno-collections/tests/fixtures/invoices/ --output results.json

Testbed: TASK_QA_002 - PDF Parsing Confidence Validation
 """

import sys
import json
import click
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / 'novotechno-collections' / 'src' / 'collections'))

try:
    from pdf_parser import InvoiceParser
except ImportError:
    print("❌ ERROR: pdf_parser.py not found. Ensure correct path.")
    sys.exit(1)


@dataclass
class ValidationResult:
    """Structured validation result."""
    invoice_file: str
    parsed_invoice: Optional[Dict[str, Any]]
    ground_truth: Dict[str, Any]
    confidence: float
    accuracy: float
    status: str
    field_results: Dict[str, Any]


def load_ground_truth(json_file: Path) -> Dict[str, Any]:
    """Load ground truth data from JSON sidecar file."""
    if not json_file.exists():
        raise FileNotFoundError(f"Ground truth file not found: {json_file}")
    
    with open(json_file) as f:
        return json.load(f)


def calculate_confidence(parsed_invoice: Dict[str, Any], ground_truth: Dict[str, Any]) -> float:
    """
    Calculate field-level confidence score.
    
    Weighted confidence calculation:
    - invoice_number: 30% weight
    - client_name: 25% weight  
    - amount: 30% weight
    - due_date: 25% weight
    """
    confidence = { 
        "invoice_number": 0.0, 
        "client_name": 0.0,
        "amount": 0.0,
        "due_date": 0.0
    }
    
    weights = {
        "invoice_number": 0.30,
        "client_name": 0.25,
        "amount": 0.30,
        "due_date": 0.25
    }
    
    attribute_map = {
        "invoice_number": "invoice_number",
        "client_name": "client_name", 
        "amount": "amount",
        "due_date": "due_date"
    }
    
    # Core fields - exact match required
    for field in ["invoice_number", "amount"]:
        parsed = parsed_invoice.get(attribute_map.get(field, field))
        expected = ground_truth.get(attribute_map.get(field, field))
        
        if parsed is None or expected is None:
            confidence[field] = 0.0
            continue
            
        if field == "amount":
            # Allow ±0.01 tolerance for floating point
            if abs(float(parsed) - float(expected)) <= 0.01:
                confidence[field] = 1.0
            else:
                print(f"    ❌ AMOUNT MISMATCH: {parsed:.2f} != {expected:.2f}")
                confidence[field] = 0.0
        else:
            # Exact string match
            if str(parsed).strip() == str(expected).strip():
                confidence[field] = 1.0
            else:
                print(f"    ❌ {field.upper()} MISMATCH: '{parsed}' != '{expected}'")
                confidence[field] = 0.0
    
    # Fuzzy match fields
    for field in ["client_name"]:
        parsed = parsed_invoice.get(attribute_map.get(field, field))
        expected = ground_truth.get(attribute_map.get(field, field))
        
        if parsed is None or expected is None:
            confidence[field] = 0.0
            continue
            
        parsed_str = str(parsed).strip().lower()
        expected_str = str(expected).strip().lower()
        
        if parsed_str == expected_str:
            confidence[field] = 1.0
        else:
            # Fuzzy match - calculate similarity
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, parsed_str, expected_str).ratio()
            confidence[field] = max(0.0, ratio * 0.8)  # Scale down fuzzy matches
            
            if ratio < 0.9:
                print(f"    ⚠️  CLIENT_NAME fuzzy: {ratio:.2f} ({parsed[:50]}...)")
    
    # Date fields
    for field in ["due_date"]:
        parsed = parsed_invoice.get(attribute_map.get(field, field))
        expected = ground_truth.get(attribute_map.get(field, field))
        
        if parsed is None or expected is None:
            confidence[field] = 0.0
            continue
            
        parsed_str = str(parsed)[:10]  # Normalize date
        expected_str = str(expected)[:10]
        
        if parsed_str == expected_str:
            confidence[field] = 1.0
        else:
            print(f"    ❌ {field.upper()} MISMATCH: {parsed} != {expected}")
            confidence[field] = 0.0
    
    # Calculate weighted average
    weighted_sum = sum(confidence[field] * weights[field] for field in confidence)
    total_weight = sum(weights[field] for field in confidence)
    
    return weighted_sum / total_weight if total_weight > 0 else 0.0


def validate_invoice(pdf_file: Path, json_file: Path, parser: InvoiceParser) -> ValidationResult:
    """Validate a single invoice."""
    
    # Load ground truth
    ground_truth = load_ground_truth(json_file)
    
    # Parse the PDF
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")
    
    parsed_invoice = parser.parse(str(pdf_file))
    
    # Calculate confidence
    confidence = calculate_confidence(
        parsed_invoice.to_dict(),
        ground_truth
    )
    
    # Check status
    threshold = 0.90  # Target: >90% accuracy
    is_passed = confidence >= threshold
    status = "PASS" if is_passed else "FAIL"
    
    # Build field results
    field_results = {}
    for field in ["invoice_number", "client_name", "amount", "due_date"]:
        parsed = str(getattr(parsed_invoice, field, None))
        expected = str(ground_truth.get(field, "N/A"))
        field_results[field] = {
            "parsed": parsed,
            "expected": expected,
            "match": parsed == expected
        }
    
    return ValidationResult(
        invoice_file=pdf_file.name,
        parsed_invoice=parsed_invoice.to_dict(),
        ground_truth=ground_truth,
        confidence=confidence,
        accuracy=confidence * 100,  # Percentage
        status=status,
        field_results=field_results
    )


@click.command()
@click.option("--fixtures", type=click.Path(exists=True), required=True,
              help="Directory with PDF fixtures and JSON ground truth files")
@click.option("--output", type=click.Path(), default="~/validation-results-pdf.json",
              help="Output file for results")
@click.option("--threshold", type=float, default=0.90,  # 90% accuracy target
              help="Minimum confidence threshold for passing")
def main(fixtures: str, output: str, threshold: float) -> int:
    """Run PDF parsing confidence validation."""
    
    fixtures_dir = Path(fixtures)
    output_path = Path(output).expanduser()
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "=" * 70)
    print("📄 PDF PARSING CONFIDENCE VALIDATION")
    print("=" * 70)
    print(f"📁 Fixtures: {fixtures_dir}")
    print(f"🎯 Threshold: {threshold * 100:.0f}% confidence")
    print(f"📄 Output: {output_path}")
    print("=" * 70 + "\n")
    
    # Initialize parser
    parser = InvoiceParser()
    
    # Find all PDF files
    pdf_files = list(fixtures_dir.glob("*.pdf"))
    json_files = list(fixtures_dir.glob("*.json"))
    
    if not pdf_files:
        print("❌ ERROR: No PDF files found in fixtures directory")
        return 1
    
    print(f"📋 Found {len(pdf_files)} PDF files")
    print(f"📋 Found {len(json_files)} JSON ground truth files\n")
    
    # Validate each invoice
    results = {
        "test_name": "PDF Parsing Confidence Validation",
        "timestamp": datetime.utcnow().isoformat(),
        "threshold": threshold,
        "results": [],
        "summary": {}
    }
    
    total_fields = 0
    correct_fields = 0
    passed_count = 0
    
    for pdf_file in sorted(pdf_files):
        print(f"\n🔍 Processing: {pdf_file.name}")
        print("-" * 70)
        
        # Find matching JSON file
        json_file = pdf_file.with_suffix(".json")
        if not json_file.exists():
            print(f"  ❌ Missing ground truth: {json_file.name}")
            continue
        
        try:
            # Validate this invoice
            result = validate_invoice(pdf_file, json_file, parser)
            
            # Print results
            status_icon = "✅" if result.status == "PASS" else "❌"
            print(f"  {status_icon} Status: {result.status} (confidence: {result.confidence:.3f})")
            print(f"  📊 Accuracy: {result.accuracy:.1f}%")
            
            # Count field-level accuracy
            for field, data in result.field_results.items():
                total_fields += 1
                icon = "✅" if data["match"] else "❌"
                print(f"    {icon} {field}: '{data['parsed']}' {'==' if data['match'] else '!='} '{data['expected']}'")
                if data["match"]:
                    correct_fields += 1
            
            # Track pass/fail
            if result.status == "PASS":
                passed_count += 1
            
            # Add to results
            results["results"].append({
                "file": pdf_file.name,
                "status": result.status,
                "confidence": result.confidence,
                "accuracy": result.accuracy,
                "fields": result.field_results
            })
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Calculate overall statistics
    overall_accuracy = (correct_fields / total_fields * 100) if total_fields > 0 else 0
    overall_confidence_avg = sum(r["confidence"] for r in results["results"]) / len(results["results"]) if results["results"] else 0
    
    results["summary"] = {
        "total_invoices": len(results["results"]),
        "passed": passed_count,
        "failed": len(results["results"]) - passed_count,
        "overall_field_accuracy_percent": overall_accuracy,
        "overall_confidence_avg": overall_confidence_avg,
        "field_accuracy_breakdown": {
            "correct": correct_fields,
            "total": total_fields,
            "percentage": overall_accuracy
        },
        "all_passed": passed_count == len(results["results"]) and len(results["results"]) > 0,
        "target_threshold_met": overall_confidence_avg >= threshold
    }
    
    # Final summary
    print("\n" + "=" * 70)
    print("📊 VALIDATION SUMMARY")
    print("=" * 70)
    print(f"  📋 Invoices Tested: {results['summary']['total_invoices']}/5")
    print(f"  ✅ Passed: {results['summary']['passed']}")
    print(f"  ❌ Failed: {results['summary']['failed']}")
    print(f"  📈 Overall Field Accuracy: {results['summary']['overall_field_accuracy_percent']:.1f}%")
    print(f"  📈 Average Confidence: {results['summary']['overall_confidence_avg']:.3f}")
    
    # Color code the summary
    if results["summary"]["all_passed"]:
        print("\n" + "=" * 70)
        print("🎉 ALL INVOICES PASSED VALIDATION")
        print("=" * 70 + "\n")
        exit_code = 0
    else:
        print("\n" + "=" * 70)
        print("❌ VALIDATION FAILED - REVIEW REQUIRED")
        print("=" * 70 + "\n")
        exit_code = 1
    
    # Write results
    try:
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"📄 Detailed results saved to: {output_path}")
    except Exception as e:
        print(f"⚠️  Could not save results: {e}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())