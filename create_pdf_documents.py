#!/usr/bin/env python3
"""
Create PDF documents from policy content using reportlab
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from pathlib import Path

def create_doc_1_pdf():
    """Create Global Entertainment & Client Relations Policy PDF"""

    pdf_path = "/home/stu/Projects/intuition-api/test_docs/Global_Entertainment_Client_Relations_Policy.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#333333'),
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )

    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        leading=12
    )

    story = []

    # Title
    story.append(Paragraph("ZENITH CORPORATION", title_style))
    story.append(Paragraph("Global Entertainment & Client Relations Policy", title_style))
    story.append(Spacer(1, 0.3*inch))

    # Header info
    story.append(Paragraph("<b>Effective Date:</b> January 1, 2025", body_style))
    story.append(Paragraph("<b>Policy Number:</b> ZEN-CLP-2025-01", body_style))
    story.append(Paragraph("<b>Classification:</b> GLOBAL - APPLIES TO ALL REGIONS", body_style))
    story.append(Spacer(1, 0.2*inch))

    # Executive Summary
    story.append(Paragraph("1. EXECUTIVE SUMMARY", heading_style))
    summary_text = """This policy establishes standards for employee engagement with clients in social and entertainment
    settings. All Zenith employees are authorized to conduct client entertainment within the parameters established
    by this policy. This policy applies to all geographic regions worldwide unless superseded by regional addendums."""
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 0.15*inch))

    # Section 1
    story.append(Paragraph("2. SCOPE AND APPLICABILITY", heading_style))
    story.append(Paragraph("<b>Section 2.1 Geographic Scope: GLOBAL</b>", body_style))
    scope_text = """This policy applies to all employees, contractors, and representatives of Zenith Corporation
    worldwide, including:<br/>
    • North America (USA, Canada, Mexico)<br/>
    • Europe (EU and non-EU countries)<br/>
    • Asia-Pacific Region<br/>
    • Middle East<br/>
    • Africa<br/>
    • All other geographies"""
    story.append(Paragraph(scope_text, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Section 2 - Permitted Activities
    story.append(Paragraph("3. PERMITTED ENTERTAINMENT ACTIVITIES", heading_style))
    story.append(Paragraph(
        "The following entertainment activities are explicitly PERMITTED under this global policy:",
        body_style
    ))

    permitted = """<b>Section 3.1 Dining & Beverages:</b><br/>
    • Restaurant meals (any cuisine type)<br/>
    • Cocktail bars and lounges<br/>
    • Wine and spirits tastings<br/>
    • Coffee and tea venues<br/>
    • Hotel dining experiences<br/>
    <br/>
    <b>Section 3.2 Sports & Recreation:</b><br/>
    • Golf outings<br/>
    • Tennis facilities<br/>
    • Basketball courts<br/>
    • Swimming facilities<br/>
    • Ski resorts<br/>
    • Water sports (boating, sailing)<br/>
    <br/>
    <b>Section 3.3 Cultural Activities:</b><br/>
    • Theater and performing arts<br/>
    • Museums and galleries<br/>
    • Movie theaters<br/>
    • Concert venues<br/>
    • Historical site tours<br/>
    • Art festivals"""
    story.append(Paragraph(permitted, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Approval section
    story.append(Paragraph("4. AUTHORIZATION LEVELS", heading_style))
    auth_text = """<b>Section 4.1 Standard employee approval authority:</b><br/>
    • Employees may approve entertainment activities up to USD 500 per event<br/>
    • Managers may approve up to USD 1,500 per event<br/>
    • Director approval required for USD 1,500-5,000<br/>
    • VP approval required for USD 5,000+"""
    story.append(Paragraph(auth_text, body_style))
    story.append(Spacer(1, 0.2*inch))

    # Signatures
    story.append(Paragraph("5. APPROVAL AUTHORITY", heading_style))
    story.append(Paragraph("Global Chief Compliance Officer: Sarah Mitchell", body_style))
    story.append(Paragraph("Global CFO: Robert Chen", body_style))
    story.append(Paragraph("CEO: Margaret Williams", body_style))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("<b>Last Revised:</b> January 1, 2025", body_style))

    doc.build(story)
    return pdf_path

def create_doc_2_pdf():
    """Create Asia-Pacific Regional Addendum PDF"""

    pdf_path = "/home/stu/Projects/intuition-api/test_docs/Regional_Addendum_APAC_High_Risk_Activities.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#333333'),
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )

    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=9,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        leading=11
    )

    critical_style = ParagraphStyle(
        'Critical',
        parent=styles['BodyText'],
        fontSize=9,
        textColor=colors.red,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )

    story = []

    # Title
    story.append(Paragraph("ZENITH CORPORATION", title_style))
    story.append(Paragraph("Asia-Pacific Region: Prohibited High-Risk Entertainment Activities", title_style))
    story.append(Paragraph("Regional Addendum to Global Entertainment Policy", body_style))
    story.append(Spacer(1, 0.2*inch))

    # Header
    story.append(Paragraph("<b>Effective Date:</b> January 1, 2025", body_style))
    story.append(Paragraph("<b>Policy Number:</b> ZEN-CLP-APAC-2025-01", body_style))
    story.append(Paragraph("<b>Geographic Scope:</b> ASIA-PACIFIC REGION ONLY", body_style))
    story.append(Spacer(1, 0.15*inch))

    # CRITICAL scope statement
    critical_text = """CRITICAL: This addendum applies ONLY to the following APAC countries:<br/>
    • China (PRC)<br/>
    • Japan<br/>
    • South Korea<br/>
    • Taiwan<br/>
    • Vietnam<br/>
    • Indonesia<br/>
    • Thailand<br/>
    • Malaysia<br/>
    • Philippines<br/>
    • Singapore"""
    story.append(Paragraph(critical_text, critical_style))
    story.append(Spacer(1, 0.1*inch))

    not_applies = """<b><font color="red">This addendum does NOT apply to: Europe, North America, Middle East, Africa,
    or any other non-APAC regions.</font></b>"""
    story.append(Paragraph(not_applies, body_style))
    story.append(Spacer(1, 0.15*inch))

    # Executive Summary
    story.append(Paragraph("1. EXECUTIVE SUMMARY", heading_style))
    summary_text = """This addendum modifies the Global Entertainment & Client Relations Policy specifically for
    the Asia-Pacific region. Due to regulatory, cultural, and business-specific considerations in APAC, certain
    entertainment activities are PROHIBITED in this region, even though they may be permitted globally."""
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Section 1 - Prohibited Activities
    story.append(Paragraph("2. PROHIBITED ENTERTAINMENT ACTIVITIES IN APAC REGION", heading_style))
    story.append(Paragraph("Section 2.1 Explicitly Prohibited Activities:", body_style))

    prohibited = """<b>2.1.1 KARAOKE VENUES (STRICTLY PROHIBITED)</b><br/>
    • Private karaoke bars<br/>
    • Karaoke lounges<br/>
    • Entertainment complexes featuring karaoke<br/>
    • Establishment of any type where karaoke is primary activity<br/>
    <br/>
    <font color="red"><b>Reason for Prohibition:</b> APAC regulatory environment. Certain karaoke establishments
    in the region operate under questionable legal structures and may involve improper inducements. Zenith employees
    must avoid any appearance of impropriety.</font><br/>
    <br/>
    <b>Prohibited in:</b> China, Japan, South Korea, Vietnam, Indonesia, Thailand, Malaysia<br/>
    <b>NOT Prohibited in:</b> Europe, Americas, Middle East, Africa<br/>
    <br/>
    <b>2.1.2 NIGHTCLUB ENTERTAINMENT (Late-Night)</b><br/>
    • Nightclubs and dance clubs<br/>
    • Discotheques with adult entertainment<br/>
    • Late-night entertainment venues (operating after 11 PM)<br/>
    <br/>
    <b>Prohibited in:</b> China, Japan, South Korea, Vietnam, Indonesia, Thailand<br/>
    <br/>
    <b>2.1.3 HOSTESS BARS AND ADULT ENTERTAINMENT</b><br/>
    • Any venue with hostess services<br/>
    • Adult entertainment venues<br/>
    • Escort service coordination<br/>
    • Any activity involving hired companions for entertainment<br/>
    <br/>
    <b>2.1.4 GAMBLING FACILITIES</b><br/>
    • Casinos<br/>
    • Gambling establishments<br/>
    • Gaming venues<br/>
    • Betting parlors<br/>
    <br/>
    <b>Prohibited in:</b> China, Vietnam, Indonesia, Malaysia"""
    story.append(Paragraph(prohibited, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Permitted in APAC
    story.append(Paragraph("3. PERMITTED ACTIVITIES IN APAC REGION", heading_style))
    permitted = """The following activities ARE permitted in APAC (per Global Policy):<br/>
    • Fine dining restaurants<br/>
    • Golf outings<br/>
    • Museum visits and cultural events<br/>
    • Theater and performing arts<br/>
    • Hotel business dining<br/>
    • Team activities<br/>
    • Business conferences and seminars"""
    story.append(Paragraph(permitted, body_style))
    story.append(Spacer(1, 0.15*inch))

    # Violations
    story.append(Paragraph("4. ENFORCEMENT", heading_style))
    violations = """<b>APAC-Specific Enforcement:</b><br/>
    • First violation: Mandatory retraining + written warning<br/>
    • Second violation: Suspension of entertainment privileges<br/>
    • Third violation: Disciplinary action up to immediate termination"""
    story.append(Paragraph(violations, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Approval
    story.append(Paragraph("5. APPROVAL AUTHORITY", heading_style))
    story.append(Paragraph("APAC Regional President: David Liu", body_style))
    story.append(Paragraph("APAC Regional Compliance Officer: Jennifer Wong", body_style))
    story.append(Paragraph("Global Chief Compliance Officer: Sarah Mitchell", body_style))

    doc.build(story)
    return pdf_path

def create_doc_3_pdf():
    """Create Global Business Travel & Expenses Policy PDF"""

    pdf_path = "/home/stu/Projects/intuition-api/test_docs/Global_Business_Travel_Entertainment_Expenses_Policy.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#333333'),
        spaceAfter=6,
        fontName='Helvetica-Bold'
    )

    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=9,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        leading=11
    )

    story = []

    # Title
    story.append(Paragraph("ZENITH CORPORATION", title_style))
    story.append(Paragraph("Global Business Travel & Entertainment Expenses Policy", title_style))
    story.append(Spacer(1, 0.2*inch))

    # Header
    story.append(Paragraph("<b>Policy Number:</b> ZEN-TRAVEL-2025-01", body_style))
    story.append(Paragraph("<b>Classification:</b> GLOBAL - APPLIES TO ALL REGIONS", body_style))
    story.append(Paragraph("<b>Effective Date:</b> January 1, 2025", body_style))
    story.append(Spacer(1, 0.15*inch))

    # Executive Summary
    story.append(Paragraph("1. EXECUTIVE SUMMARY", heading_style))
    summary_text = """This policy governs business travel and entertainment expenses for all Zenith Corporation
    employees worldwide. This policy works in conjunction with the Global Entertainment & Client Relations
    Policy and regional addendums."""
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Section 1
    story.append(Paragraph("2. ENTERTAINMENT EXPENSE CATEGORIES", heading_style))
    categories = """Entertainment expenses are categorized as:<br/>
    • <b>Client Entertainment:</b> Meals and activities with external clients<br/>
    • <b>Team Building:</b> Internal employee activities<br/>
    • <b>Business Development:</b> Prospecting and networking<br/>
    • <b>Relationship Maintenance:</b> Ongoing client engagement"""
    story.append(Paragraph(categories, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Approval Matrix
    story.append(Paragraph("3. GLOBAL APPROVAL MATRIX", heading_style))
    approval_text = """<b>Global Standard Requirements:</b><br/>
    • Under USD 100: No approval required<br/>
    • USD 100-500: Manager approval required<br/>
    • USD 500-1,500: Director approval required<br/>
    • USD 1,500-5,000: VP approval required<br/>
    • Over USD 5,000: C-Suite approval (CFO or CEO)<br/>
    <br/>
    <b><font color="red">APAC Region Exception:</font></b><br/>
    <b><font color="red">In Asia-Pacific region, the following modifications apply:</font></b><br/>
    • <b><font color="red">Under USD 300: Manager approval required (vs. no approval globally)</font></b><br/>
    • <b><font color="red">USD 300-1,000: VP approval required (vs. Manager globally)</font></b><br/>
    • <b><font color="red">ALL APAC expenses require Finance pre-approval regardless of amount</font></b>"""
    story.append(Paragraph(approval_text, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Section 4
    story.append(Paragraph("4. NON-REIMBURSABLE ITEMS", heading_style))
    non_reimbursable = """The following are never reimbursable:<br/>
    • Personal entertainment (movies, concerts for self only)<br/>
    • Alcohol for personal consumption<br/>
    • Activities that violate regional addendums<br/>
    • Expenses at prohibited venues<br/>
    • Spousal or family member entertainment<br/>
    • Gambling losses"""
    story.append(Paragraph(non_reimbursable, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Section 5 - CRITICAL
    story.append(Paragraph("5. REGIONAL POLICY INTEGRATION", heading_style))
    critical_integration = """<b><font color="red">CRITICAL: Where regional addendums exist, they take precedence:</font></b><br/>
    • Asia-Pacific addendum supersedes this policy on prohibited activities<br/>
    • Regional restrictions are MORE restrictive than global policy<br/>
    • Employees must follow most restrictive applicable policy<br/>
    <br/>
    <b>CRITICAL EXAMPLE:</b><br/>
    • Karaoke is not explicitly prohibited in this global policy<br/>
    • APAC addendum EXPLICITLY PROHIBITS karaoke in APAC<br/>
    • Therefore: Karaoke is PERMITTED globally but PROHIBITED in APAC<br/>
    • Similarly: Karaoke is PERMITTED in Germany (not in APAC scope)"""
    story.append(Paragraph(critical_integration, body_style))
    story.append(Spacer(1, 0.1*inch))

    # Section 6
    story.append(Paragraph("6. DOCUMENTATION REQUIREMENTS", heading_style))
    docs = """All expenses must include:<br/>
    • Receipt or invoice<br/>
    • Business purpose (2-3 sentences minimum)<br/>
    • Client name and organization<br/>
    • Date and location of entertainment<br/>
    • All attendees (names and titles)<br/>
    • Employee name and department"""
    story.append(Paragraph(docs, body_style))
    story.append(Spacer(1, 0.2*inch))

    # Signatures
    story.append(Paragraph("7. APPROVAL AUTHORITY", heading_style))
    story.append(Paragraph("Global CFO: Robert Chen", body_style))
    story.append(Paragraph("Global Chief Compliance Officer: Sarah Mitchell", body_style))
    story.append(Paragraph("CEO: Margaret Williams", body_style))
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph("<b>Effective Date:</b> January 1, 2025", body_style))

    doc.build(story)
    return pdf_path

def main():
    """Create all PDF documents"""
    print("Creating PDF test documents...\n")

    print("Creating Document 1: Global Entertainment & Client Relations Policy...")
    path1 = create_doc_1_pdf()
    print(f"✓ Created: {path1}")

    print("\nCreating Document 2: Asia-Pacific Regional Addendum...")
    path2 = create_doc_2_pdf()
    print(f"✓ Created: {path2}")

    print("\nCreating Document 3: Global Business Travel & Expenses Policy...")
    path3 = create_doc_3_pdf()
    print(f"✓ Created: {path3}")

    print("\n" + "="*70)
    print("PDF DOCUMENTS CREATED SUCCESSFULLY")
    print("="*70)

    # Verify files
    from pathlib import Path
    test_docs_dir = Path("/home/stu/Projects/intuition-api/test_docs")
    pdfs = list(test_docs_dir.glob("*.pdf"))

    print(f"\nPDF Files Ready for Upload ({len(pdfs)} total):")
    for pdf in pdfs:
        size_kb = pdf.stat().st_size / 1024
        print(f"  ✓ {pdf.name} ({size_kb:.1f} KB)")

    return len(pdfs) >= 3

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
