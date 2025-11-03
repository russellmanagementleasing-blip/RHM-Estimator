# -*- coding: utf-8 -*-
"""
RHM Multi-Service Estimator
Login + Search + PDF + Google Sheets (via st.secrets)
NO service_account.json needed — secure & cloud-ready
"""

import streamlit as st
import json
from datetime import datetime
from fpdf import FPDF, XPos, YPos
import os

# Google Sheets (secure via st.secrets)
try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_ENABLED = True
except ImportError:
    st.warning("Install gspread & google-auth for Sheets save.")
    SHEETS_ENABLED = False

# =============================
# 1. LOGIN SYSTEM
# =============================
USERS = {
    "adam": "rhm2025",
    "jane": "estimator2025",
    "mike": "rhm123"
}

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("Login Required")
        col1, col2 = st.columns([1, 1])
        with col1:
            username = st.text_input("Username")
        with col2:
            password = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            if USERS.get(username) == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success(f"Welcome, {username.title()}!")
                st.rerun()
            else:
                st.error("Invalid username or password")
        st.stop()
    else:
        with st.sidebar:
            st.write(f"**Logged in as:** {st.session_state.username.title()}")
            if st.button("Logout"):
                st.session_state.logged_in = False
                st.rerun()

# Call login
check_login()

# =============================
# 2. SERVICE DATABASE
# =============================
SERVICES = {
    "drywall repair": {
        "questions": [
            {"prompt": "How large is the damaged area?",
             "options": [("Small patch (under 1 sq ft)", 1.0), ("Medium patch (1–4 sq ft)", 3.0),
                         ("Large patch (4–10 sq ft)", 7.0), ("Over 10 sq ft (custom)", None)]},
            {"prompt": "Is texture matching required?", "options": [("Yes", 1.5), ("No", 1.0)]},
            {"prompt": "Do you want us to paint the patched area?", "options": [("Yes, match existing color", 2.0), ("No", 1.0)]},
            {"prompt": "Is the damage on a ceiling?", "options": [("Yes", 1.3), ("No", 1.0)]}
        ],
        "base_price": 85.00, "price_per_unit": 25.00, "unit": "sq ft",
        "custom_size_prompt": "Enter the area in square feet:"
    },

    "interior painting": {
        "questions": [
            {"prompt": "What is the total wall area to paint?",
             "options": [("One wall (under 100 sq ft)", 1.0), ("One room (100–300 sq ft)", 3.0),
                         ("Whole floor (300–600 sq ft)", 6.0), ("Custom size", None)]},
            {"prompt": "Number of colors?", "options": [("1 color", 1.0), ("2 colors", 1.3), ("3+ colors", 1.6)]},
            {"prompt": "Ceiling painting?", "options": [("Yes", 1.4), ("No", 1.0)]},
            {"prompt": "Prep work needed (holes, cracks)?", "options": [("Light", 1.1), ("Moderate", 1.4), ("Heavy", 1.8)]}
        ],
        "base_price": 150.00, "price_per_unit": 2.50, "unit": "sq ft",
        "custom_size_prompt": "Enter total wall area in sq ft:"
    },

    "flooring installation": {
        "questions": [
            {"prompt": "Flooring type?", "options": [("Laminate", 1.0), ("Vinyl plank", 1.2), ("Hardwood", 2.5), ("Tile", 3.0)]},
            {"prompt": "Area to cover?",
             "options": [("Small room (<100 sq ft)", 1.0), ("Medium (100–300 sq ft)", 3.0),
                         ("Large (300+ sq ft)", 6.0), ("Custom", None)]},
            {"prompt": "Subfloor prep needed?", "options": [("No", 1.0), ("Leveling", 1.5), ("Remove old floor", 2.0)]}
        ],
        "base_price": 200.00, "price_per_unit": 4.50, "unit": "sq ft",
        "custom_size_prompt": "Enter area in sq ft:"
    },

    # ADD MORE SERVICES HERE (100+)
    # "roof repair": { ... },
    # "deck building": { ... },
}

# =============================
# 3. SEARCHABLE SERVICE SELECTION
# =============================
st.title("Multi-Service Estimator")
st.markdown("---")

st.subheader("Search & Select Services")
search_term = st.text_input("Search services...", placeholder="e.g. drywall, paint, floor", key="search")

# Filter services
filtered_services = [
    s for s in SERVICES.keys()
    if search_term.lower() in s.replace("_", " ").lower()
] if search_term else list(SERVICES.keys())

if not filtered_services:
    st.warning("No services found. Try a different term.")
    selected_services = []
else:
    st.write(f"**Found {len(filtered_services)} service(s)**")
    cols = st.columns(3)
    selected_services = []
    for idx, service in enumerate(filtered_services):
        with cols[idx % 3]:
            if st.checkbox(
                service.replace("_", " ").title(),
                key=f"chk_{service}"
            ):
                selected_services.append(service)

if not selected_services:
    st.info("Please select at least one service.")
    st.stop()

# =============================
# 4. QUESTIONS PER SERVICE
# =============================
all_answers = {}
all_multipliers = {}
all_units = {}
all_labor = {}
all_material = {}

for service in selected_services:
    config = SERVICES[service]
    st.subheader(f"**{service.replace('_', ' ').title()}**")
    
    answers = {}
    multipliers = 1.0
    total_units = 0.0

    for idx, q in enumerate(config["questions"]):
        st.markdown(f"**Q{idx+1}: {q['prompt']}**")
        opts = q["options"]

        if any(f is None for _, f in opts):
            choice = st.radio("Select", [l for l, _ in opts], key=f"{service}_q{idx}")
            answers[q["prompt"]] = choice

            if "custom" in choice.lower():
                total_units = st.number_input(config["custom_size_prompt"], min_value=0.1, step=0.5, key=f"{service}_c{idx}")
                answers[q["prompt"]] = f"{total_units} {config['unit']} (custom)"
            else:
                total_units = next(f for l, f in opts if l == choice)
        else:
            choice = st.radio("Select", [l for l, _ in opts], key=f"{service}_q{idx}")
            answers[q["prompt"]] = choice
            factor = next(f for l, f in opts if l == choice)
            multipliers *= factor

    labor_cost = config["base_price"] * multipliers
    material_cost = total_units * config["price_per_unit"] if total_units else 0.0

    all_answers[service] = answers
    all_multipliers[service] = multipliers
    all_units[service] = total_units
    all_labor[service] = labor_cost
    all_material[service] = material_cost

# =============================
# 5. CUSTOMER INFO
# =============================
with st.expander("Customer Information (optional)", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        customer_name = st.text_input("Name")
        customer_phone = st.text_input("Phone")
    with col2:
        customer_email = st.text_input("Email")
        job_address = st.text_area("Job Address")

# =============================
# 6. TOTALS
# =============================
total_labor = sum(all_labor.values())
total_material = sum(all_material.values())
grand_total = total_labor + total_material

# =============================
# 7. BREAKDOWN
# =============================
st.markdown("---")
st.subheader("Combined Estimate")

for service in selected_services:
    with st.expander(f"**{service.replace('_', ' ').title()}** – ${all_labor[service] + all_material[service]:.2f}"):
        colA, colB = st.columns(2)
        with colA:
            st.metric("Base Labor", f"${SERVICES[service]['base_price']:.2f}")
            if all_multipliers[service] > 1:
                st.metric("Multiplier", f"×{all_multipliers[service]:.2f}")
            st.metric("Labor", f"${all_labor[service]:.2f}")
        with colB:
            if all_units[service]:
                st.metric(f"Materials ({SERVICES[service]['unit']})", f"${all_material[service]:.2f}")

st.markdown(f"<h2 style='text-align: center; color: #2E8B57;'>GRAND TOTAL: ${grand_total:.2f}</h2>", unsafe_allow_html=True)

# =============================
# 8. ANSWERS TABLE
# =============================
st.markdown("### Your Selections")
for service in selected_services:
    st.markdown(f"**{service.replace('_', ' ').title()}**")
    df = {"Question": [], "Answer": []}
    for q, a in all_answers[service].items():
        df["Question"].append(q)
        df["Answer"].append(a)
    st.table(df)

# =============================
# 9. EXPORT DATA
# =============================
estimate_data = {
    "customer": {k: v or None for k, v in zip(["name", "phone", "email", "address"],
                                             [customer_name, customer_phone, customer_email, job_address])},
    "timestamp": datetime.now().isoformat(),
    "estimator": st.session_state.username,
    "services": {}
}

for service in selected_services:
    config = SERVICES[service]
    estimate_data["services"][service] = {
        "answers": all_answers[service],
        "breakdown": {
            "base_price": config["base_price"],
            "multipliers": round(all_multipliers[service], 3),
            "labor_cost": round(all_labor[service], 2),
            "material_cost": round(all_material[service], 2),
            "total": round(all_labor[service] + all_material[service], 2),
            "unit": config["unit"] if all_units[service] else None,
            "units": round(all_units[service], 2) if all_units[service] else None
        }
    }

estimate_data["summary"] = {
    "total_labor": round(total_labor, 2),
    "total_material": round(total_material, 2),
    "grand_total": round(grand_total, 2)
}

# JSON
json_str = json.dumps(estimate_data, indent=2)
st.download_button("Download JSON", data=json_str,
                   file_name=f"estimate_{datetime.now():%Y%m%d_%H%M%S}.json", mime="application/json")

# =============================
# 10. SAVE TO GOOGLE SHEETS (via st.secrets)
# =============================
def save_to_sheets(data: dict):
    if not SHEETS_ENABLED:
        st.error("Sheets not enabled. Install gspread & google-auth.")
        return

    try:
        # Use st.secrets (secure, no file)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        sheet = client.open("RHM Estimates").sheet1  # CHANGE TO YOUR SHEET NAME
        
        row = [
            data["timestamp"],
            data["estimator"],
            data["customer"].get("name", ""),
            data["customer"].get("email", ""),
            data["customer"].get("phone", ""),
            ", ".join(selected_services),
            data["summary"]["grand_total"],
            data["summary"]["total_labor"],
            data["summary"]["total_material"]
        ]
        sheet.append_row(row)
        st.success("Saved to Google Sheets!")
    except Exception as e:
        st.error(f"Save failed: {e}. Check secrets & sheet name.")

# Save Button
if st.button("Save to Google Sheets", use_container_width=True, type="primary"):
    save_to_sheets(estimate_data)

# =============================
# 11. PDF – DejaVuSans + Bold
# =============================
def create_pdf(data: dict) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    use_unicode = False
    try:
        if os.path.exists("DejaVuSans.ttf"):
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        if os.path.exists("DejaVuSans-Bold.ttf"):
            pdf.add_font("DejaVu", "B", "DejaVuSans-Bold.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        use_unicode = True
    except Exception as e:
        st.warning(f"DejaVu failed: {e}. Using Helvetica.")

    if not use_unicode:
        pdf.set_font("Helvetica", size=12)

    def write(txt, style="", size=12, align="L"):
        if use_unicode:
            pdf.set_font("DejaVu", style, size)
        else:
            pdf.set_font("Helvetica", style, size)
            txt = txt.replace("–", "-").replace("→", "->").replace("×", "x")
        pdf.cell(0, 10, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=align)

    write("Multi-Service Estimate", "B", 16, "C")
    pdf.ln(5)
    write(f"Estimator: {data['estimator'].title()}")
    write(f"Date: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    pdf.ln(5)

    if any(data["customer"].values()):
        write("Customer", "B")
        for k, v in data["customer"].items():
            if v:
                write(f"  {k.title()}: {v}")
        pdf.ln(5)

    for service, info in data["services"].items():
        config = SERVICES[service]
        write(f"{service.replace('_', ' ').title()} – ${info['breakdown']['total']:.2f}", "B", 14)
        pdf.ln(3)
        for q, a in info["answers"].items():
            write(f"  {q}")
            write(f"    → {a}")
        pdf.ln(3)
        b = info["breakdown"]
        write(f"  Base: ${b['base_price']:.2f}")
        if b['multipliers'] > 1:
            write(f"  Multiplier: ×{b['multipliers']}")
        write(f"  Labor: ${b['labor_cost']:.2f}")
        if b['material_cost'] > 0:
            write(f"  Materials: ${b['material_cost']:.2f}")
        pdf.ln(5)

    write(f"GRAND TOTAL: ${data['summary']['grand_total']:.2f}", "B", 16, "C")
    output = pdf.output()
    return bytes(output) if isinstance(output, bytearray) else output

# PDF Download
pdf_bytes = create_pdf(estimate_data)
st.download_button("Download PDF", data=pdf_bytes,
                   file_name=f"estimate_{datetime.now():%Y%m%d_%H%M%S}.pdf", mime="application/pdf")

st.markdown("---")
st.caption("Uses `st.secrets` for Google Sheets. Add secrets in Streamlit Cloud → App Settings → Secrets.")
