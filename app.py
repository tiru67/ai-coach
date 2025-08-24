# app.py
import os
import io
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime
from typing import Dict, List

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# -----------------------------
# Config
# -----------------------------
st.set_page_config(page_title="AI Coach – Business Diagnostic", page_icon="🧭", layout="centered")

APP_NAME = "AI Coach – Business Diagnostic"
PRICE_MYR = 99
CSV_DB = "leads_db.csv"  # mock CRM storage (CSV)

# Optional integrations via env (left empty -> demo mode)
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
CALENDLY_URL = os.getenv("CALENDLY_URL", "https://calendly.com/")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

# -----------------------------
# Referral Tracking (UTM / ref)
# -----------------------------
def get_referral() -> Dict[str, str]:
    try:
        qp = st.query_params  # Streamlit >= 1.30
    except Exception:
        qp = st.experimental_get_query_params()  # fallback
    fields = {}
    for k in ["ref", "utm_source", "utm_medium", "utm_campaign"]:
        v = qp.get(k, [""])[0] if isinstance(qp.get(k), list) else qp.get(k, "")
        fields[k] = v or ""
    return fields

# -----------------------------
# Mock Auth (demo)
# -----------------------------
def init_state():
    defaults = dict(
        stage="landing",  # landing -> pay -> auth -> survey -> report -> done
        user_email="",
        user_name="",
        user_phone="",
        referral=get_referral(),
        answers={},  # {"q_key": {"score": int, "note": str}}
        paid=False,
        report_pdf_bytes=None,
        lead_id="",
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# -----------------------------
# Compass Questions
# -----------------------------
QUESTIONS = [
    ("vision", "Clarity of vision & goals"),
    ("market", "Market understanding & positioning"),
    ("product", "Product/Service readiness"),
    ("sales", "Sales & lead generation"),
    ("ops", "Operations & delivery"),
    ("finance", "Financial tracking & pricing"),
    ("team", "Team & hiring"),
    ("brand", "Brand & online presence"),
]

# -----------------------------
# Utils: Save to CSV (mock CRM)
# -----------------------------
def upsert_lead(row: Dict):
    df = pd.DataFrame([row])
    if os.path.exists(CSV_DB):
        df0 = pd.read_csv(CSV_DB)
        df = pd.concat([df0, df], ignore_index=True)
    df.to_csv(CSV_DB, index=False)

# -----------------------------
# PDF Report Generation
# -----------------------------
def make_report_pdf(user_name: str, email: str, scores: Dict[str, Dict], insights: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter

    title = f"{APP_NAME} – Compass Report"
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, h - 72, title)

    c.setFont("Helvetica", 11)
    c.drawString(72, h - 96, f"Name: {user_name}")
    c.drawString(72, h - 112, f"Email: {email}")
    c.drawString(72, h - 128, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    # Scores table
    y = h - 160
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Compass Scores (1–5)")
    y -= 18
    c.setFont("Helvetica", 10)
    for key, label in QUESTIONS:
        sc = scores[key]["score"]
        c.drawString(80, y, f"- {label}: {sc}")
        y -= 14

    # Insights
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Milestones & Interpretation")
    y -= 16
    c.setFont("Helvetica", 10)

    # Wrap insights text
    wrap = []
    line = ""
    for word in insights.split():
        if len(line) + len(word) + 1 < 90:
            line += (" " if line else "") + word
        else:
            wrap.append(line)
            line = word
    if line:
        wrap.append(line)
    for l in wrap:
        c.drawString(80, y, l)
        y -= 13
        if y < 72:
            c.showPage(); y = h - 72

    # Simple spider chart (rendered separately & embedded is overkill for demo)
    c.showPage()
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, h - 72, "Compass Chart")
    # Draw a basic radar-like star by lines/points (schematic)
    cx, cy, R = 300, 400, 150
    import math
    c.setFont("Helvetica", 9)
    # spokes
    for i, (key, label) in enumerate(QUESTIONS):
        angle = (2 * math.pi) * (i / len(QUESTIONS)) - math.pi / 2
        x = cx + R * math.cos(angle)
        y = cy + R * math.sin(angle)
        c.line(cx, cy, x, y)
        c.drawString(x + 4, y + 4, label[:16])
    # polygon for scores
    pts = []
    for i, (key, label) in enumerate(QUESTIONS):
        s = scores[key]["score"]
        r = (s / 5.0) * R
        angle = (2 * math.pi) * (i / len(QUESTIONS)) - math.pi / 2
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        pts.append((x, y))
    # draw polygon
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        c.line(x1, y1, x2, y2)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()

# -----------------------------
# Insights Generation (rule-based for demo)
# -----------------------------
def interpret(scores: Dict[str, Dict]) -> str:
    avg = np.mean([v["score"] for v in scores.values()])
    low_areas = [label for (k, label) in QUESTIONS if scores[k]["score"] <= 2]
    high_areas = [label for (k, label) in QUESTIONS if scores[k]["score"] >= 4]

    lines = [
        f"Your overall readiness score is {avg:.1f}/5.",
    ]
    if high_areas:
        lines.append(f"Strengths: {', '.join(high_areas)}.")
    if low_areas:
        lines.append(f"Focus areas: {', '.join(low_areas)}.")
    lines.append("Recommended next steps:")
    if "Sales & lead generation" in low_areas:
        lines.append("- Implement a lead pipeline with clear weekly targets and tracking.")
    if "Financial tracking & pricing" in low_areas:
        lines.append("- Set up monthly P&L tracking and review unit economics.")
    if "Brand & online presence" in low_areas:
        lines.append("- Refresh website messaging and create a content calendar.")
    if not low_areas:
        lines.append("- You’re in great shape. Consider accelerating growth initiatives.")
    return " ".join(lines)

# -----------------------------
# Email with PDF (optional)
# -----------------------------
def email_report(to_email: str, pdf_bytes: bytes, subject="Your Compass Report"):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        return False, "Email not configured in demo."
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content("Hi! Your Compass Report is attached.\n\nThank you.")
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="Compass_Report.pdf")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True, "Email sent."
    except Exception as e:
        return False, f"Email failed: {e}"

# -----------------------------
# UI: Landing
# -----------------------------
def ui_landing():
    st.header("🧭 AI Coach – Business Diagnostic")
    st.write(f"Get a personalized Compass Report for your business. RM{PRICE_MYR}.")
    if any(st.session_state["referral"].values()):
        st.caption(f"Referral: {st.session_state['referral']}")
    st.image(
        "https://images.unsplash.com/photo-1522071820081-009f0129c71c?q=80&w=1200&auto=format&fit=crop",
        caption="AI-powered business insights",
        use_column_width=True,
    )
    st.write("Click below to begin. (In this demo, payment is simulated.)")
    if st.button("Start Diagnostic"):
        st.session_state.stage = "pay"

# -----------------------------
# UI: Payment (demo or Stripe test)
# -----------------------------
def ui_payment():
    st.subheader("💳 Payment")
    st.write(f"This demo simulates payment of RM{PRICE_MYR}.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Simulate Payment (Demo) ✅"):
            st.session_state.paid = True
            st.session_state.stage = "auth"
    with col2:
        if STRIPE_PUBLISHABLE_KEY:
            st.info("Stripe test mode enabled. (Provide real integration post-hire.)")
            if st.button("Proceed with Stripe (Test)"):
                st.success("Stripe checkout would open here (test mode).")
        else:
            st.caption("Stripe keys not set; using demo mode.")

# -----------------------------
# UI: Auth (demo)
# -----------------------------
def ui_auth():
    st.subheader("👤 Sign up / Log in")
    with st.form("auth_form"):
        email = st.text_input("Email", value=st.session_state.user_email)
        name = st.text_input("Full Name", value=st.session_state.user_name)
        phone = st.text_input("Phone", value=st.session_state.user_phone)
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Continue")
    if submit:
        if not (email and name and password):
            st.error("Please fill email, name, and password.")
            return
        st.session_state.user_email = email
        st.session_state.user_name = name
        st.session_state.user_phone = phone
        st.session_state.lead_id = f"lead_{int(time.time())}"
        # Upsert into mock CRM
        upsert_lead({
            "lead_id": st.session_state.lead_id,
            "name": name,
            "email": email,
            "phone": phone,
            "paid": st.session_state.paid,
            "created_utc": datetime.utcnow().isoformat(),
            **st.session_state["referral"],
        })
        st.session_state.stage = "survey"

# -----------------------------
# UI: Survey / Chat-like Qs
# -----------------------------
def ui_survey():
    st.subheader("🗂️ Business Compass – Answer a few questions")
    st.write("Rate each area from 1 (low) to 5 (high), and add notes if needed.")
    with st.form("survey_form"):
        responses = {}
        for key, label in QUESTIONS:
            score = st.slider(label, 1, 5, 3, key=f"s_{key}")
            note = st.text_input(f"Notes – {label}", key=f"n_{key}")
            responses[key] = {"score": int(score), "note": note}
        submit = st.form_submit_button("Generate Report")
    if submit:
        st.session_state.answers = responses
        # update lead with scores
        row = {
            "lead_id": st.session_state.lead_id,
            "updated_utc": datetime.utcnow().isoformat(),
        }
        for k, _ in QUESTIONS:
            row[f"score_{k}"] = responses[k]["score"]
        upsert_lead(row)
        st.session_state.stage = "report"

# -----------------------------
# UI: Report + Email + Calendly
# -----------------------------
def ui_report():
    st.subheader("📄 Your Compass Report")
    scores = st.session_state.answers
    insights = interpret(scores)
    pdf_bytes = make_report_pdf(st.session_state.user_name, st.session_state.user_email, scores, insights)
    st.session_state.report_pdf_bytes = pdf_bytes

    # Show quick chart inline
    labels = [lbl for _, lbl in QUESTIONS]
    vals = [scores[k]["score"] for k, _ in QUESTIONS]
    fig = plt.figure()
    plt.bar(labels, vals)
    plt.xticks(rotation=45, ha="right")
    plt.ylim(0, 5)
    plt.title("Compass Scores")
    st.pyplot(fig)

    st.success("Report generated!")
    st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name="Compass_Report.pdf", mime="application/pdf")

    sent = False
    if st.button("📧 Email me the report"):
        ok, msg = email_report(st.session_state.user_email, pdf_bytes)
        st.info(msg)
        sent = ok

    st.markdown("---")
    st.write("Next step: book your **AI Coaching call**.")
    st.link_button("📅 Book on Calendly", CALENDLY_URL)

    if st.button("Finish"):
        # store final row
        upsert_lead({
            "lead_id": st.session_state.lead_id,
            "report_ready": True,
            "emailed": sent,
            "completed_utc": datetime.utcnow().isoformat(),
        })
        st.session_state.stage = "done"

# -----------------------------
# UI: Done
# -----------------------------
def ui_done():
    st.header("✅ All set!")
    st.write("Thank you. Your responses were saved. We’ll see you on the call.")
    st.link_button("Return to Home", "#")
    if st.button("Start Over"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        init_state()

# -----------------------------
# Router
# -----------------------------
def router():
    stage = st.session_state.stage
    if stage == "landing":
        ui_landing()
    elif stage == "pay":
        ui_payment()
    elif stage == "auth":
        ui_auth()
    elif stage == "survey":
        ui_survey()
    elif stage == "report":
        ui_report()
    elif stage == "done":
        ui_done()
    else:
        ui_landing()

router()
