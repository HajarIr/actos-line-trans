"""
PDF quote generator — Actos Line Trans

Uses ReportLab. Builds a single-page A4 quote in the company's teal/gold colors.
The output is an in-memory BytesIO that FastAPI streams to the client.
"""

import io
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle


TEAL = colors.HexColor("#008E9B")
GOLD = colors.HexColor("#EBA31E")
LIGHT = colors.HexColor("#F3F8F9")
DARK = colors.HexColor("#1f2937")


def build_quote_pdf(lead, breakdown, currency_info=None):
    """Render a quote PDF and return BytesIO ready for streaming.

    `lead`       SQLAlchemy History row (or any object with .id, .origin, ...)
    `breakdown`  dict from calculate_price()
    `currency_info`  optional dict {"code": "EUR", "symbol": "€", "rate": 0.092}
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # ---- Header band
    c.setFillColor(TEAL)
    c.rect(0, H - 28*mm, W, 28*mm, fill=True, stroke=False)

    # Logo block (no image — pure vector)
    c.setFillColor(GOLD)
    c.roundRect(15*mm, H - 23*mm, 18*mm, 18*mm, 3*mm, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(24*mm, H - 16*mm, "AL")

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40*mm, H - 14*mm, "ACTOS LINE TRANS")
    c.setFont("Helvetica", 9)
    c.drawString(40*mm, H - 19*mm, "International Logistics — Fresh Produce Export")
    c.drawString(40*mm, H - 23*mm, "Agadir, Morocco")

    # Quote number on the right
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(W - 15*mm, H - 14*mm, f"QUOTE #{getattr(lead, 'id', '—')}")
    date_str = (lead.date if getattr(lead, "date", None) else datetime.datetime.utcnow()).strftime("%Y-%m-%d %H:%M")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - 15*mm, H - 19*mm, f"Date: {date_str}")

    # ---- Customer block
    y = H - 40*mm
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(15*mm, y, "BILL TO")
    c.setFont("Helvetica", 10)
    c.drawString(15*mm, y - 5*mm, getattr(lead, "customer_name", "") or "—")
    c.drawString(15*mm, y - 9*mm, getattr(lead, "contact_number", "") or "—")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(110*mm, y, "SHIPMENT")
    c.setFont("Helvetica", 10)
    c.drawString(110*mm, y - 5*mm, f"Route: {lead.origin} -> {lead.destination}")
    dist_line = f"Distance: {breakdown.get('distance_km', '-')} km"
    if breakdown.get("trip_days"):
        dist_line += f"  (~{breakdown['trip_days']} day(s))"
    c.drawString(110*mm, y - 9*mm, dist_line)
    c.drawString(110*mm, y - 13*mm, f"Product: {breakdown.get('product_type', getattr(lead,'product_type','-'))}")
    cold = "Refrigerated (cold chain)" if breakdown.get("refrigerated") else "Standard"
    c.drawString(110*mm, y - 17*mm, f"Transport: {cold}")
    weight_line = f"Weight: {lead.weight} kg"
    if breakdown.get("shipment_type"):
        weight_line += f"  -  {breakdown['shipment_type']}"
    c.drawString(110*mm, y - 21*mm, weight_line)

    # ---- Line items table
    y_table = y - 32*mm

    cur_symbol = "MAD"
    cur_factor = 1.0
    if currency_info:
        cur_symbol = currency_info.get("symbol", "MAD")
        cur_factor = float(currency_info.get("rate", 1.0))

    def fmt(amount):
        return f"{cur_symbol} {amount * cur_factor:,.2f}"

    b = breakdown
    dist = b.get("distance_km", "-")

    if b.get("cost_before_margin") is not None:
        # ---- detailed cost-based breakdown (new pricing engine) ----
        rows = [["Description", "Detail", "Amount"]]
        # Operating costs
        rows.append(["Fixed cost share", "per-trip allocation", fmt(b["fixed_per_trip"])])
        fuel_detail = f"{dist} km" + (" incl. reefer" if b.get("cold_fee", 0) > 0 else "")
        rows.append(["Fuel (gasoil)", fuel_detail, fmt(b["gasoil_cost"])])
        rows.append(["Tolls (peage)", f"{dist} km", fmt(b["toll_cost"])])
        rows.append(["Maintenance & tires", f"{dist} km", fmt(b["maintenance_cost"])])
        rows.append(["Driver allowance", f"{b.get('trip_days', 1)} day(s)", fmt(b["driver_cost"])])
        if b.get("ferry_cost", 0) > 0:
            rows.append(["Ferry (Strait)", "round trip", fmt(b["ferry_cost"])])
        if b.get("customs_cost", 0) > 0:
            rows.append(["Customs & transit", "diwana dossier", fmt(b["customs_cost"])])
        rows.append(["Misc fees", "parking, weighing", fmt(b["misc_cost"])])
        # Surcharges
        if b.get("product_fee", 0) > 0:
            rows.append(["Perishable handling", f"perishability x{b.get('perishability', 1.0)}", fmt(b["product_fee"])])
        if b.get("fragile_fee", 0) > 0:
            rows.append(["Fragile (+10%)", "careful handling", fmt(b["fragile_fee"])])
        if b.get("dangerous_fee", 0) > 0:
            rows.append(["Dangerous goods (+20%)", "ADR handling", fmt(b["dangerous_fee"])])
        if b.get("urgent_fee", 0) > 0:
            rows.append(["Urgent / express (+30%)", "priority crew", fmt(b["urgent_fee"])])

        # Per-truck cost = sum of everything above (one full truck)
        one_truck = (b["fixed_per_trip"] + b["gasoil_cost"] + b["toll_cost"]
                     + b["maintenance_cost"] + b["driver_cost"] + b.get("ferry_cost", 0)
                     + b.get("customs_cost", 0) + b["misc_cost"] + b.get("product_fee", 0)
                     + b.get("fragile_fee", 0) + b.get("dangerous_fee", 0) + b.get("urgent_fee", 0))
        trucks = b.get("trucks_needed", 1)
        load = b.get("load_factor", 1.0)
        if trucks and trucks > 1:
            rows.append(["", "Per-truck cost", fmt(one_truck)])
            rows.append(["", f"x {trucks} trucks", fmt(b["cost_before_margin"])])
        elif load and load < 1.0:
            rows.append(["", "Full-truck cost", fmt(one_truck)])
            rows.append(["", f"Groupage share (x{load})", fmt(b["cost_before_margin"])])
        else:
            rows.append(["", "Cost subtotal", fmt(b["cost_before_margin"])])

        margin_pct = int(round(b.get("margin_pct", 0) * 100))
        rows.append(["", f"Margin (+{margin_pct}%)", fmt(b["margin_amount"])])
        rows.append(["", "TOTAL", fmt(b["total_price"])])
    else:
        # ---- legacy fallback (old stored quotes) ----
        rows = [
            ["Description", "Detail", "Amount"],
            ["Base rate", "Cross-border" if b.get("cross_border") else "Domestic", fmt(b["base_rate"])],
            ["Gasoil (fuel)", f"{dist} km", fmt(b["gasoil_cost"])],
            ["Diwana (customs)", f"{lead.weight} kg", fmt(b.get("diwana_cost", 0))],
            ["Product surcharge", f"perishability x{b.get('perishability', 1.0)}", fmt(b["product_fee"])],
        ]
        if b.get("cold_fee", 0) > 0:
            rows.append(["Cold chain", "Refrigerated reefer", fmt(b["cold_fee"])])
        rows.append(["", "TOTAL", fmt(b["total_price"])])

    table = Table(rows, colWidths=[60*mm, 75*mm, 45*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 10),
        ("ALIGN",       (2, 0), (2, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT]),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.3, colors.HexColor("#cbd5e1")),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        # margin row (second to last): gold + bold + separator above
        ("FONTNAME",    (0, -2), (-1, -2), "Helvetica-Bold"),
        ("TEXTCOLOR",   (1, -2), (2, -2), GOLD),
        ("LINEABOVE",   (0, -2), (-1, -2), 0.6, colors.HexColor("#94a3b8")),
        # total row (last): gold band
        ("BACKGROUND",  (0, -1), (-1, -1), GOLD),
        ("TEXTCOLOR",   (0, -1), (-1, -1), colors.white),
        ("FONTNAME",    (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, -1), (-1, -1), 12),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))

    tw, th = table.wrapOn(c, W - 30*mm, H)
    table.drawOn(c, 15*mm, y_table - th)

    y_after = y_table - th - 10*mm

    # If currency conversion was applied, show the MAD reference
    if currency_info and currency_info.get("code") and currency_info["code"] != "MAD":
        c.setFillColor(DARK)
        c.setFont("Helvetica-Oblique", 9)
        c.drawRightString(W - 15*mm, y_after, f"Reference: {breakdown['total_price']:,.2f} MAD (rate 1 MAD = {cur_factor} {currency_info['code']})")
        y_after -= 6*mm

    # ---- Terms
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15*mm, y_after, "Terms & Conditions")
    c.setFont("Helvetica", 8)
    terms = [
        "1. Quote valid for 7 days from issue date.",
        "2. Prices expressed in Moroccan Dirham (MAD); foreign currency totals are indicative.",
        "3. Estimate covers fuel, tolls, maintenance, driver, ferry and operating costs, plus the company margin.",
        "4. Cold chain surcharge reflects the extra fuel of a refrigerated truck; mandatory for perishable goods (EU rules).",
        "5. Customs & transit fees are estimated; actual duties may vary based on the official tariff at clearance.",
        "6. Transport insurance optional; ask the commercial team for a separate quote.",
    ]
    for i, t in enumerate(terms):
        c.drawString(15*mm, y_after - (i + 1) * 4*mm, t)

    # ---- Footer
    c.setFillColor(TEAL)
    c.rect(0, 0, W, 12*mm, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 8)
    c.drawString(15*mm, 5*mm, "Actos Line Trans S.A.R.L. — RC: 12345 — Agadir, Morocco")
    c.drawRightString(W - 15*mm, 5*mm, "Generated automatically by the Actos quote system")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf
