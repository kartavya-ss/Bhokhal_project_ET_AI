"""
Generates the synthetic Meridian Pharmaceuticals dataset.
Run once to populate /home/claude/meridian/data/ with PDFs, Excel, email txt, and a P&ID image.
Replace these with your real 18 files later -- ingestion pipeline doesn't care about the source.
"""
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont

DATA_DIR = "/home/claude/meridian/data"
os.makedirs(DATA_DIR, exist_ok=True)

styles = getSampleStyleSheet()

def make_pdf(filename, title, paragraphs, table_data=None):
    path = os.path.join(DATA_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=letter)
    flow = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for p in paragraphs:
        flow.append(Paragraph(p, styles["Normal"]))
        flow.append(Spacer(1, 8))
    if table_data:
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ]))
        flow.append(Spacer(1, 12))
        flow.append(t)
    doc.build(flow)
    print(f"Wrote {path}")

# ---------------------------------------------------------------------------
# 1. BMR - Batch MP-PCM-2602 (the FAILED batch)
# ---------------------------------------------------------------------------
make_pdf(
    "BMR_MP-PCM-2602.pdf",
    "Batch Manufacturing Record - Batch MP-PCM-2602",
    [
        "Product: Paracetamol Tablets 500mg. Batch Number: MP-PCM-2602. "
        "Manufacturing Date: 2026-02-14. Compression Machine: TCM-04. "
        "Operator of Record: Priya Nair. Shift Supervisor: Rajesh Kumar.",

        "In-process quality check performed at 11:40 AM on 2026-02-14 by operator Priya Nair. "
        "Tablet weight check failed: average tablet weight recorded at 612mg against a specification "
        "range of 580-600mg. Batch MP-PCM-2602 was placed on HOLD pending investigation.",

        "Deviation was immediately raised and logged as DEV-2602-001. Machine TCM-04 was taken offline "
        "for inspection following the failed weight check.",

        "Reference SOP: ENG-007 (Preventive Maintenance of Tablet Compression Machines). "
        "Reference Deviation Report: DEV-2602-001.",
    ],
)

# ---------------------------------------------------------------------------
# 2. BMR - Batch MP-PCM-2601 (a PASSED control batch, different machine)
# ---------------------------------------------------------------------------
make_pdf(
    "BMR_MP-PCM-2601.pdf",
    "Batch Manufacturing Record - Batch MP-PCM-2601",
    [
        "Product: Paracetamol Tablets 500mg. Batch Number: MP-PCM-2601. "
        "Manufacturing Date: 2026-02-10. Compression Machine: TCM-02. "
        "Operator of Record: Suresh Iyer. Shift Supervisor: Rajesh Kumar.",

        "In-process quality check performed at 10:15 AM on 2026-02-10. Average tablet weight recorded "
        "at 591mg, within the specification range of 580-600mg. Batch MP-PCM-2601 PASSED all in-process "
        "checks and was released to packaging.",

        "No deviations were raised for this batch. Machine TCM-02 had completed its scheduled preventive "
        "maintenance on 2026-01-28 per SOP ENG-007.",
    ],
)

# ---------------------------------------------------------------------------
# 3. Deviation Report DEV-2602-001
# ---------------------------------------------------------------------------
make_pdf(
    "Deviation_Report_DEV-2602-001.pdf",
    "Deviation Report DEV-2602-001",
    [
        "Deviation Number: DEV-2602-001. Related Batch: MP-PCM-2602. Date Raised: 2026-02-14. "
        "Raised By: Priya Nair. Category: In-process quality check failure - tablet weight out of specification.",

        "Description: During routine in-process weight verification, tablets produced on Machine TCM-04 "
        "were found to average 612mg, exceeding the upper specification limit of 600mg. Operator Priya Nair "
        "immediately halted the compression run and notified Shift Supervisor Rajesh Kumar.",

        "Root Cause Investigation: Maintenance Engineer Anita Desai inspected Machine TCM-04 on 2026-02-15 "
        "and identified a worn punch tip in station 6 of the upper punch set, along with visible degraded "
        "punch tooling causing inconsistent fill depth. Wear and tear on the punch assembly beyond acceptable "
        "tolerance was confirmed as the direct root cause.",

        "Underlying Cause: Cross-reference with the Machine TCM-04 maintenance history showed that the "
        "scheduled preventive maintenance checkup mandated by SOP ENG-007 (due 2026-01-30) had been missed. "
        "The maintenance team, led by Suresh Iyer, had not performed the punch inspection and replacement "
        "cycle required at the 90-day interval.",

        "Corrective and Preventive Action (CAPA): Replace worn punch tooling on TCM-04. Reinforce scheduling "
        "compliance for SOP ENG-007 across all compression machines. Batch MP-PCM-2602 was rejected and "
        "will not be released.",
    ],
)

# ---------------------------------------------------------------------------
# 4. SOP ENG-007
# ---------------------------------------------------------------------------
make_pdf(
    "SOP_ENG-007_Maintenance.pdf",
    "SOP ENG-007: Preventive Maintenance of Tablet Compression Machines",
    [
        "SOP Number: ENG-007. Scope: All tablet compression machines (TCM-01 through TCM-06) at the "
        "Meridian Pharmaceuticals manufacturing facility.",

        "Requirement: Every compression machine must undergo a full preventive maintenance checkup, "
        "including punch and die inspection, every 90 days. Punches showing wear beyond tolerance must "
        "be replaced before the machine is returned to production.",

        "Responsible Party: Maintenance Team, under supervision of Maintenance Engineer Anita Desai. "
        "Maintenance Technician Suresh Iyer is responsible for logging checkup completion in the "
        "Machine Maintenance Log.",

        "Non-compliance with this SOP has historically been linked to tablet weight and hardness "
        "deviations due to degraded punch tooling.",
    ],
)

# ---------------------------------------------------------------------------
# 5. Excel - Operator Training Records
# ---------------------------------------------------------------------------
wb = Workbook()
ws = wb.active
ws.title = "Training Records"
ws.append(["Employee Name", "Role", "Training Course", "Completion Date", "Certified For Machine"])
rows = [
    ("Priya Nair", "Operator", "Tablet Compression Operation - Level 2", "2025-11-05", "TCM-04"),
    ("Priya Nair", "Operator", "In-Process Quality Checks", "2025-11-12", "All Compression Machines"),
    ("Suresh Iyer", "Maintenance Technician", "Punch & Die Maintenance", "2025-09-20", "All Compression Machines"),
    ("Anita Desai", "Maintenance Engineer", "SOP ENG-007 Certification", "2025-08-15", "All Compression Machines"),
    ("Rajesh Kumar", "Shift Supervisor", "Deviation Management QA-015", "2025-07-01", "N/A"),
]
for r in rows:
    ws.append(r)
wb.save(os.path.join(DATA_DIR, "Training_Records.xlsx"))
print("Wrote Training_Records.xlsx")

# ---------------------------------------------------------------------------
# 6. Email thread (plain text)
# ---------------------------------------------------------------------------
email_text = """From: Priya Nair
To: Rajesh Kumar
Subject: URGENT - Batch MP-PCM-2602 weight check failed
Date: 2026-02-14 11:45 AM

Rajesh,

Flagging immediately - the 11:40 AM in-process weight check on Batch MP-PCM-2602
(Machine TCM-04) came back at 612mg average, well above our 600mg upper limit.
I've stopped the run and put the batch on hold. Raising a deviation now (DEV-2602-001).

- Priya

---

From: Rajesh Kumar
To: Priya Nair, Anita Desai
Subject: RE: URGENT - Batch MP-PCM-2602 weight check failed
Date: 2026-02-14 12:10 PM

Priya, good catch, thanks for stopping it fast.

Anita - can you get TCM-04 inspected first thing tomorrow? We need root cause before
we can even think about disposition on this batch. Pulling the maintenance log now.

- Rajesh

---

From: Anita Desai
To: Rajesh Kumar, Priya Nair
Subject: RE: URGENT - Batch MP-PCM-2602 weight check failed
Date: 2026-02-15 09:30 AM

Team,

Inspected TCM-04 this morning. Found a worn punch tip at station 6, and general
degraded punch tooling across the upper punch set - that's almost certainly why fill
depth was off and tablets came out overweight.

Checked the maintenance history - this machine's ENG-007 checkup was due 2026-01-30
and was never completed. Suresh's team missed the scheduled window. That's the
underlying cause here, not just a random tooling failure.

Writing this up in DEV-2602-001. Recommending we replace the punch set and tighten
up scheduling compliance for ENG-007 across all machines, not just TCM-04.

- Anita
"""
with open(os.path.join(DATA_DIR, "Email_Thread_2602.txt"), "w") as f:
    f.write(email_text)
print("Wrote Email_Thread_2602.txt")

# ---------------------------------------------------------------------------
# 7. P&ID image with equipment tag (simple synthetic diagram)
# ---------------------------------------------------------------------------
img = Image.new("RGB", (900, 600), "white")
draw = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
except Exception:
    font = ImageFont.load_default()
    small_font = font

draw.rectangle([50, 50, 850, 550], outline="black", width=3)
draw.text((300, 20), "P&ID - Tablet Compression Line 4", fill="black", font=font)

# Machine boxes
draw.rectangle([100, 150, 300, 280], outline="black", width=2)
draw.text((130, 200), "TCM-04", fill="black", font=font)
draw.text((110, 290), "Tablet Compression Machine 4", fill="black", font=small_font)

draw.rectangle([400, 150, 600, 280], outline="black", width=2)
draw.text((430, 200), "HOPPER-4", fill="black", font=small_font)

draw.rectangle([650, 150, 800, 280], outline="black", width=2)
draw.text((665, 200), "DEDUST-4", fill="black", font=small_font)

# Piping/flow arrows
draw.line([300, 215, 400, 215], fill="black", width=3)
draw.line([600, 215, 650, 215], fill="black", width=3)

draw.text((100, 400), "Feed line from Granulation -> Hopper -> TCM-04 -> Dedusting -> Coating", fill="black", font=small_font)
draw.text((100, 450), "Machine ID Tag: TCM-04  |  Line: 4  |  Area: Tablet Compression Suite", fill="black", font=small_font)

img.save(os.path.join(DATA_DIR, "PID_TCM04_Line4.png"))
print("Wrote PID_TCM04_Line4.png")

print("\nAll sample source documents generated in", DATA_DIR)
