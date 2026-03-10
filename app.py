import streamlit as st
import anthropic
import pdfplumber
import pandas as pd
from docx import Document
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QA & Governance Chatbot — PetroApp",
    page_icon="📋",
    layout="wide"
)

# ── PetroApp Branding CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #f8faff; }
    .petroapp-header {
        background: linear-gradient(90deg, #2563EB, #1d4ed8);
        padding: 18px 32px; border-radius: 12px; margin-bottom: 24px;
        display: flex; align-items: center; gap: 16px;
    }
    .petroapp-header .logo-icon {
        font-size: 32px; font-weight: 900; color: white;
        background: rgba(255,255,255,0.2); border-radius: 10px;
        padding: 4px 12px; font-family: Arial, sans-serif;
    }
    .petroapp-header .title-block h1 { color: white; font-size: 22px; margin: 0; font-weight: 700; }
    .petroapp-header .title-block p  { color: rgba(255,255,255,0.8); font-size: 13px; margin: 2px 0 0 0; }
    .stButton > button {
        background-color: #2563EB !important; color: white !important;
        border: none !important; border-radius: 8px !important; font-weight: 600 !important;
    }
    .stButton > button:hover { background-color: #1d4ed8 !important; }
    section[data-testid="stSidebar"] { background-color: #f0f5ff; }
    .stTabs [data-baseweb="tab"] {
        background-color: #e8f0fe; border-radius: 8px 8px 0 0;
        color: #2563EB; font-weight: 600;
    }
    .stTabs [aria-selected="true"] { background-color: #2563EB !important; color: white !important; }

    /* Login card */
    .login-card {
        max-width: 460px; margin: 60px auto; background: white;
        border-radius: 16px; padding: 40px; box-shadow: 0 4px 24px rgba(37,99,235,0.10);
        text-align: center;
    }
    .login-card h2 { color: #2563EB; margin-bottom: 4px; }
    .login-card p  { color: #666; margin-bottom: 24px; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ── Fixed recipients ──────────────────────────────────────────────────────────
TO_EMAIL  = "quality.assurance@petroapp.com"
CC_EMAILS = ["osama.adel@petroapp.com", "a.hassan@petroapp.com", "mohamed.yassin@petroapp.com"]

# ── Load secrets ──────────────────────────────────────────────────────────────
try:
    API_KEY       = st.secrets["CLAUDE_API_KEY"]
    SMTP_EMAIL    = st.secrets["SMTP_EMAIL"]
    SMTP_PASSWORD = st.secrets["SMTP_PASSWORD"]
    SMTP_SERVER   = st.secrets.get("SMTP_SERVER", "smtp.office365.com")
    SMTP_PORT     = int(st.secrets.get("SMTP_PORT", 587))
except Exception:
    API_KEY = SMTP_EMAIL = SMTP_PASSWORD = None
    SMTP_SERVER = "smtp.office365.com"
    SMTP_PORT   = 587

# ══════════════════════════════════════════════════════════════════════════════
# ACCESS CONTROL — Only @petroapp.com emails allowed
# ══════════════════════════════════════════════════════════════════════════════
ALLOWED_DOMAIN = "petroapp.com"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""

def show_login():
    st.markdown("""
    <div style="max-width:460px;margin:60px auto;background:white;border-radius:16px;
                padding:40px;box-shadow:0 4px 24px rgba(37,99,235,0.10);text-align:center;">
        <div style="font-size:48px;margin-bottom:12px;">✦</div>
        <h2 style="color:#2563EB;margin-bottom:4px;">QA & Governance Chatbot</h2>
        <p style="color:#666;font-size:14px;margin-bottom:8px;">PetroApp Internal Tool</p>
        <p style="color:#999;font-size:13px;">Access restricted to PetroApp employees only</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("##### Enter your PetroApp details to continue")
            name  = st.text_input("Full Name", placeholder="Ahmed Hassan")
            email = st.text_input("Work Email", placeholder="name@petroapp.com")
            login_btn = st.form_submit_button("🔐 Sign In", use_container_width=True)

        if login_btn:
            if not name.strip() or not email.strip():
                st.error("Please enter your name and email.")
            elif not email.strip().lower().endswith(f"@{ALLOWED_DOMAIN}"):
                st.error(f"❌ Access denied. Only @{ALLOWED_DOMAIN} emails are allowed.")
            else:
                st.session_state.authenticated = True
                st.session_state.user_email    = email.strip().lower()
                st.session_state.user_name     = name.strip()
                st.rerun()

# ── Show login if not authenticated ──────────────────────────────────────────
if not st.session_state.authenticated:
    show_login()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP (only shown after successful login)
# ══════════════════════════════════════════════════════════════════════════════

# Header
st.markdown(f"""
<div class="petroapp-header">
    <div class="logo-icon">✦P</div>
    <div class="title-block">
        <h1>QA &amp; Governance Chatbot</h1>
        <p>Welcome, {st.session_state.user_name} &nbsp;·&nbsp; {st.session_state.user_email}</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.user_name}**")
    st.caption(st.session_state.user_email)
    if st.button("🚪 Sign Out", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_email    = ""
        st.session_state.user_name     = ""
        st.session_state.messages      = []
        st.rerun()

    st.markdown("---")
    st.markdown("## 📁 Upload Documents")
    st.caption("Supported: PDF, DOCX, XLSX — up to 200MB per file")
    uploaded_files = st.file_uploader(
        "Upload files", type=["pdf", "docx", "xlsx"],
        accept_multiple_files=True, label_visibility="collapsed"
    )
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} document(s) loaded")
        for f in uploaded_files:
            st.caption(f"📄 {f.name}")
    else:
        st.info("No documents uploaded yet.")

    st.markdown("---")
    st.caption("🔒 Powered by Claude AI · PetroApp Internal")

# ── Helper: extract text ──────────────────────────────────────────────────────
def extract_text(file) -> str:
    name = file.name.lower()
    text = ""
    if name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    elif name.endswith(".docx"):
        doc = Document(file)
        for para in doc.paragraphs:
            text += para.text + "\n"
    elif name.endswith(".xlsx"):
        df_dict = pd.read_excel(file, sheet_name=None)
        for sheet_name, df in df_dict.items():
            text += f"\n[Sheet: {sheet_name}]\n"
            text += df.to_string(index=False) + "\n"
    return text.strip()

# ── Helper: send email ────────────────────────────────────────────────────────
def send_request_email(requester_name, requester_email, request_text):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        main_msg = MIMEMultipart("alternative")
        main_msg["From"]    = SMTP_EMAIL
        main_msg["To"]      = TO_EMAIL
        main_msg["CC"]      = ", ".join(CC_EMAILS)
        main_msg["Subject"] = f"New Authority Request — {requester_name} ({now})"
        main_html = f"""
        <html><body style="font-family:Arial,sans-serif;color:#333;padding:20px;">
            <div style="background:linear-gradient(90deg,#2563EB,#1d4ed8);padding:16px 24px;border-radius:10px;margin-bottom:20px;">
                <h2 style="color:white;margin:0;">🔔 New Authority Request — PetroApp</h2>
            </div>
            <table style="border-collapse:collapse;width:100%;max-width:620px;">
                <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;width:170px;border:1px solid #ddd;">Requester Name</td>
                    <td style="padding:10px;border:1px solid #ddd;">{requester_name}</td></tr>
                <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Requester Email</td>
                    <td style="padding:10px;border:1px solid #ddd;">{requester_email}</td></tr>
                <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Submitted At</td>
                    <td style="padding:10px;border:1px solid #ddd;">{now}</td></tr>
                <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Request Details</td>
                    <td style="padding:10px;border:1px solid #ddd;">{request_text}</td></tr>
            </table>
            <p style="color:#888;font-size:12px;margin-top:20px;">Submitted via QA &amp; Governance Chatbot — PetroApp</p>
        </body></html>"""
        main_msg.attach(MIMEText(main_html, "html"))
        all_recipients = [TO_EMAIL] + CC_EMAILS + [requester_email]
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls(); s.login(SMTP_EMAIL, SMTP_PASSWORD)
            s.sendmail(SMTP_EMAIL, all_recipients, main_msg.as_string())

        confirm_msg = MIMEMultipart("alternative")
        confirm_msg["From"]    = SMTP_EMAIL
        confirm_msg["To"]      = requester_email
        confirm_msg["Subject"] = "✅ Your Authority Request Has Been Submitted — PetroApp QA"
        confirm_html = f"""
        <html><body style="font-family:Arial,sans-serif;color:#333;padding:20px;">
            <div style="background:linear-gradient(90deg,#2563EB,#1d4ed8);padding:16px 24px;border-radius:10px;margin-bottom:20px;">
                <h2 style="color:white;margin:0;">✅ Request Submitted Successfully</h2>
            </div>
            <p>Dear <strong>{requester_name}</strong>,</p>
            <p>Your request has been submitted to the QA &amp; Governance team and is now under review.</p>
            <h3 style="color:#2563EB;">Your Request:</h3>
            <blockquote style="border-left:4px solid #2563EB;padding:10px 16px;background:#f0f5ff;border-radius:0 8px 8px 0;">
                {request_text}
            </blockquote>
            <p style="color:#888;font-size:12px;margin-top:20px;">QA &amp; Governance Chatbot — PetroApp</p>
        </body></html>"""
        confirm_msg.attach(MIMEText(confirm_html, "html"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls(); s.login(SMTP_EMAIL, SMTP_PASSWORD)
            s.sendmail(SMTP_EMAIL, [requester_email], confirm_msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)

# ── Document context ──────────────────────────────────────────────────────────
document_context = ""
if uploaded_files:
    for f in uploaded_files:
        document_context += f"\n\n=== Document: {f.name} ===\n{extract_text(f)}"

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["💬 Ask a Question", "📝 Request New Authority"])

# ── TAB 1: Chatbot ────────────────────────────────────────────────────────────
with tab1:
    if not uploaded_files:
        st.info("👈 Please upload your documents from the sidebar to start chatting.")
    else:
        if "messages" not in st.session_state:
            st.session_state.messages = []
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_input = st.chat_input("Ask a question about your Policies, Procedures, or DOA...")
        if user_input:
            if not API_KEY:
                st.error("API Key not configured. Please contact the system administrator.")
            else:
                st.session_state.messages.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.write(user_input)

                system_prompt = f"""You are a helpful assistant for the QA and Governance department at PetroApp.
Answer questions strictly based on the documents provided. If not found, say: "I could not find this information in the provided documents."
Be clear, concise, and professional. Always end EVERY response with:
---
📞 **For any unclear authorities or further assistance, please contact the QA & Governance team directly.**

--- DOCUMENTS START ---
{document_context}
--- DOCUMENTS END ---"""

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            client   = anthropic.Anthropic(api_key=API_KEY)
                            response = client.messages.create(
                                model="claude-haiku-4-5-20251001",
                                max_tokens=1024,
                                system=system_prompt,
                                messages=[{"role": m["role"], "content": m["content"]}
                                          for m in st.session_state.messages]
                            )
                            answer = response.content[0].text
                            st.write(answer)
                            st.session_state.messages.append({"role": "assistant", "content": answer})
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

# ── TAB 2: Request New Authority ──────────────────────────────────────────────
with tab2:
    st.subheader("📝 Request a New Authority")
    st.write("Fill in the form below to suggest adding a new authority to the DOA. Your request will be sent directly to the QA & Governance team.")

    with st.form("authority_request_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            req_name  = st.text_input("Your Full Name *", value=st.session_state.user_name)
        with col2:
            req_email = st.text_input("Your Email Address *", value=st.session_state.user_email)
        req_details = st.text_area(
            "Describe the authority you are requesting *",
            placeholder="e.g., I would like to request approval authority for purchase orders up to 50,000 EGP for the IT department.",
            height=160
        )
        submitted = st.form_submit_button("📤 Submit Request", use_container_width=True, type="primary")

    if submitted:
        if not req_name.strip() or not req_email.strip() or not req_details.strip():
            st.error("Please fill in all required fields.")
        elif "@" not in req_email:
            st.error("Please enter a valid email address.")
        elif not SMTP_EMAIL or not SMTP_PASSWORD:
            st.warning("⚠️ Email is not configured yet. Please contact the system administrator.")
        else:
            with st.spinner("Sending your request..."):
                success, message = send_request_email(req_name.strip(), req_email.strip(), req_details.strip())
            if success:
                st.success("✅ Your request has been submitted! A confirmation email has been sent to your inbox.")
            else:
                st.error(f"Failed to send email. Error: {message}")
