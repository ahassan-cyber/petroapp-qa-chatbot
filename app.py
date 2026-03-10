import streamlit as st
import anthropic
import pdfplumber
import pandas as pd
from docx import Document
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import glob

# ── Constants ─────────────────────────────────────────────────────────────────
ADMIN_EMAIL    = "a.hassan@petroapp.com"
ALLOWED_DOMAIN = "petroapp.com"
TO_EMAIL       = "quality.assurance@petroapp.com"
CC_EMAILS      = ["osama.adel@petroapp.com", "a.hassan@petroapp.com", "mohamed.yassin@petroapp.com"]
DOCS_FOLDER    = "documents"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PetroApp — Governance Tool",
    page_icon="📋",
    layout="wide"
)

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

# ── PetroApp P Logo SVG (matches brand) ──────────────────────────────────────
PETROAPP_LOGO_SVG = """
<svg width="80" height="80" viewBox="0 0 68 90" xmlns="http://www.w3.org/2000/svg">
  <rect x="20" y="5" width="17" height="80" fill="#1B6FE8"/>
  <path fill="#1B6FE8" d="M 37,5 Q 66,5 66,30 Q 66,55 37,55 L 20,55 L 20,5 Z"/>
  <rect x="3" y="36" width="17" height="20" fill="#1B6FE8"/>
  <path fill="white" d="M 37,18 Q 51,18 51,30 Q 51,42 37,42 L 3,42 L 3,36 L 20,36 L 20,18 Z"/>
</svg>
"""

PETROAPP_LOGO_SVG_SMALL = """
<svg width="44" height="44" viewBox="0 0 68 90" xmlns="http://www.w3.org/2000/svg">
  <rect x="20" y="5" width="17" height="80" fill="white"/>
  <path fill="white" d="M 37,5 Q 66,5 66,30 Q 66,55 37,55 L 20,55 L 20,5 Z"/>
  <rect x="3" y="36" width="17" height="20" fill="white"/>
  <path fill="#1B6FE8" d="M 37,18 Q 51,18 51,30 Q 51,42 37,42 L 3,42 L 3,36 L 20,36 L 20,18 Z"/>
</svg>
"""

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

* { font-family: 'Inter', sans-serif; }
.stApp { background-color: #f0f4ff; }

/* ── Animations ── */
@keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes glowPulse {
    0%   { box-shadow: 0 0 0 0 rgba(27,111,232,0.30); }
    50%  { box-shadow: 0 0 0 18px rgba(27,111,232,0); }
    100% { box-shadow: 0 0 0 0 rgba(27,111,232,0); }
}
@keyframes floatLogo {
    0%   { transform: translateY(0px); }
    50%  { transform: translateY(-6px); }
    100% { transform: translateY(0px); }
}

/* ── Login ── */
.login-wrapper {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-height: 78vh;
    animation: fadeSlideIn 0.6s ease-out;
}
.petro-logo-wrap {
    animation: glowPulse 2.5s infinite, floatLogo 3s ease-in-out infinite;
    border-radius: 16px; display: inline-block; margin-bottom: 20px;
}
.login-title {
    font-size: 28px; font-weight: 700; color: #1e3a8a;
    margin: 4px 0; text-align: center;
}
.login-sub {
    font-size: 14px; color: #1B6FE8; font-weight: 500;
    margin-bottom: 4px; text-align: center;
}
.login-restricted {
    font-size: 12px; color: #94a3b8; margin-bottom: 28px; text-align: center;
}
.login-card {
    background: white; border-radius: 20px; padding: 36px 40px;
    box-shadow: 0 8px 40px rgba(27,111,232,0.10);
    width: 100%; max-width: 440px;
}

/* ── Header ── */
.petroapp-header {
    background: linear-gradient(90deg, #1B4FD8, #1B6FE8, #3b82f6);
    padding: 14px 24px; border-radius: 14px; margin-bottom: 20px;
    display: flex; align-items: center; gap: 14px;
    box-shadow: 0 4px 20px rgba(27,111,232,0.25);
}
.header-logo {
    width: 48px; height: 48px;
    background: rgba(255,255,255,0.15);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}
.header-title h1 { color: white; font-size: 20px; margin: 0; font-weight: 700; }
.header-title p  { color: rgba(255,255,255,0.75); font-size: 12px; margin: 2px 0 0 0; }

/* ── Quick FAQ buttons ── */
.stButton > button[kind="secondary"] {
    background: white !important;
    border: 1.5px solid #dbeafe !important;
    color: #1B6FE8 !important;
    border-radius: 20px !important;
    font-size: 12px !important;
    padding: 6px 14px !important;
    box-shadow: 0 1px 4px rgba(27,111,232,0.07) !important;
}
.stButton > button[kind="secondary"]:hover {
    background: #1B6FE8 !important;
    color: white !important;
    border-color: #1B6FE8 !important;
}

/* ── Admin badge ── */
.admin-badge {
    background: linear-gradient(90deg, #1B6FE8, #1B4FD8);
    color: white; border-radius: 20px; padding: 2px 12px;
    font-size: 11px; font-weight: 600; display: inline-block;
    margin-left: 8px; vertical-align: middle;
}

/* ── Error card ── */
.error-card {
    background: #fef2f2; border: 1px solid #fecaca;
    border-radius: 12px; padding: 16px 20px; margin-top: 12px;
}

/* ── Primary buttons ── */
.stButton > button[kind="primary"],
.stButton > button:not([kind]) {
    background-color: #1B6FE8 !important; color: white !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button:not([kind]):hover {
    background-color: #1B4FD8 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab"] {
    background: #e8f0fe; border-radius: 8px 8px 0 0;
    color: #1B6FE8; font-weight: 600;
}
.stTabs [aria-selected="true"] {
    background: #1B6FE8 !important; color: white !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] { background: #f0f5ff; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ══════════════════════════════════════════════════════════════════════════════
for key, val in {
    "authenticated": False,
    "user_email": "",
    "user_name": "",
    "messages": [],
    "uploaded_docs_context": "",
    "last_error": None,
    "pending_question": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

is_admin = st.session_state.user_email.lower() == ADMIN_EMAIL

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def extract_text(file, filename: str = "") -> str:
    name = (filename or file.name).lower()
    text = ""
    try:
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
    except Exception as e:
        text = f"[Error reading file: {e}]"
    return text.strip()


def load_repo_documents() -> str:
    """Load documents pre-stored in the /documents folder of the repo."""
    context = ""
    if not os.path.exists(DOCS_FOLDER):
        return context
    patterns = ["*.pdf", "*.docx", "*.xlsx"]
    files = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(DOCS_FOLDER, p)))
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, "rb") as f:
                extracted = extract_text(f, fname)
                context += f"\n\n=== Document: {fname} ===\n{extracted}"
        except Exception as e:
            context += f"\n\n=== Document: {fname} ===\n[Error: {e}]"
    return context


def send_email_generic(subject: str, html_body: str, to: list) -> tuple:
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = SMTP_EMAIL
        msg["To"]      = ", ".join(to)
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_EMAIL, SMTP_PASSWORD)
            s.sendmail(SMTP_EMAIL, to, msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)


def send_request_email(requester_name, requester_email, request_text):
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""
    <html><body style="font-family:Inter,Arial,sans-serif;color:#333;padding:24px;">
        <div style="background:linear-gradient(90deg,#1B4FD8,#1B6FE8);padding:18px 28px;border-radius:12px;margin-bottom:20px;">
            <h2 style="color:white;margin:0;">🔔 New Authority Request — PetroApp</h2>
        </div>
        <table style="border-collapse:collapse;width:100%;max-width:620px;">
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;width:170px;border:1px solid #ddd;">Name</td>
                <td style="padding:10px;border:1px solid #ddd;">{requester_name}</td></tr>
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Email</td>
                <td style="padding:10px;border:1px solid #ddd;">{requester_email}</td></tr>
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Time</td>
                <td style="padding:10px;border:1px solid #ddd;">{now}</td></tr>
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Request</td>
                <td style="padding:10px;border:1px solid #ddd;">{request_text}</td></tr>
        </table>
        <p style="color:#888;font-size:12px;margin-top:20px;">PetroApp — Governance Tool</p>
    </body></html>"""
    all_to = [TO_EMAIL] + CC_EMAILS + [requester_email]
    ok, msg = send_email_generic(f"New Authority Request — {requester_name} ({now})", html, all_to)
    if ok:
        confirm_html = f"""
        <html><body style="font-family:Inter,Arial,sans-serif;color:#333;padding:24px;">
            <div style="background:linear-gradient(90deg,#1B4FD8,#1B6FE8);padding:18px 28px;border-radius:12px;margin-bottom:20px;">
                <h2 style="color:white;margin:0;">✅ Request Submitted</h2>
            </div>
            <p>Dear <strong>{requester_name}</strong>,</p>
            <p>Your request has been submitted to the QA &amp; Governance team.</p>
            <blockquote style="border-left:4px solid #1B6FE8;padding:10px 16px;background:#f0f5ff;border-radius:0 8px 8px 0;">
                {request_text}
            </blockquote>
            <p style="color:#888;font-size:12px;margin-top:20px;">PetroApp — Governance Tool</p>
        </body></html>"""
        send_email_generic("✅ Your Authority Request Has Been Submitted", confirm_html, [requester_email])
    return ok, msg


def send_error_report(user_email, error_text):
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""
    <html><body style="font-family:Inter,Arial,sans-serif;color:#333;padding:24px;">
        <div style="background:#dc2626;padding:18px 28px;border-radius:12px;margin-bottom:20px;">
            <h2 style="color:white;margin:0;">🚨 Chatbot Error Report</h2>
        </div>
        <table style="border-collapse:collapse;width:100%;max-width:620px;">
            <tr><td style="padding:10px;background:#fef2f2;font-weight:bold;width:130px;border:1px solid #ddd;">User</td>
                <td style="padding:10px;border:1px solid #ddd;">{user_email}</td></tr>
            <tr><td style="padding:10px;background:#fef2f2;font-weight:bold;border:1px solid #ddd;">Time</td>
                <td style="padding:10px;border:1px solid #ddd;">{now}</td></tr>
            <tr><td style="padding:10px;background:#fef2f2;font-weight:bold;border:1px solid #ddd;">Error</td>
                <td style="padding:10px;border:1px solid #ddd;color:#dc2626;font-family:monospace;">{error_text}</td></tr>
        </table>
        <p style="color:#888;font-size:12px;margin-top:20px;">PetroApp — Governance Tool</p>
    </body></html>"""
    return send_email_generic(f"🚨 Chatbot Error — {now}", html, [ADMIN_EMAIL])


def call_claude(messages_history, document_context):
    """Call Claude API and return the answer text, or raise on error."""
    system_prompt = f"""You are a helpful assistant for the QA and Governance department at PetroApp.
Answer questions strictly based on the documents below.
If the answer is not found, say: "I could not find this information in the provided documents."
Be clear, concise, and professional. Always end EVERY response with:
---
📞 **For any unclear authorities or further assistance, please contact the QA & Governance team directly.**

--- DOCUMENTS ---
{document_context}
--- END ---"""

    client   = anthropic.Anthropic(api_key=API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages_history]
    )
    return response.content[0].text


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown(f"""
        <div class="login-wrapper">
            <div class="petro-logo-wrap">
                {PETROAPP_LOGO_SVG}
            </div>
            <div class="login-title">QA &amp; Governance Chatbot</div>
            <div class="login-sub">PetroApp — Governance Tool</div>
            <div class="login-restricted">🔒 Access restricted to PetroApp employees only</div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            name  = st.text_input("Full Name", placeholder="Ahmed Hassan")
            email = st.text_input("Work Email", placeholder="name@petroapp.com")
            login = st.form_submit_button("Sign In →", use_container_width=True)

        if login:
            if not name.strip() or not email.strip():
                st.error("Please enter your name and email.")
            elif not email.strip().lower().endswith(f"@{ALLOWED_DOMAIN}"):
                st.error(f"❌ Access denied. Only @{ALLOWED_DOMAIN} emails are allowed.")
            else:
                st.session_state.authenticated = True
                st.session_state.user_email    = email.strip().lower()
                st.session_state.user_name     = name.strip()
                st.rerun()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
is_admin = st.session_state.user_email.lower() == ADMIN_EMAIL

# ── Load documents from repo folder ──────────────────────────────────────────
repo_doc_context = load_repo_documents()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    admin_label = ' <span class="admin-badge">ADMIN</span>' if is_admin else ""
    st.markdown(f"👤 **{st.session_state.user_name}**{admin_label}", unsafe_allow_html=True)
    st.caption(st.session_state.user_email)

    if st.button("🚪 Sign Out", use_container_width=True):
        for k in ["authenticated","user_email","user_name","messages","uploaded_docs_context","last_error","pending_question"]:
            st.session_state[k] = False if k=="authenticated" else "" if k in ["user_email","user_name","uploaded_docs_context"] else [] if k=="messages" else None
        st.rerun()

    st.markdown("---")

    if is_admin:
        st.markdown("## 📁 Manage Documents")
        st.caption("Admin only — Upload Policies, Procedures, or DOA files")
        uploaded_files = st.file_uploader(
            "Upload files", type=["pdf","docx","xlsx"],
            accept_multiple_files=True, label_visibility="collapsed"
        )
        if uploaded_files:
            ctx = ""
            for f in uploaded_files:
                ctx += f"\n\n=== Document: {f.name} ===\n{extract_text(f)}"
            st.session_state.uploaded_docs_context = ctx
            st.success(f"✅ {len(uploaded_files)} file(s) loaded")
            for f in uploaded_files:
                st.caption(f"📄 {f.name}")
        elif repo_doc_context:
            st.info("📂 Using documents from the repository.")
        else:
            st.warning("No documents loaded yet.")

        st.markdown("---")
        st.markdown("## ⚙️ System Status")
        st.caption(f"API Key: {'✅ Configured' if API_KEY else '❌ Missing'}")
        st.caption(f"Email:   {'✅ Configured' if SMTP_EMAIL else '❌ Missing'}")
        repo_count = len(glob.glob(os.path.join(DOCS_FOLDER,"*.*"))) if os.path.exists(DOCS_FOLDER) else 0
        st.caption(f"Repo Docs: {repo_count} file(s)")
    else:
        if repo_doc_context or st.session_state.uploaded_docs_context:
            st.success("📂 Documents are loaded and ready!")
        else:
            st.info("Documents are being prepared. Please check back soon.")

    st.markdown("---")
    st.caption("🔒 PetroApp — Governance Tool")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="petroapp-header">
    <div class="header-logo">{PETROAPP_LOGO_SVG_SMALL}</div>
    <div class="header-title">
        <h1>QA &amp; Governance Chatbot</h1>
        <p>Welcome, {st.session_state.user_name} &nbsp;·&nbsp; {st.session_state.user_email}</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Combine document context ──────────────────────────────────────────────────
document_context = repo_doc_context + st.session_state.uploaded_docs_context

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = ["💬 Ask a Question", "📝 Request New Authority"]
if is_admin:
    tabs.append("🛠️ Admin Panel")

tab_objects = st.tabs(tabs)
tab1 = tab_objects[0]
tab2 = tab_objects[1]
tab3 = tab_objects[2] if is_admin else None

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — Chat
# ════════════════════════════════════════════════════════════════════════════════
with tab1:
    if not document_context.strip():
        st.info("📂 Documents are being loaded. Please contact the admin if this persists.")
    else:
        # ── Quick FAQ buttons ──
        st.markdown("**💡 Quick Questions:**")
        faqs = [
            "What is the approval authority for contracts?",
            "What are the steps for salary transfer?",
            "Who approves purchase orders?",
            "What is the policy for travel expenses?",
            "What is the DOA for hiring?"
        ]
        cols = st.columns(len(faqs))
        for i, faq in enumerate(faqs):
            with cols[i]:
                if st.button(faq, key=f"faq_{i}", use_container_width=True):
                    st.session_state.pending_question = faq
                    st.rerun()

        st.markdown("---")

        # ── Chat history ──
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # ── Chat input ──
        user_input = st.chat_input("Ask a question about Policies, Procedures, or DOA...")

        # ── Resolve question to process (typed OR from FAQ button) ──
        question_to_process = user_input or st.session_state.get("pending_question")

        if question_to_process:
            # Clear pending if it came from FAQ
            if st.session_state.get("pending_question"):
                st.session_state.pending_question = None

            if not API_KEY:
                err = "Claude API Key is not configured. Please contact the admin."
                st.error(err)
                st.session_state.last_error = err
            else:
                st.session_state.messages.append({"role": "user", "content": question_to_process})
                with st.chat_message("user"):
                    st.write(question_to_process)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            answer = call_claude(st.session_state.messages, document_context)
                            st.write(answer)
                            st.session_state.messages.append({"role": "assistant", "content": answer})
                            st.session_state.last_error = None
                        except Exception as e:
                            err_msg = str(e)
                            st.session_state.last_error = err_msg
                            st.markdown(f"""
                            <div class="error-card">
                                <strong>⚠️ Something went wrong</strong><br>
                                <small style="color:#666;">{err_msg}</small>
                            </div>
                            """, unsafe_allow_html=True)

        # ── Report Error button ──
        if st.session_state.last_error:
            st.markdown("---")
            if st.button("🚨 Report this error to Admin", type="secondary"):
                if SMTP_EMAIL and SMTP_PASSWORD:
                    ok, _ = send_error_report(st.session_state.user_email, st.session_state.last_error)
                    if ok:
                        st.success("✅ Error reported to the admin successfully!")
                        st.session_state.last_error = None
                    else:
                        st.error("Could not send error report. Please contact the admin directly.")
                else:
                    st.warning("Email not configured. Please contact a.hassan@petroapp.com directly.")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — Request New Authority
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("📝 Request a New Authority")
    st.write("Submit a request to add or modify an authority in the DOA. The QA & Governance team will review and respond.")

    with st.form("authority_request_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            req_name = st.text_input("Your Full Name *", value=st.session_state.user_name)
        with col2:
            req_email = st.text_input("Your Email *", value=st.session_state.user_email)
        req_details = st.text_area(
            "Describe the authority you are requesting *",
            placeholder="e.g., I would like to request approval authority for purchase orders up to 50,000 EGP for the IT department.",
            height=150
        )
        submitted = st.form_submit_button("📤 Submit Request", use_container_width=True, type="primary")

    if submitted:
        if not req_name.strip() or not req_email.strip() or not req_details.strip():
            st.error("Please fill in all required fields.")
        elif "@" not in req_email:
            st.error("Please enter a valid email address.")
        elif not SMTP_EMAIL or not SMTP_PASSWORD:
            st.warning("⚠️ Email is not configured. Please contact a.hassan@petroapp.com directly.")
        else:
            with st.spinner("Sending your request..."):
                ok, msg = send_request_email(req_name.strip(), req_email.strip(), req_details.strip())
            if ok:
                st.success("✅ Request submitted! A confirmation email has been sent to your inbox.")
            else:
                st.error(f"Failed to send. Error: {msg}")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — Admin Panel (Admin only)
# ════════════════════════════════════════════════════════════════════════════════
if is_admin and tab3:
    with tab3:
        st.subheader("🛠️ Admin Panel")
        st.caption("Only visible to a.hassan@petroapp.com")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 📊 System Overview")
            repo_count = len(glob.glob(os.path.join(DOCS_FOLDER,"*.*"))) if os.path.exists(DOCS_FOLDER) else 0
            st.metric("Repo Documents", f"{repo_count} files")
            st.metric("API Key", "✅ Active" if API_KEY else "❌ Missing")
            st.metric("Email Config", "✅ Active" if SMTP_EMAIL else "❌ Missing")

            st.markdown("### 🔗 Quick Links")
            st.markdown("- [GitHub Repository](https://github.com/ahassan-cyber/petroapp-qa-chatbot)")
            st.markdown("- [Streamlit Cloud Dashboard](https://share.streamlit.io)")
            st.markdown("- [Anthropic Console](https://platform.claude.com)")

        with col2:
            st.markdown("### 📁 Document Management")
            st.info("""
            **How to add permanent documents:**
            1. Go to your GitHub repository
            2. Open the `documents` folder
            3. Click "Add file" → "Upload files"
            4. Upload your PDF, DOCX, or XLSX files
            5. Documents load automatically for all users

            **Session documents** (uploaded via sidebar) are only available until the app restarts.
            """)

            st.markdown("### 📧 Send Admin Announcement")
            with st.form("admin_announce"):
                announce_to   = st.text_input("To (email)", placeholder="all@petroapp.com")
                announce_subj = st.text_input("Subject")
                announce_body = st.text_area("Message", height=100)
                send_ann = st.form_submit_button("📤 Send", use_container_width=True)
            if send_ann:
                if announce_to and announce_subj and announce_body:
                    html = f"<html><body style='font-family:Arial;padding:20px;'><p>{announce_body}</p><br><p style='color:#888;font-size:12px;'>PetroApp — Governance Tool</p></body></html>"
                    ok, _ = send_email_generic(announce_subj, html, [announce_to])
                    st.success("✅ Sent!") if ok else st.error("Failed to send.")
                else:
                    st.error("Please fill all fields.")
