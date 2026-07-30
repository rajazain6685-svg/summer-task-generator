import streamlit as st
from google import genai
from supabase import create_client
import json
from fpdf import FPDF
import tempfile

# --- Connections ---
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]
supabase = create_client(supabase_url, supabase_key)

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
def generate_questions(class_level, subject, topic, question_type, count, difficulty="medium"):
    format_instructions = {
        "mcq": '''[{"type": "mcq", "question": "...", "options": ["...", "...", "...", "..."], "answer": "..."}]''',
        "true_false": '''[{"type": "true_false", "question": "...", "answer": "True or False"}]''',
        "fill_blank": '''[{"type": "fill_blank", "question": "sentence with ____ blank", "answer": "..."}]''',
        "theory": '''[{"type": "theory", "question": "...", "answer": "model answer text"}]''',
        "math": '''[{"type": "math", "question": "...", "answer": "final answer", "solution": "step by step solution"}]'''
    }
    prompt = f"""
You are a question generator for a school summer task app.

Generate {count} {question_type} questions for Class {class_level} {subject}
on the topic "{topic}", at {difficulty} difficulty.

Return ONLY valid JSON, no extra text, no markdown code fences, in this exact format:

{format_instructions[question_type]}
"""
    response = client.models.generate_content(model="gemini-3.5-flash", contents=prompt)
    text = response.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    return json.loads(text)


# --- PDF generation ---
def clean_text(text):
    return text.encode("latin-1", "replace").decode("latin-1")

def create_pdf(school_name, logo_path, class_level, subject, topic, questions, include_answers):
    pdf = FPDF()
    pdf.add_page()

    if logo_path:
        pdf.image(logo_path, x=10, y=8, w=20)
        pdf.set_xy(35, 10)
    else:
        pdf.set_xy(10, 10)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, clean_text(school_name), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 12)
    label = "Summer Vacation Task" + (" - Answer Key" if include_answers else "")
    pdf.cell(0, 8, label, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, clean_text(f"Class: {class_level}    Subject: {subject}    Topic: {topic}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 11)
    for i, q in enumerate(questions, 1):
        pdf.multi_cell(0, 7, clean_text(f"Q{i}. {q['question']}"), new_x="LMARGIN", new_y="NEXT")
        if q["type"] == "mcq":
            for opt in q["options"]:
                pdf.multi_cell(0, 6, clean_text(f"    - {opt}"), new_x="LMARGIN", new_y="NEXT")
        if include_answers:
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(0, 6, clean_text(f"    Answer: {q['answer']}"), new_x="LMARGIN", new_y="NEXT")
            if "solution" in q:
                pdf.multi_cell(0, 6, clean_text(f"    Solution: {q['solution']}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
        pdf.ln(2)

    pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    pdf.output(pdf_path)
    return pdf_path


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
user = st.session_state["user"]
st.sidebar.write(f"Logged in as: {user.email}")
if st.sidebar.button("Log Out"):
    sign_out()
    st.rerun()

# Get or create teacher's school profile
teacher_row = supabase.table("teachers").select("*").eq("id", user.id).execute()

if not teacher_row.data:
    st.title("Set Up Your School (one-time)")
    school_name_input = st.text_input("School Name")
    if st.button("Save School"):
        school_result = supabase.table("school_profile").insert({"school_name": school_name_input}).execute()
        school_id = school_result.data[0]["id"]
        supabase.table("teachers").insert({
            "id": user.id, "school_id": school_id, "full_name": user.email, "role": "admin"
        }).execute()
        st.rerun()
    st.stop()

school_id = teacher_row.data[0]["school_id"]
school = supabase.table("school_profile").select("*").eq("id", school_id).execute().data[0]
school_name = school["school_name"]

st.title("Summer Task Generator")
st.caption(f"School: {school_name}")

logo_file = st.file_uploader("School Logo (optional, per PDF)", type=["png", "jpg", "jpeg"])
logo_path = None
if logo_file:
    logo_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
    with open(logo_path, "wb") as f:
        f.write(logo_file.getvalue())

st.subheader("Task Details")
class_level = st.text_input("Class", "7")
subject = st.text_input("Subject", "Science")
topic = st.text_input("Topic", "Photosynthesis")
question_type = st.selectbox("Question Type", ["mcq", "true_false", "fill_blank", "theory", "math"])
count = st.number_input("Number of Questions", min_value=1, max_value=20, value=5)
difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"])

if st.button("Generate Questions"):
    with st.spinner("Generating..."):
        questions = generate_questions(class_level, subject, topic, question_type, count, difficulty)
    st.session_state["questions"] = questions

if "questions" in st.session_state:
    st.subheader("Preview")
    for i, q in enumerate(st.session_state["questions"], 1):
        st.write(f"**Q{i}. {q['question']}**")
        if q["type"] == "mcq":
            for opt in q["options"]:
                st.write(f"- {opt}")
        st.write(f"*Answer: {q['answer']}*")
        st.write("---")

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
