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
import base64
import json

# ── Constants ─────────────────────────────────────────────────────────────────
ADMIN_EMAIL    = "a.hassan@petroapp.com"
ALLOWED_DOMAIN = "petroapp.com"
TO_EMAIL       = "quality.assurance@petroapp.com"
CC_EMAILS      = ["osama.adel@petroapp.com", "a.hassan@petroapp.com", "mohamed.yassin@petroapp.com"]
DOCS_FOLDER    = "documents"
FAQ_COUNTS_FILE = "faq_counts.json"

DEFAULT_FAQS = [
    "What is the process for business plan approval?",
    "What are the approval limits for contracts?",
    "Who can approve travel expenses?",
    "What is the process for salary changes?",
    "What is the DOA for new hiring?"
]

NOT_FOUND_PHRASES = [
    # ── English ──────────────────────────────────────────────────────────────
    "could not find this information",
    "could not find",
    "not found in the provided",
    "not found in the document",
    "not available in the document",
    "no information about",
    "no information on",
    "cannot find",
    "can't find",
    "unable to find",
    "not mentioned in",
    "not covered in",
    "does not contain information",
    "there is no information",
    "i don't have information",
    "i do not have information",
    "not included in",
    "not in the documents",
    "no relevant information",
    "outside the scope",
    "not address",
    "not specify",
    "does not specify",
    "no details",
    "no specific information",
    # ── Arabic ───────────────────────────────────────────────────────────────
    "لم أجد",
    "لم يتم ذكر",
    "لم أتمكن",
    "لا تتوفر",
    "لا يوجد",
    "لا توجد",
    "غير موجود",
    "غير مذكور",
    "غير متوفر",
    "لا أملك معلومات",
    "ليس في المستندات",
    "لا يمكنني إيجاد",
    "لا تحتوي",
    "لم تتضمن",
    "لم يرد",
    "لم يُذكر",
    "لا يتضمن",
]

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

# ── PetroApp P Logo SVG ───────────────────────────────────────────────────────
# Built to match the exact PetroApp brand:
# - Tall vertical stem
# - Thick rounded bowl on the right (top half), small inner counter
# - Square bracket extending LEFT from stem at bowl-bottom level
_LOGO_BLUE = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140">
  <rect x="28" y="0" width="19" height="140" fill="#2080E5"/>
  <path fill="#2080E5" d="M 47,0 L 58,0 A 33,33 0 0 1 58,66 L 28,66 L 28,0 Z"/>
  <rect x="6" y="49" width="22" height="22" fill="#2080E5"/>
  <path fill="white" d="M 47,17 L 52,17 A 16,16 0 0 1 52,49 L 47,49 Z"/>
</svg>'''

_LOGO_WHITE = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140">
  <rect x="28" y="0" width="19" height="140" fill="white"/>
  <path fill="white" d="M 47,0 L 58,0 A 33,33 0 0 1 58,66 L 28,66 L 28,0 Z"/>
  <rect x="6" y="49" width="22" height="22" fill="white"/>
  <path fill="#2080E5" d="M 47,17 L 52,17 A 16,16 0 0 1 52,49 L 47,49 Z"/>
</svg>'''

def _b64img(svg, w, h):
    b64 = base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{b64}" width="{w}" height="{h}" style="display:block;"/>'

LOGO_LG    = _b64img(_LOGO_BLUE,  80, 80)
LOGO_SM    = _b64img(_LOGO_WHITE, 40, 40)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
* { font-family: 'Inter', sans-serif; }
.stApp { background-color: #f0f4ff; }

@keyframes fadeSlideIn { from{opacity:0;transform:translateY(24px)} to{opacity:1;transform:translateY(0)} }
@keyframes glowPulse   { 0%{box-shadow:0 0 0 0 rgba(32,128,229,.3)} 50%{box-shadow:0 0 0 18px rgba(32,128,229,0)} 100%{box-shadow:0 0 0 0 rgba(32,128,229,0)} }
@keyframes floatLogo   { 0%{transform:translateY(0)} 50%{transform:translateY(-6px)} 100%{transform:translateY(0)} }

.login-wrapper { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:78vh; animation:fadeSlideIn .6s ease-out; }
.petro-logo-wrap { animation:glowPulse 2.5s infinite, floatLogo 3s ease-in-out infinite; border-radius:16px; display:inline-flex; align-items:center; justify-content:center; margin-bottom:20px; }
.login-title { font-size:28px; font-weight:700; color:#1e3a8a; margin:8px 0 4px 0; text-align:center; }
.login-sub   { font-size:14px; color:#2080E5; font-weight:500; margin-bottom:4px; text-align:center; }
.login-restricted { font-size:12px; color:#94a3b8; margin-bottom:28px; text-align:center; }

.petroapp-header { background:linear-gradient(90deg,#1B4FD8,#2080E5,#3b82f6); padding:14px 24px; border-radius:14px; margin-bottom:20px; display:flex; align-items:center; gap:14px; box-shadow:0 4px 20px rgba(32,128,229,.25); }
.header-logo { width:48px; height:48px; background:rgba(255,255,255,.15); border-radius:10px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.header-title h1 { color:white; font-size:20px; margin:0; font-weight:700; }
.header-title p  { color:rgba(255,255,255,.75); font-size:12px; margin:2px 0 0 0; }

.admin-badge { background:linear-gradient(90deg,#2080E5,#1B4FD8); color:white; border-radius:20px; padding:2px 12px; font-size:11px; font-weight:600; display:inline-block; margin-left:8px; vertical-align:middle; }
.error-card { background:#fef2f2; border:1px solid #fecaca; border-radius:12px; padding:16px 20px; margin-top:12px; }
.notfound-actions { background:#eff6ff; border:1px solid #bfdbfe; border-radius:12px; padding:14px 18px; margin-top:10px; }

.stButton > button { background-color:#2080E5 !important; color:white !important; border:none !important; border-radius:10px !important; font-weight:600 !important; }
.stButton > button:hover { background-color:#1B4FD8 !important; }
.stTabs [data-baseweb="tab"] { background:#e8f0fe; border-radius:8px 8px 0 0; color:#2080E5; font-weight:600; }
.stTabs [aria-selected="true"] { background:#2080E5 !important; color:white !important; }
section[data-testid="stSidebar"] { background:#f0f5ff; }
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
    "pending_question": None,
    "prefill_inquiry": "",
    "show_inquiry_form": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

is_admin = st.session_state.user_email.lower() == ADMIN_EMAIL

# ══════════════════════════════════════════════════════════════════════════════
# FAQ FREQUENCY TRACKING
# ══════════════════════════════════════════════════════════════════════════════
def load_faq_counts():
    if os.path.exists(FAQ_COUNTS_FILE):
        try:
            with open(FAQ_COUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_faq_counts(counts):
    try:
        with open(FAQ_COUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(counts, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def track_question(question: str):
    counts = load_faq_counts()
    counts[question] = counts.get(question, 0) + 1
    save_faq_counts(counts)

def get_dynamic_faqs(n=5):
    counts = load_faq_counts()
    if len(counts) >= n:
        sorted_q = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [q for q, _ in sorted_q[:n]]
    top = [q for q, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)]
    needed = [f for f in DEFAULT_FAQS if f not in top]
    return (top + needed)[:n]

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
    context = ""
    if not os.path.exists(DOCS_FOLDER):
        return context
    files = []
    for p in ["*.pdf","*.docx","*.xlsx"]:
        files.extend(glob.glob(os.path.join(DOCS_FOLDER, p)))
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, "rb") as f:
                context += f"\n\n=== Document: {fname} ===\n{extract_text(f, fname)}"
        except Exception as e:
            context += f"\n\n=== Document: {fname} ===\n[Error: {e}]"
    return context


def send_email_generic(subject, html_body, to):
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


def send_request_email(name, email, details):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<html><body style="font-family:Inter,Arial,sans-serif;color:#333;padding:24px;">
        <div style="background:linear-gradient(90deg,#1B4FD8,#2080E5);padding:18px 28px;border-radius:12px;margin-bottom:20px;">
            <h2 style="color:white;margin:0;">New Request / Inquiry — PetroApp</h2></div>
        <table style="border-collapse:collapse;width:100%;max-width:620px;">
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;width:140px;border:1px solid #ddd;">Name</td><td style="padding:10px;border:1px solid #ddd;">{name}</td></tr>
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Email</td><td style="padding:10px;border:1px solid #ddd;">{email}</td></tr>
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Time</td><td style="padding:10px;border:1px solid #ddd;">{now}</td></tr>
            <tr><td style="padding:10px;background:#f0f5ff;font-weight:bold;border:1px solid #ddd;">Details</td><td style="padding:10px;border:1px solid #ddd;">{details}</td></tr>
        </table>
        <p style="color:#888;font-size:12px;margin-top:20px;">PetroApp — Governance Tool</p>
    </body></html>"""
    ok, msg = send_email_generic(f"New Request/Inquiry — {name} ({now})", html,
                                  [TO_EMAIL] + CC_EMAILS + [email])
    if ok:
        confirm = f"""<html><body style="font-family:Inter,Arial,sans-serif;color:#333;padding:24px;">
            <div style="background:linear-gradient(90deg,#1B4FD8,#2080E5);padding:18px 28px;border-radius:12px;margin-bottom:20px;">
                <h2 style="color:white;margin:0;">Request Submitted</h2></div>
            <p>Dear <strong>{name}</strong>, your request has been submitted to the QA and Governance team.</p>
            <blockquote style="border-left:4px solid #2080E5;padding:10px 16px;background:#f0f5ff;border-radius:0 8px 8px 0;">{details}</blockquote>
            <p style="color:#888;font-size:12px;margin-top:20px;">PetroApp — Governance Tool</p>
        </body></html>"""
        send_email_generic("Your Request Has Been Submitted", confirm, [email])
    return ok, msg


def send_error_report(user_email, error_text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<html><body style="font-family:Inter,Arial,sans-serif;color:#333;padding:24px;">
        <div style="background:#dc2626;padding:18px 28px;border-radius:12px;margin-bottom:20px;">
            <h2 style="color:white;margin:0;">Chatbot Error Report</h2></div>
        <table style="border-collapse:collapse;width:100%;max-width:620px;">
            <tr><td style="padding:10px;background:#fef2f2;font-weight:bold;width:130px;border:1px solid #ddd;">User</td><td style="padding:10px;border:1px solid #ddd;">{user_email}</td></tr>
            <tr><td style="padding:10px;background:#fef2f2;font-weight:bold;border:1px solid #ddd;">Time</td><td style="padding:10px;border:1px solid #ddd;">{now}</td></tr>
            <tr><td style="padding:10px;background:#fef2f2;font-weight:bold;border:1px solid #ddd;">Error</td><td style="padding:10px;border:1px solid #ddd;color:#dc2626;font-family:monospace;">{error_text}</td></tr>
        </table>
        <p style="color:#888;font-size:12px;margin-top:20px;">PetroApp — Governance Tool</p>
    </body></html>"""
    return send_email_generic(f"Chatbot Error — {now}", html, [ADMIN_EMAIL])


def send_qa_report_for_unanswered(user_email, user_name, question):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<html><body style="font-family:Inter,Arial,sans-serif;color:#333;padding:24px;">
        <div style="background:linear-gradient(90deg,#f59e0b,#d97706);padding:18px 28px;border-radius:12px;margin-bottom:20px;">
            <h2 style="color:white;margin:0;">Unanswered Question Reported</h2></div>
        <table style="border-collapse:collapse;width:100%;max-width:620px;">
            <tr><td style="padding:10px;background:#fffbeb;font-weight:bold;width:140px;border:1px solid #ddd;">User</td><td style="padding:10px;border:1px solid #ddd;">{user_name} ({user_email})</td></tr>
            <tr><td style="padding:10px;background:#fffbeb;font-weight:bold;border:1px solid #ddd;">Time</td><td style="padding:10px;border:1px solid #ddd;">{now}</td></tr>
            <tr><td style="padding:10px;background:#fffbeb;font-weight:bold;border:1px solid #ddd;">Question</td><td style="padding:10px;border:1px solid #ddd;">{question}</td></tr>
        </table>
        <p style="color:#888;font-size:12px;margin-top:20px;">PetroApp — Governance Tool — This question was not found in the current documents.</p>
    </body></html>"""
    return send_email_generic(f"Unanswered Question — {now}", html,
                               [TO_EMAIL] + CC_EMAILS)


def call_claude(messages_history, document_context):
    system_prompt = f"""You are a precise assistant for the QA and Governance department at PetroApp.
Your ONLY source of information is the documents provided below. Do NOT use any external knowledge.

STRICT RULES:
1. Read the documents exactly as written. Never paraphrase, combine, or assume roles.
2. When answering about tables (e.g., Develop / Endorse / Approve columns), list each column SEPARATELY and copy the exact names from the document. Do NOT mix values between columns.
3. If a table has columns like [Decision | Develop | Endorse | Approve], make sure you read each row left to right and keep each column's value in the correct place.
4. Do NOT include BOD (Board of Directors) level authorities unless the user explicitly asks about BOD.
5. ALWAYS try your best to answer from the documents:
   - First: look for an exact match to the question.
   - If no exact match: find the NEAREST or MOST RELATED topic in the documents and share it, clearly stating it is the closest match found.
   - Only if truly nothing related exists at all: say "I could not find this information in the provided documents."
6. Never leave the user with no information — always share the nearest relevant content you can find.
7. Answer in the same language the user writes in (Arabic or English).
8. Always end every response with this line:
---
For further assistance, please contact the QA and Governance team directly.

--- DOCUMENTS ---
{document_context}
--- END ---"""

    client = anthropic.Anthropic(api_key=API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages_history]
    )
    return response.content[0].text


def is_not_found_answer(answer: str) -> bool:
    low = answer.lower()
    return any(phrase.lower() in low for phrase in NOT_FOUND_PHRASES)


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown(
            f'<div class="login-wrapper">'
            f'<div class="petro-logo-wrap">{LOGO_LG}</div>'
            f'<div class="login-title">QA &amp; Governance Chatbot</div>'
            f'<div class="login-sub">PetroApp — Governance Tool</div>'
            f'<div class="login-restricted">Access restricted to PetroApp employees only</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        with st.form("login_form"):
            name  = st.text_input("Full Name", placeholder="Ahmed Hassan")
            email = st.text_input("Work Email", placeholder="name@petroapp.com")
            login = st.form_submit_button("Sign In →", use_container_width=True)

        if login:
            if not name.strip() or not email.strip():
                st.error("Please enter your name and email.")
            elif not email.strip().lower().endswith(f"@{ALLOWED_DOMAIN}"):
                st.error(f"Access denied. Only @{ALLOWED_DOMAIN} emails are allowed.")
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
repo_doc_context = load_repo_documents()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    admin_label = ' <span class="admin-badge">ADMIN</span>' if is_admin else ""
    st.markdown(f"👤 **{st.session_state.user_name}**{admin_label}", unsafe_allow_html=True)
    st.caption(st.session_state.user_email)

    if st.button("🚪 Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
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
        repo_count = len(glob.glob(os.path.join(DOCS_FOLDER,"*.*"))) if os.path.exists(DOCS_FOLDER) else 0
        st.caption(f"API Key: {'✅ Configured' if API_KEY else '❌ Missing'}")
        st.caption(f"Email:   {'✅ Configured' if SMTP_EMAIL else '❌ Missing'}")
        st.caption(f"Repo Docs: {repo_count} file(s)")
    else:
        if repo_doc_context or st.session_state.uploaded_docs_context:
            st.success("📂 Documents are loaded and ready!")
        else:
            st.info("Documents are being prepared.")

    st.markdown("---")
    st.caption("🔒 PetroApp — Governance Tool")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div class="petroapp-header">'
    f'<div class="header-logo">{LOGO_SM}</div>'
    f'<div class="header-title">'
    f'<h1>QA &amp; Governance Chatbot</h1>'
    f'<p>Welcome, {st.session_state.user_name} · {st.session_state.user_email}</p>'
    f'</div></div>',
    unsafe_allow_html=True
)

document_context = repo_doc_context + st.session_state.uploaded_docs_context

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_labels = ["💬 Ask a Question", "📋 New Request / Inquiry"]
if is_admin:
    tab_labels.append("🛠️ Admin Panel")

tab_objects = st.tabs(tab_labels)
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
        # ── Dynamic Quick Questions ──
        dynamic_faqs = get_dynamic_faqs(5)
        st.markdown("**💡 Most Asked Questions:**")
        cols = st.columns(len(dynamic_faqs))
        for i, faq in enumerate(dynamic_faqs):
            with cols[i]:
                if st.button(faq, key=f"faq_{i}", use_container_width=True):
                    st.session_state.pending_question = faq
                    st.rerun()

        st.markdown("---")

        # ── Chat history ──
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                # Show action buttons under not-found assistant answers
                if msg["role"] == "assistant" and is_not_found_answer(msg["content"]):
                    # Find the user question that triggered this answer
                    user_q = ""
                    if idx > 0 and st.session_state.messages[idx-1]["role"] == "user":
                        user_q = st.session_state.messages[idx-1]["content"]
                    if st.button("📋 Submit Request to Gov Team", key=f"submit_gov_{idx}"):
                        st.session_state.prefill_inquiry = user_q
                        if SMTP_EMAIL and SMTP_PASSWORD:
                            send_qa_report_for_unanswered(
                                st.session_state.user_email,
                                st.session_state.user_name,
                                user_q
                            )
                        st.info("👉 Click the **'📋 New Request / Inquiry'** tab above — it's been pre-filled with your question.")

        # ── Chat input ──
        user_input = st.chat_input("Ask a question about Policies, Procedures, or DOA...")
        question_to_process = user_input or st.session_state.get("pending_question")

        if question_to_process:
            if st.session_state.get("pending_question"):
                st.session_state.pending_question = None

            if not API_KEY:
                err = "Claude API Key is not configured. Please contact the admin."
                st.error(err)
                st.session_state.last_error = err
            else:
                st.session_state.messages.append({"role": "user", "content": question_to_process})
                track_question(question_to_process)

                with st.chat_message("user"):
                    st.write(question_to_process)

                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            answer = call_claude(st.session_state.messages, document_context)
                            st.write(answer)
                            st.session_state.messages.append({"role": "assistant", "content": answer})
                            st.session_state.last_error = None

                            # Single button if not found
                            if is_not_found_answer(answer):
                                if st.button("📋 Submit Request to Gov Team", key="submit_gov_new"):
                                    st.session_state.prefill_inquiry = question_to_process
                                    if SMTP_EMAIL and SMTP_PASSWORD:
                                        send_qa_report_for_unanswered(
                                            st.session_state.user_email,
                                            st.session_state.user_name,
                                            question_to_process
                                        )
                                    st.info("👉 Click the **'📋 New Request / Inquiry'** tab above — it's been pre-filled with your question.")
                        except Exception as e:
                            err_msg = str(e)
                            st.session_state.last_error = err_msg
                            st.markdown(
                                f'<div class="error-card"><strong>⚠️ Something went wrong</strong><br>'
                                f'<small style="color:#666;">{err_msg}</small></div>',
                                unsafe_allow_html=True
                            )

        # ── Report system error button ──
        if st.session_state.last_error:
            st.markdown("---")
            if st.button("🚨 Report this error to Admin"):
                if SMTP_EMAIL and SMTP_PASSWORD:
                    ok, _ = send_error_report(st.session_state.user_email, st.session_state.last_error)
                    st.success("✅ Error reported!") if ok else st.error("Could not send. Contact a.hassan@petroapp.com")
                    if ok:
                        st.session_state.last_error = None
                else:
                    st.warning("Email not configured. Contact a.hassan@petroapp.com directly.")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — New Request / Inquiry
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("📋 New Request / Inquiry")
    st.write("Submit a request or inquiry to the QA and Governance team. We will review and respond as soon as possible.")

    prefill = st.session_state.get("prefill_inquiry", "")

    with st.form("request_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            req_name  = st.text_input("Your Full Name *", value=st.session_state.user_name)
        with c2:
            req_email = st.text_input("Your Email *", value=st.session_state.user_email)
        req_details = st.text_area(
            "Your request or inquiry *",
            value=prefill,
            placeholder="Describe your request, question, or the authority you would like to add/modify.",
            height=150
        )
        submitted = st.form_submit_button("📤 Submit", use_container_width=True, type="primary")

    if submitted:
        st.session_state.prefill_inquiry = ""
        if not req_name.strip() or not req_email.strip() or not req_details.strip():
            st.error("Please fill in all required fields.")
        elif "@" not in req_email:
            st.error("Please enter a valid email address.")
        elif not SMTP_EMAIL or not SMTP_PASSWORD:
            st.warning("⚠️ Email is not configured. Contact a.hassan@petroapp.com directly.")
        else:
            with st.spinner("Sending your request..."):
                ok, msg = send_request_email(req_name.strip(), req_email.strip(), req_details.strip())
            if ok:
                st.success("✅ Request submitted! A confirmation email has been sent to your inbox.")
            else:
                st.error(f"Failed to send. Error: {msg}")

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — Admin Panel
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
            st.metric("API Key",    "✅ Active" if API_KEY    else "❌ Missing")
            st.metric("Email Config","✅ Active" if SMTP_EMAIL else "❌ Missing")

            st.markdown("### 📈 Top Questions Asked")
            counts = load_faq_counts()
            if counts:
                sorted_q = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
                for q, c in sorted_q:
                    st.caption(f"({c}x) {q}")
                if st.button("🗑️ Reset Question Counts"):
                    save_faq_counts({})
                    st.success("Counts reset.")
            else:
                st.caption("No questions tracked yet.")

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
            """)
            st.markdown("### 📧 Send Announcement")
            with st.form("admin_announce"):
                ann_to   = st.text_input("To (email)")
                ann_subj = st.text_input("Subject")
                ann_body = st.text_area("Message", height=100)
                send_ann = st.form_submit_button("📤 Send", use_container_width=True)
            if send_ann:
                if ann_to and ann_subj and ann_body:
                    html = f"<html><body style='font-family:Arial;padding:20px;'><p>{ann_body}</p><p style='color:#888;font-size:12px;'>PetroApp — Governance Tool</p></body></html>"
                    ok, _ = send_email_generic(ann_subj, html, [ann_to])
                    st.success("✅ Sent!") if ok else st.error("Failed.")
                else:
                    st.error("Please fill all fields.")
                    
