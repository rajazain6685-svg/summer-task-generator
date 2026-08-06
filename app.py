import streamlit as st
from google import genai
from supabase import create_client
import json
from fpdf import FPDF
import tempfile
from streamlit_markmap import markmap

st.set_page_config(page_title="Summer Task Generator", page_icon="📚", layout="centered")

st.markdown("""
<style>
    .question-card {
        background-color: #F1F8F4;
        border: 1px solid #D7EAD9;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    .question-card .q-number {
        color: #2E7D32;
        font-weight: 700;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .question-card .q-text {
        font-size: 1.05rem;
        font-weight: 600;
        margin: 4px 0 8px 0;
    }
    .question-card .q-option {
        padding: 2px 0 2px 12px;
        color: #333;
    }
    .question-card .q-answer {
        margin-top: 8px;
        color: #2E7D32;
        font-style: italic;
        font-size: 0.92rem;
    }
    .app-header {
        text-align: center;
        padding: 10px 0 20px 0;
    }
    .app-header h1 {
        margin-bottom: 0;
    }
    .app-header p {
        color: #667;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


def render_question_card(i, q, show_answer=True):
    """Renders one question as a styled card. Works for st.markdown with HTML."""
    html = f'<div class="question-card">'
    html += f'<div class="q-number">Question {i}</div>'
    html += f'<div class="q-text">{q["question"]}</div>'
    if q["type"] == "mcq":
        for opt in q["options"]:
            html += f'<div class="q-option">◦ {opt}</div>'
    if show_answer:
        html += f'<div class="q-answer">Answer: {q["answer"]}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# --- Connections ---
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]
supabase = create_client(supabase_url, supabase_key)  # used for auth (signup/login/logout)

service_key = st.secrets["SUPABASE_SERVICE_KEY"]
db = create_client(supabase_url, service_key)  # used for table reads/writes (server-side only, bypasses RLS)

app_url = st.secrets.get("APP_URL", "")

# --- Auth helpers ---
def sign_up(email, password):
    return supabase.auth.sign_up({"email": email, "password": password})

def sign_in(email, password):
    return supabase.auth.sign_in_with_password({"email": email, "password": password})

def sign_out():
    supabase.auth.sign_out()
    st.session_state.clear()

def reset_password(email):
    supabase.auth.reset_password_for_email(email)


# --- Question generation ---
def generate_questions(class_level, subject, topic, question_type, count, difficulty="medium", source_text=None):
    format_instructions = {
        "mcq": '''[{"type": "mcq", "question": "...", "options": ["...", "...", "...", "..."], "answer": "..."}]''',
        "true_false": '''[{"type": "true_false", "question": "...", "answer": "True or False"}]''',
        "fill_blank": '''[{"type": "fill_blank", "question": "sentence with ____ blank", "answer": "..."}]''',
        "theory": '''[{"type": "theory", "question": "...", "answer": "model answer text"}]''',
        "math": '''[{"type": "math", "question": "...", "answer": "final answer", "solution": "step by step solution"}]''',
        "mind_map": '''[{"type": "mind_map", "title": "Central Topic", "children": [{"title": "Main Branch 1", "children": [{"title": "Sub-point", "children": []}]}, {"title": "Main Branch 2", "children": []}]}]'''
    }

    if source_text:
        # Trim very long notes to keep prompt size reasonable
        trimmed = source_text[:15000]
        source_instruction = f"""
Base the questions STRICTLY on the following notes/chapter content provided by the teacher.
Do not use outside knowledge beyond what's in this text.

--- NOTES START ---
{trimmed}
--- NOTES END ---
"""
    else:
        source_instruction = f'Base the questions on general knowledge of the topic "{topic}".'

    if question_type == "mind_map":
        count_instruction = f"with about {count} main branches, each with 2-4 sub-points"
    else:
        count_instruction = f"{count} separate questions"

    prompt = f"""
You are a question generator for a school summer task app.

Generate a {question_type} for Class {class_level} {subject}, at {difficulty} difficulty, {count_instruction}.

{source_instruction}

Return ONLY valid JSON, no extra text, no markdown code fences, in this exact format:

{format_instructions[question_type]}
"""
    response = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
    text = response.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    return json.loads(text)


def extract_text_from_file(uploaded_file):
    """Extracts text from an uploaded PDF, DOCX, or TXT file."""
    name = uploaded_file.name.lower()

    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    elif name.endswith(".docx"):
        from docx import Document
        doc = Document(uploaded_file)
        return "\n".join(p.text for p in doc.paragraphs)

    elif name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8")

    else:
        return ""


def mindmap_to_markdown(node, level=1):
    """Converts a mind map node (title + children) into markdown outline for markmap."""
    md = ("#" * level) + " " + node["title"] + "\n" if level == 1 else ("  " * (level - 1)) + "- " + node["title"] + "\n"
    for child in node.get("children", []):
        md += mindmap_to_markdown(child, level + 1)
    return md

def mindmap_to_pdf_lines(node, level=0):
    """Converts a mind map node into indented text lines for the PDF."""
    lines = [("    " * level) + ("- " if level > 0 else "") + node["title"]]
    for child in node.get("children", []):
        lines += mindmap_to_pdf_lines(child, level + 1)
    return lines


# --- PDF generation ---
def clean_text(text):
    return text.encode("latin-1", "replace").decode("latin-1")

class StyledPDF(FPDF):
    def __init__(self, school_name, logo_path, class_level, subject, topic, include_answers):
        super().__init__()
        self.school_name = school_name
        self.logo_path = logo_path
        self.class_level = class_level
        self.subject = subject
        self.topic = topic
        self.include_answers = include_answers

    def header(self):
        # Green banner across the top of every page
        self.set_fill_color(46, 125, 50)
        self.rect(0, 0, 210, 28, style="F")

        if self.logo_path:
            self.image(self.logo_path, x=8, y=5, w=18)
            text_x = 30
        else:
            text_x = 10

        self.set_xy(text_x, 6)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 8, clean_text(self.school_name), new_x="LMARGIN", new_y="NEXT")

        self.set_x(text_x)
        self.set_font("Helvetica", "", 10)
        label = "Summer Vacation Task" + (" - Answer Key" if self.include_answers else "")
        self.cell(0, 6, label, new_x="LMARGIN", new_y="NEXT")

        self.set_text_color(0, 0, 0)
        self.set_y(32)
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(241, 248, 244)
        self.cell(0, 8, clean_text(f"Class: {self.class_level}   |   Subject: {self.subject}   |   Topic: {self.topic}"),
                  fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def create_pdf(school_name, logo_path, class_level, subject, topic, questions, include_answers):
    pdf = StyledPDF(school_name, logo_path, class_level, subject, topic, include_answers)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 11)
    for i, q in enumerate(questions, 1):
        if q["type"] == "mind_map":
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(46, 125, 50)
            pdf.multi_cell(0, 7, clean_text("Mind Map: " + q["title"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 11)
            for line in mindmap_to_pdf_lines(q)[1:]:
                pdf.multi_cell(0, 6, clean_text(line), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            continue

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(46, 125, 50)
        pdf.cell(0, 6, clean_text(f"Q{i}"), new_x="LMARGIN", new_y="NEXT")

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 7, clean_text(q["question"]), new_x="LMARGIN", new_y="NEXT")

        if q["type"] == "mcq":
            for opt in q["options"]:
                pdf.multi_cell(0, 6, clean_text(f"     -  {opt}"), new_x="LMARGIN", new_y="NEXT")

        if include_answers:
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(46, 125, 50)
            pdf.multi_cell(0, 6, clean_text(f"Answer: {q['answer']}"), new_x="LMARGIN", new_y="NEXT")
            if "solution" in q:
                pdf.set_text_color(90, 90, 90)
                pdf.multi_cell(0, 6, clean_text(f"Solution: {q['solution']}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 11)

        pdf.ln(3)
        pdf.set_draw_color(220, 230, 222)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)

    pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    pdf.output(pdf_path)
    return pdf_path


# --- Public shareable view (no login required) ---
query_task_id = st.query_params.get("task")
if query_task_id:
    task_result = db.table("tasks").select("*").eq("id", query_task_id).execute().data
    if not task_result:
        st.error("This task link is invalid or the task was deleted.")
        st.stop()

    t = task_result[0]
    school_result = db.table("school_profile").select("*").eq("id", t["school_id"]).execute().data
    school_name_public = school_result[0]["school_name"] if school_result else "School"

    st.title(school_name_public)
    st.caption(f"Summer Vacation Task — Class {t['class_level']}, {t['subject']}, {t['topic']}")

    questions = t["questions_json"]
    for i, q in enumerate(questions, 1):
        if q["type"] == "mind_map":
            st.write(f"**Mind Map: {q['title']}**")
            markmap(mindmap_to_markdown(q), height=400)
        else:
            render_question_card(i, q, show_answer=False)

    if st.button("Download PDF"):
        path = create_pdf(school_name_public, None, t['class_level'], t['subject'], t['topic'], questions, include_answers=False)
        with open(path, "rb") as f:
            st.download_button("Click to save PDF", f, file_name="student_task.pdf", mime="application/pdf")

    st.stop()  # public visitors stop here — never see the teacher login screen


# --- Session state ---
if "user" not in st.session_state:
    st.session_state["user"] = None


# --- AUTH SCREEN ---
if not st.session_state["user"]:
    st.title("Summer Task Generator — Teacher Login")
    tab1, tab2, tab3 = st.tabs(["Log In", "Sign Up", "Forgot Password"])

    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Log In"):
            try:
                result = sign_in(email, password)
                st.session_state["user"] = result.user
                st.session_state["access_token"] = result.session.access_token
                st.session_state["refresh_token"] = result.session.refresh_token
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab2:
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Sign Up"):
            try:
                sign_up(new_email, new_password)
                st.success("Account created! Check your email to confirm, then log in.")
            except Exception as e:
                st.error(f"Sign up failed: {e}")

    with tab3:
        reset_email = st.text_input("Email", key="reset_email")
        if st.button("Send Reset Link"):
            try:
                reset_password(reset_email)
                st.success("Password reset email sent.")
            except Exception as e:
                st.error(f"Reset failed: {e}")

    st.stop()


# --- LOGGED IN ---
# Re-attach the saved login session to this fresh connection so
# Supabase's Row Level Security recognizes us as authenticated.
user = st.session_state["user"]
st.sidebar.write(f"Logged in as: {user.email}")
if st.sidebar.button("Log Out"):
    sign_out()
    st.rerun()

# Get or create teacher's school profile
teacher_row = db.table("teachers").select("*").eq("id", user.id).execute()

if not teacher_row.data:
    st.title("Set Up Your School (one-time)")
    school_name_input = st.text_input("School Name")
    if st.button("Save School"):
        school_result = db.table("school_profile").insert({"school_name": school_name_input}).execute()
        school_id = school_result.data[0]["id"]
        db.table("teachers").insert({
            "id": user.id, "school_id": school_id, "full_name": user.email, "role": "admin"
        }).execute()
        st.rerun()
    st.stop()

school_id = teacher_row.data[0]["school_id"]
school = db.table("school_profile").select("*").eq("id", school_id).execute().data[0]
school_name = school["school_name"]

st.markdown(f"""
<div class="app-header">
    <h1>📚 Summer Task Generator</h1>
    <p>{school_name}</p>
</div>
""", unsafe_allow_html=True)

tab_create, tab_history = st.tabs(["Create New Task", "Task History"])

with tab_create:
    logo_file = st.file_uploader("School Logo (optional, per PDF)", type=["png", "jpg", "jpeg"])
    logo_path = None
    if logo_file:
        logo_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        with open(logo_path, "wb") as f:
            f.write(logo_file.getvalue())

    st.subheader("Task Details")
    class_level = st.text_input("Class", "7")
    subject = st.text_input("Subject", "Science")

    source_choice = st.radio("Question source", ["Type a topic", "Upload notes/chapter file"])

    topic = ""
    source_text = None

    if source_choice == "Type a topic":
        topic = st.text_input("Topic", "Photosynthesis")
    else:
        notes_file = st.file_uploader("Upload notes/chapter (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
        if notes_file:
            with st.spinner("Reading file..."):
                source_text = extract_text_from_file(notes_file)
            if source_text:
                st.success(f"Extracted {len(source_text)} characters from the file.")
                topic = notes_file.name
            else:
                st.error("Couldn't extract text from this file. Try a different file.")

    question_type = st.selectbox("Question Type", ["mcq", "true_false", "fill_blank", "theory", "math", "mind_map"])
    count = st.number_input("Number of Questions", min_value=1, max_value=20, value=5)
    difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"])

    if st.button("Generate Questions"):
        if source_choice == "Upload notes/chapter file" and not source_text:
            st.error("Please upload a valid file first.")
        else:
            with st.spinner("Generating..."):
                questions = generate_questions(class_level, subject, topic, question_type, count, difficulty, source_text=source_text)
            st.session_state["questions"] = questions

            # Save this task to history automatically
            db.table("tasks").insert({
                "school_id": school_id,
                "class_level": class_level,
                "subject": subject,
                "topic": topic,
                "question_type": question_type,
                "difficulty": difficulty,
                "questions_json": questions
            }).execute()

    if "questions" in st.session_state:
        st.subheader("Preview")
        for i, q in enumerate(st.session_state["questions"], 1):
            if q["type"] == "mind_map":
                st.write(f"**Mind Map: {q['title']}**")
                markmap(mindmap_to_markdown(q), height=400)
            else:
                render_question_card(i, q, show_answer=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Create Student PDF (no answers)"):
                path = create_pdf(school_name, logo_path, class_level, subject, topic, st.session_state["questions"], include_answers=False)
                with open(path, "rb") as f:
                    st.download_button("Download Student PDF", f, file_name="student_task.pdf", mime="application/pdf")
        with col2:
            if st.button("Create Teacher PDF (with answers)"):
                path = create_pdf(school_name, logo_path, class_level, subject, topic, st.session_state["questions"], include_answers=True)
                with open(path, "rb") as f:
                    st.download_button("Download Teacher PDF", f, file_name="teacher_answer_key.pdf", mime="application/pdf")

with tab_history:
    st.subheader("Past Tasks")
    past_tasks = db.table("tasks").select("*").eq("school_id", school_id).order("created_at", desc=True).execute().data

    if not past_tasks:
        st.write("No tasks created yet.")
    else:
        for t in past_tasks:
            with st.expander(f"{t['subject']} - {t['topic']} (Class {t['class_level']}, {t['question_type']}) — {t['created_at'][:10]}"):
                share_url = f"{app_url}/?task={t['id']}" if app_url else f"?task={t['id']}"
                st.text_input("Shareable link for students/parents", value=share_url, key=f"share_{t['id']}")
                if not app_url:
                    st.caption("Tip: add APP_URL in Streamlit secrets (your app's live URL) to get a full clickable link.")

                questions = t["questions_json"]
                for i, q in enumerate(questions, 1):
                    if q["type"] == "mind_map":
                        st.write(f"**Mind Map: {q['title']}**")
                        markmap(mindmap_to_markdown(q), height=400)
                    else:
                        render_question_card(i, q, show_answer=True)

                colh1, colh2 = st.columns(2)
                with colh1:
                    if st.button("Download Student PDF", key=f"student_{t['id']}"):
                        path = create_pdf(school_name, None, t['class_level'], t['subject'], t['topic'], questions, include_answers=False)
                        with open(path, "rb") as f:
                            st.download_button("Click to save", f, file_name="student_task.pdf", mime="application/pdf", key=f"dl_student_{t['id']}")
                with colh2:
                    if st.button("Download Teacher PDF", key=f"teacher_{t['id']}"):
                        path = create_pdf(school_name, None, t['class_level'], t['subject'], t['topic'], questions, include_answers=True)
                        with open(path, "rb") as f:
                            st.download_button("Click to save", f, file_name="teacher_answer_key.pdf", mime="application/pdf", key=f"dl_teacher_{t['id']}")
    
