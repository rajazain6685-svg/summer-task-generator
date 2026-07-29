import streamlit as st
from google import genai
import json

# Load API key from Streamlit secrets
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

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()

    return json.loads(text)


# --- Streamlit UI ---
st.title("Summer Task Generator")

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
    for i, q in enumerate(st.session_state["questions"], 1):
        st.write(f"**Q{i}. {q['question']}**")
        if q["type"] == "mcq":
            for opt in q["options"]:
                st.write(f"- {opt}")
        st.write(f"*Answer: {q['answer']}*")
        if "solution" in q:
            st.write(f"Solution: {q['solution']}")
        st.write("---")
