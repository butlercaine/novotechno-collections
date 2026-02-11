#!/usr/bin/env python3
"""
Generate test PDF invoices from JSON fixtures for validation.

This script creates PDF files from the textual content stored in the
JSON fixture files, enabling realistic parsing testing without manual
document creation.
"""

import sys
from pathlib import Path
from typing import Dict
import json

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import inch
    HAS_REPORTLAB = True
except ImportError:
    # Fallback: create simple text-based PDFs if reportlab unavailable
    HAS_REPORTLAB = False

sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'collections'))


def generate_text_pdf(content: str, pdf_path: Path, size=A4):
    """Generate a simple PDF from text content using reportlab."""
    if not HAS_REPORTLAB:
        # Fallback if reportlab not available
        _generate_fallback_pdf(content, pdf_path)
        return
    
    c = canvas.Canvas(str(pdf_path), pagesize=size)
    
    # Set font
    c.setFont("Helvetica", 11)
    
    # Draw header
    y = 750
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "Invoice")
    
    # Draw content
    c.setFont("Helvetica", 11)
    y -= 40
    lines = content.split("\\n")
    
    for line in lines:
        if y < 100:
            c.showPage()
            y = 750
        
        # Handle bold/line items
        if "Consulting" in line or "Software" in line or "Service" in line:
            c.setFont("Helvetica", 10)
            c.drawString(100, y, line)
            c.setFont("Helvetica", 11)
        elif line.strip() and not line.startswith(" "):
            c.drawString(72, y, line)
        else:
            c.drawString(100, y, line)
        
        y -= 15
    
    # Draw footer if space
    if y > 100:
        y = max(50, y - 40)
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(72, y, "Generated for testing purposes")
    
    c.save()
    print(f"  📄 Created: {pdf_path.name}")


def _generate_fallback_pdf(content: str, pdf_path: Path):
    """Generate a minimal PDF file with text content (fallback)."""
    # For testing purposes, create a simple text file that looks like PDF
    # In production, use reportlab
    text_path = pdf_path.with_suffix('.txt')
    text_path.write_text(content.replace('\\n', '\n'))
    print(f"  ⚠️  Created text file (install reportlab for PDF): {text_path.name}")


def load_template(json_file: Path) -> Dict:
    """Load invoice template from JSON."""
    with open(json_file) as f:
        return json.load(f)


def main():
    """Generate all PDF test fixtures."""
    
    print("\n" + "=" * 70)
    print("📄 GENERATING TEST PDF INVOICES")
    print("=" * 70)
    
    # Setup paths
    project_root = Path(__file__).parent.parent
    fixtures_dir = project_root / 'tests' / 'fixtures' / 'invoices'
    
    if not fixtures_dir.exists():
        print(f"❌ ERROR: Fixtures directory not found: {fixtures_dir}")
        return 1
    
    print(f"📁 Fixtures: {fixtures_dir}")
    
    # Find JSON files
    json_files = sorted(fixtures_dir.glob("invoice_*.json"))
    
    if not json_files:
        print("❌ No JSON fixture files found")
        return 1
    
    print(f"📋 Found {len(json_files)} JSON templates")
    
    # Determine size based on template
    size_map = {
        "colombian": A4,
        "mexican": letter,
        "spanish": A4,
        "minimal": A4,
        "complex": A4
    }
    
    pdf_count = 0
    error_count = 0
    
    for json_file in json_files:
        print(f"\n📝 Processing: {json_file.name}")
        
        try:
            template = load_template(json_file)
            
            # Get PDF content
            pdf_content = template.get("pdf_content", "")
            if not pdf_content:
                print(f"  ⚠️  No pdf_content found, using synthetic content")
                # Generate synthetic content from structured data
                lines = []
                lines.append(f"Invoice #: {template.get('invoice_number', 'TBD')}")
                lines.append("Bill To:")
                lines.append(template.get("client_name", "TBD"))
                lines.append(f"Total: ${template.get('amount', 0):,.2f}")
                lines.append(f"Due Date: {template.get('due_date', 'TBD')}")
                
                items = template.get("items", [])
                if items:
                    lines.append("")
                    lines.append("Items:")
                    for item in items:
                        lines.append(f"  {item.get('description', 'Service')}: "
                                   f"${item.get('price', 0):.2f} x {item.get('quantity', 1)}")
                
                pdf_content = "\\n".join(lines)
            
            # Determine size from filename
            size = A4  # Default
            for key, val in size_map.items():
                if key in json_file.name.lower():
                    size = val
                    break
            
            # Create PDF
            pdf_path = json_file.with_suffix(".pdf")
            generate_text_pdf(pdf_content, pdf_path, size)
            pdf_count += 1
            
            print(f"  ✓ Generated: {pdf_path.name}")
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            error_count += 1
            continue
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 GENERATION SUMMARY")
    print("=" * 70)
    print(f"  ✅ PDFs Generated: {pdf_count}")
    print(f"  ❌ Errors: {error_count}")
    
    if error_count == 0:
        print("\n🎉 All PDFs generated successfully!")
        return 0
    else:
        print("\n⚠️  Some PDFs failed to generate")
        return 1


if __name__ == "__main__":
    sys.exit(main())