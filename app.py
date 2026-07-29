import streamlit as st
from google import genai
import json
from fpdf import FPDF
import tempfile

api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

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

def clean_text(text):
    # Remove characters the PDF font can't render
    return text.encode("latin-1", "replace").decode("latin-1")

def create_pdf(school_name, logo_path, class_level, subject, topic, questions):
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
    pdf.cell(0, 8, "Summer Vacation Task", new_x="LMARGIN", new_y="NEXT")
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
        pdf.ln(2)

    pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    pdf.output(pdf_path)
    return pdf_path


# --- UI ---
st.title("Summer Task Generator")

st.subheader("School Details")
school_name = st.text_input("School Name", "My School")
logo_file = st.file_uploader("School Logo (optional)", type=["png", "jpg", "jpeg"])

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

    if st.button("Create PDF"):
        pdf_path = create_pdf(school_name, logo_path, class_level, subject, topic, st.session_state["questions"])
        with open(pdf_path, "rb") as f:
            st.download_button("Download PDF", f, file_name="summer_task.pdf", mime="application/pdf")
