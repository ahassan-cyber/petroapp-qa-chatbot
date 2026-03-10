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
ADMIN_EMAIL     = "a.hassan@petroapp.com"
ALLOWED_DOMAIN  = "petroapp.com"
TO_EMAIL        = "quality.assurance@petroapp.com"
CC_EMAILS       = ["osama.adel@petroapp.com", "a.hassan@petroapp.com", "mohamed.yassin@petroapp.com"]
DOCS_FOLDER        = "documents"
FAQ_COUNTS_FILE    = "faq_counts.json"
INQUIRY_COUNT_FILE = "inquiry_count.json"

# RAG Settings
CHUNK_SIZE     = 700   # words per chunk
CHUNK_OVERLAP  = 80    # word overlap between chunks
TOP_K_CHUNKS   = 10    # how many chunks to send to Claude per question

DEFAULT_FAQS = [
    "What is the process for business plan approval?",
    "What are the approval limits for contracts?",
    "Who can approve travel expenses?",
    "What is the process for salary changes?",
    "What is the DOA for new hiring?"
]

NOT_FOUND_PHRASES = [
    "could not find this information", "could not find",
    "not found in the provided", "not found in the document",
    "not available in the document", "no information about",
    "no information on", "cannot find", "can't find",
    "unable to find", "not mentioned in", "not covered in",
    "does not contain information", "there is no information",
    "i don't have information", "i do not have information",
    "not included in", "not in the documents", "no relevant information",
    "outside the scope", "not address", "not specify",
    "does not specify", "no details", "no specific information",
    "لم أجد", "لم يتم ذكر", "لم أتمكن", "لا تتوفر", "لا يوجد",
    "لا توجد", "غير موجود", "غير مذكور", "غير متوفر",
    "لا أملك معلومات", "ليس في المستندات", "لا يمكنني إيجاد",
    "لا تحتوي", "لم تتضمن", "لم يرد", "لم يُذكر", "لا يتضمن",
]

# ── Category Keywords for auto-detect ─────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "doa": [
        "doa", "delegation", "authority", "authorities", "approve", "approval",
        "signatory", "authorized", "matrix", "limit", "financial limit", "delegate",
        "تفويض", "صلاحية", "صلاحيات", "موافقة", "اعتماد", "مصفوفة", "تفويضات",
    ],
    "hr": [
        "hr", "human resources", "salary", "hiring", "hire", "employee",
        "job offer", "probation", "termination", "bonus", "commission",
        "recruitment", "staff", "personnel", "onboarding", "increment",
        "موظف", "موظفين", "راتب", "توظيف", "مكافأة", "عمولة", "تعيين",
    ],
    "finance": [
        "finance", "financial", "budget", "fp&a", "cost", "revenue",
        "accounting", "invoice", "payment", "capex", "opex",
        "تمويل", "مالية", "ميزانية", "محاسبة", "فاتورة",
    ],
    "sales": [
        "sales", "commission", "discount", "fuel", "washing", "station",
        "bonus scheme", "target", "incentive", "ksa", "egypt",
        "مبيعات", "عمولة", "خصم", "حوافز", "وقود", "محطة",
    ],
    "it": [
        "it", "tools", "software", "system", "infrastructure", "tool request",
        "تقنية", "أنظمة", "برامج", "أدوات", "بنية تحتية",
    ],
    "operations": [
        "operations", "station", "fuel station", "washing", "service", "field",
        "عمليات", "محطة", "خدمات", "ميدان",
    ],
    "customer_experience": [
        "customer", "experience", "cx", "complaint", "feedback", "support",
        "عملاء", "تجربة العملاء", "شكاوى", "دعم",
    ],
}

# Subfolder → which categories it belongs to
SUBFOLDER_CATEGORY_MAP = {
    "policies/doa":             ["doa"],
    "policies/hr":              ["hr"],
    "policies/sales":           ["sales"],
    "policies/finance":         ["finance"],
    "policies/it":              ["it"],
    "policies/general":         ["hr", "finance", "doa"],
    "sops/customer_experience": ["customer_experience"],
    "sops/operations":          ["operations", "sales"],
    "sops/sales":               ["sales"],
    "sops/finance":             ["finance"],
    "sops/it":                  ["it"],
}

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

# ── PetroApp Logo — load from assets/logo.png ────────────────────────────────
def _load_logo_b64(path: str) -> str | None:
    """Load a PNG file and return base64 string, or None if not found."""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

def _png_img(b64: str, w: int, h: int, style: str = "") -> str:
    return (f'<img src="data:image/png;base64,{b64}" '
            f'width="{w}" height="{h}" style="display:block;{style}"/>')

def _svg_fallback_img(color: str, w: int, h: int) -> str:
    """Fallback SVG if PNG not available."""
    fill = color
    inner = "white" if color != "white" else "#2080E5"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140">'
           f'<rect x="28" y="0" width="19" height="140" fill="{fill}"/>'
           f'<path fill="{fill}" d="M 47,0 L 58,0 A 33,33 0 0 1 58,66 L 28,66 L 28,0 Z"/>'
           f'<rect x="6" y="49" width="22" height="22" fill="{fill}"/>'
           f'<path fill="{inner}" d="M 47,17 L 52,17 A 16,16 0 0 1 52,49 L 47,49 Z"/>'
           f'</svg>')
    b64 = base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{b64}" width="{w}" height="{h}" style="display:block;"/>'

_LOGO_PNG_B64 = _load_logo_b64("assets/logo.png")

if _LOGO_PNG_B64:
    LOGO_LG = _png_img(_LOGO_PNG_B64, 80, 80)
    LOGO_SM = _png_img(_LOGO_PNG_B64, 40, 40)
else:
    LOGO_LG = _svg_fallback_img("#2080E5", 80, 80)
    LOGO_SM = _svg_fallback_img("white",   40, 40)

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
.header-logo { width:52px; height:52px; background:white; border-radius:10px; display:flex; align-items:center; justify-content:center; flex-shrink:0; padding:4px; overflow:hidden; }
.header-title h1 { color:white; font-size:20px; margin:0; font-weight:700; }
.header-title p  { color:rgba(255,255,255,.75); font-size:12px; margin:2px 0 0 0; }

.admin-badge { background:linear-gradient(90deg,#2080E5,#1B4FD8); color:white; border-radius:20px; padding:2px 12px; font-size:11px; font-weight:600; display:inline-block; margin-left:8px; vertical-align:middle; }
.error-card { background:#fef2f2; border:1px solid #fecaca; border-radius:12px; padding:16px 20px; margin-top:12px; }
.chunk-info { background:#f0f9ff; border:1px solid #bae6fd; border-radius:8px; padding:8px 12px; margin-top:6px; font-size:11px; color:#0369a1; }

.stButton > button { background-color:#2080E5 !important; color:white !important; border:none !important; border-radius:10px !important; font-weight:600 !important; }
.stButton > button:hover { background-color:#1B4FD8 !important; }
.stTabs [data-baseweb="tab"] { background:#e8f0fe; border-radius:8px 8px 0 0; color:#2080E5; font-weight:600; }
.stTabs [aria-selected="true"] { background:#2080E5 !important; color:white !important; }
section[data-testid="stSidebar"] { background:#f0f5ff; }

/* ── Inquiry Counter Card ──────────────────────────────────────────────── */
.inquiry-counter-card {
    background: linear-gradient(135deg, #1a3c8f 0%, #2080E5 100%);
    border-radius: 14px;
    padding: 16px 18px;
    color: white;
    position: relative;
    overflow: hidden;
    margin: 4px 0;
}
.inquiry-counter-card::after {
    content: '';
    position: absolute; top: -24px; right: -24px;
    width: 90px; height: 90px;
    background: rgba(255,255,255,0.07);
    border-radius: 50%;
}
.counter-lbl  { font-size: 10px; font-weight: 700; color: rgba(255,255,255,0.7); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
.counter-num  { font-size: 36px; font-weight: 800; line-height: 1; }
.counter-desc { font-size: 11px; color: rgba(255,255,255,0.65); margin-top: 3px; }

/* ── Option C: Chat Input Highlight ───────────────────────────────────── */
[data-testid="stBottom"],
section[data-testid="stBottom"],
div[data-testid="stBottom"],
.stChatFloatingInputContainer {
    background: linear-gradient(135deg, #1a3c8f 0%, #1a6cf5 100%) !important;
    padding: 14px 20px 14px 20px !important;
    border-radius: 14px 14px 0 0 !important;
    box-shadow: 0 -4px 20px rgba(26,108,245,0.2) !important;
}
[data-testid="stBottom"]::before,
section[data-testid="stBottom"]::before,
.stChatFloatingInputContainer::before {
    content: "🔍  Ask a question about your company Framework";
    display: block;
    color: rgba(255,255,255,0.85);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
    font-family: 'Inter', sans-serif;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] > div > div {
    background: white !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.15) !important;
    border: none !important;
}
[data-testid="stChatInput"] textarea {
    font-size: 15px !important;
    color: #333 !important;
}
.stChatInput {
    background: white !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.15) !important;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ══════════════════════════════════════════════════════════════════════════════
for key, val in {
    "authenticated":        False,
    "user_email":           "",
    "user_name":            "",
    "messages":             [],
    "last_error":           None,
    "pending_question":     None,
    "prefill_inquiry":      "",
    "uploaded_chunks":      [],
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
# INQUIRY COUNTER
# ══════════════════════════════════════════════════════════════════════════════
def load_inquiry_count() -> int:
    if os.path.exists(INQUIRY_COUNT_FILE):
        try:
            with open(INQUIRY_COUNT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("total", 0)
        except Exception:
            pass
    return 0

def increment_inquiry_count():
    count = load_inquiry_count() + 1
    try:
        with open(INQUIRY_COUNT_FILE, "w", encoding="utf-8") as f:
            json.dump({"total": count}, f)
    except Exception:
        pass
    return count

# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT PROCESSING — CHUNKING RAG
# ══════════════════════════════════════════════════════════════════════════════
def extract_text(file, filename: str = "") -> str:
    name = (filename or getattr(file, 'name', '')).lower()
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


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if not words:
        return []
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


@st.cache_data(show_spinner=False)
def load_documents_chunked() -> list:
    """
    Load all documents from documents/ folder (flat or subfolders).
    Returns list of chunk dicts: {source, subfolder, chunk_id, total_chunks, text}
    """
    all_chunks = []
    if not os.path.exists(DOCS_FOLDER):
        return all_chunks

    # Find all files (recursive for subfolders + flat)
    all_files = []
    for ext in ["*.pdf", "*.docx", "*.xlsx"]:
        all_files.extend(glob.glob(os.path.join(DOCS_FOLDER, "**", ext), recursive=True))
    all_files = sorted(set(all_files))

    for fpath in all_files:
        fname = os.path.basename(fpath)
        rel_path  = os.path.relpath(fpath, DOCS_FOLDER)
        subfolder = os.path.dirname(rel_path).replace("\\", "/")

        try:
            with open(fpath, "rb") as f:
                full_text = extract_text(f, fname)

            if not full_text.strip():
                continue

            doc_chunks = chunk_text(full_text)
            for i, chunk in enumerate(doc_chunks):
                all_chunks.append({
                    "source":       fname,
                    "subfolder":    subfolder,
                    "chunk_id":     i,
                    "total_chunks": len(doc_chunks),
                    "text":         chunk,
                })
        except Exception as e:
            all_chunks.append({
                "source":       fname,
                "subfolder":    subfolder,
                "chunk_id":     0,
                "total_chunks": 1,
                "text":         f"[Error reading {fname}: {e}]",
            })

    return all_chunks


def detect_category(question: str) -> str | None:
    """Detect most likely category from question keywords."""
    q_lower = question.lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in q_lower:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def get_relevant_chunks(question: str, all_chunks: list, top_k: int = TOP_K_CHUNKS) -> list:
    """
    Score each chunk by keyword overlap + subfolder category boost.
    Returns top-k most relevant chunks in document order.
    """
    if not all_chunks:
        return []

    q_words  = set(question.lower().split())
    detected = detect_category(question)
    scored   = []

    for i, chunk in enumerate(all_chunks):
        chunk_words = set(chunk["text"].lower().split())
        overlap     = len(q_words & chunk_words)

        # Boost if chunk belongs to the detected category's subfolder
        cat_boost = 0
        if detected:
            subfolder = chunk.get("subfolder", "").lower()
            for key_sf, cats in SUBFOLDER_CATEGORY_MAP.items():
                if key_sf in subfolder and detected in cats:
                    cat_boost = 5
                    break

        score = overlap + cat_boost
        if score > 0:
            scored.append((score, i))

    scored.sort(reverse=True)
    top_indices = sorted([i for _, i in scored[:top_k]])

    # If nothing scored, fall back to first top_k chunks
    if not top_indices:
        top_indices = list(range(min(top_k, len(all_chunks))))

    return [all_chunks[i] for i in top_indices]


def chunks_to_context(chunks: list) -> str:
    """Format chunks into a readable context string for Claude."""
    parts = []
    for c in chunks:
        header = f"=== {c['source']}"
        if c['total_chunks'] > 1:
            header += f" (part {c['chunk_id']+1}/{c['total_chunks']})"
        if c['subfolder'] and c['subfolder'] != ".":
            header += f" [{c['subfolder']}]"
        header += " ==="
        parts.append(f"{header}\n{c['text']}")
    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL HELPERS
# ══════════════════════════════════════════════════════════════════════════════
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
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
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
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
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
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
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
    return send_email_generic(f"Unanswered Question — {now}", html, [TO_EMAIL] + CC_EMAILS)


# ══════════════════════════════════════════════════════════════════════════════
# CLAUDE API CALL — SMART RAG
# ══════════════════════════════════════════════════════════════════════════════
def call_claude(messages_history: list, all_chunks: list) -> str:
    # Get the latest user question for chunk selection
    latest_q = ""
    for msg in reversed(messages_history):
        if msg["role"] == "user":
            latest_q = msg["content"]
            break

    # Select relevant chunks
    relevant = get_relevant_chunks(latest_q, all_chunks, TOP_K_CHUNKS)
    document_context = chunks_to_context(relevant)
    detected_cat = detect_category(latest_q)

    system_prompt = f"""You are a precise assistant for the QA and Governance department at PetroApp.
Your ONLY source of information is the document excerpts provided below. Do NOT use any external knowledge.

STRICT RULES:
1. Read the documents exactly as written. Never paraphrase, combine, or assume roles.
2. When answering about tables (e.g., Develop / Endorse / Approve columns), list each column SEPARATELY
   and copy the exact names from the document. Do NOT mix values between columns.
3. If a table has columns like [Decision | Develop | Endorse | Approve], read each row left to right
   and keep each column's value in the correct place.
4. Do NOT include BOD (Board of Directors) level authorities unless the user explicitly asks about BOD.
5. ALWAYS try your best to answer from the documents:
   - First: look for an exact match.
   - If no exact match: find the NEAREST or MOST RELATED topic and share it, clearly stating it is the closest match.
   - Only if truly nothing related exists: say "I could not find this information in the provided documents."
6. Never leave the user with no information — always share the nearest relevant content you can find.
7. Answer in the same language the user writes in (Arabic or English).
8. Always end every response with:
---
For further assistance, please contact the QA and Governance team directly.

--- DOCUMENT EXCERPTS ---
{document_context}
--- END ---"""

    client   = anthropic.Anthropic(api_key=API_KEY)
    response = client.messages.create(
        model      = "claude-haiku-4-5-20251001",
        max_tokens = 1024,
        system     = system_prompt,
        messages   = [{"role": m["role"], "content": m["content"]} for m in messages_history]
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
            name  = st.text_input("Full Name",   placeholder="Ahmed Hassan")
            email = st.text_input("Work Email",  placeholder="name@petroapp.com")
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
# MAIN APP — Load chunks
# ══════════════════════════════════════════════════════════════════════════════
is_admin    = st.session_state.user_email.lower() == ADMIN_EMAIL
repo_chunks = load_documents_chunked()
all_chunks  = repo_chunks + st.session_state.get("uploaded_chunks", [])

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    admin_label = ' <span class="admin-badge">ADMIN</span>' if is_admin else ""
    st.markdown(f"👤 **{st.session_state.user_name}**{admin_label}", unsafe_allow_html=True)
    st.caption(st.session_state.user_email)

    if st.button("🚪 Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    # ── Inquiry Counter — visible to ALL users — TOP of sidebar ──
    st.markdown("---")
    inquiry_total = load_inquiry_count()
    st.markdown(
        f'<div class="inquiry-counter-card">'
        f'<div class="counter-lbl">📋 Inquiries Submitted</div>'
        f'<div class="counter-num">{inquiry_total}</div>'
        f'<div class="counter-desc">Total requests to Gov Team</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    st.markdown("---")

    if is_admin:
        st.markdown("## 📁 Upload Documents")
        st.caption("Upload files (session only — for permanent: add to GitHub)")
        uploaded_files = st.file_uploader(
            "Upload files", type=["pdf", "docx", "xlsx"],
            accept_multiple_files=True, label_visibility="collapsed"
        )
        if uploaded_files:
            new_chunks = []
            for f in uploaded_files:
                text = extract_text(f, f.name)
                doc_chunks = chunk_text(text)
                for i, ch in enumerate(doc_chunks):
                    new_chunks.append({
                        "source":       f.name,
                        "subfolder":    "uploaded",
                        "chunk_id":     i,
                        "total_chunks": len(doc_chunks),
                        "text":         ch,
                    })
            st.session_state.uploaded_chunks = new_chunks
            st.success(f"✅ {len(uploaded_files)} file(s) → {len(new_chunks)} chunks loaded")

        st.markdown("---")
        st.markdown("## ⚙️ System Status")
        st.caption(f"API Key:   {'✅' if API_KEY    else '❌ Missing'}")
        st.caption(f"Email:     {'✅' if SMTP_EMAIL else '❌ Missing'}")
        st.caption(f"Repo docs: {len(repo_chunks)} chunks from {len(set(c['source'] for c in repo_chunks))} files")
    else:
        pass  # No document count shown to regular users

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
    if not all_chunks:
        st.info("📂 No documents loaded yet. Please contact the admin.")
    else:
        total_files = len(set(c["source"] for c in all_chunks))
        st.caption(f"🔍 Smart search across {total_files} document(s) — {len(all_chunks)} indexed chunks")

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
                if msg["role"] == "assistant" and is_not_found_answer(msg["content"]):
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
                        st.info("👉 Click the **'📋 New Request / Inquiry'** tab above — it's been pre-filled.")

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
                    with st.spinner("Searching documents..."):
                        try:
                            answer = call_claude(st.session_state.messages, all_chunks)
                            st.write(answer)
                            st.session_state.messages.append({"role": "assistant", "content": answer})
                            st.session_state.last_error = None

                            # Show detected category info
                            detected = detect_category(question_to_process)
                            if detected:
                                st.markdown(
                                    f'<div class="chunk-info">🔍 Auto-detected category: <strong>{detected.upper()}</strong> — searched most relevant excerpts</div>',
                                    unsafe_allow_html=True
                                )

                            if is_not_found_answer(answer):
                                if st.button("📋 Submit Request to Gov Team", key="submit_gov_new"):
                                    st.session_state.prefill_inquiry = question_to_process
                                    if SMTP_EMAIL and SMTP_PASSWORD:
                                        send_qa_report_for_unanswered(
                                            st.session_state.user_email,
                                            st.session_state.user_name,
                                            question_to_process
                                        )
                                    st.info("👉 Click the **'📋 New Request / Inquiry'** tab above — it's been pre-filled.")
                        except Exception as e:
                            err_msg = str(e)
                            st.session_state.last_error = err_msg
                            st.markdown(
                                f'<div class="error-card"><strong>⚠️ Something went wrong</strong><br>'
                                f'<small style="color:#666;">{err_msg}</small></div>',
                                unsafe_allow_html=True
                            )

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
            req_email = st.text_input("Your Email *",     value=st.session_state.user_email)
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
                increment_inquiry_count()
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
            total_files  = len(set(c["source"] for c in repo_chunks))
            total_chunks = len(repo_chunks)
            st.metric("Documents Indexed", f"{total_files} files")
            st.metric("Total Chunks",      f"{total_chunks} chunks")
            st.metric("API Key",    "✅ Active" if API_KEY    else "❌ Missing")
            st.metric("Email Config","✅ Active" if SMTP_EMAIL else "❌ Missing")

            # Breakdown by subfolder
            if repo_chunks:
                st.markdown("**Documents by folder:**")
                subfolder_counts = {}
                for c in repo_chunks:
                    sf = c["subfolder"] or "root"
                    subfolder_counts[sf] = subfolder_counts.get(sf, set())
                    subfolder_counts[sf].add(c["source"])
                for sf, files in sorted(subfolder_counts.items()):
                    st.caption(f"📁 `{sf}`: {len(files)} file(s)")

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
            st.markdown("### 📁 Document Folder Structure")
            st.info("""
**Recommended folder structure on GitHub:**

```
documents/
├── policies/
│   ├── hr/         ← HR policies
│   ├── doa/        ← Delegation of Authority
│   ├── sales/      ← Sales & discounts
│   ├── finance/    ← Finance policies
│   ├── it/         ← IT & tools
│   └── general/    ← General policies
└── sops/
    ├── customer_experience/
    ├── operations/
    ├── sales/
    ├── finance/
    └── it/
```

**How to add documents:**
1. Go to your GitHub repo
2. Navigate to the right subfolder
3. Click "Add file" → "Upload files"
4. Upload PDF/DOCX/XLSX
5. App re-indexes automatically on next load
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
