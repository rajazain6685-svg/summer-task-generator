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
def sign_up(email, password, full_name):
    result = supabase.auth.sign_up({"email": email, "password": password})
    return result

def sign_in(email, password):
    result = supabase.auth.sign_in_with_password({"email": email, "password": password})
    return result

def sign_out():
    supabase.auth.sign_out()
    st.session_state.clear()

def reset_password(email):
    supabase.auth.reset_password_for_email(email)


# --- Session state setup ---
if "user" not in st.session_state:
    st.session_state["user"] = None


# --- AUTH SCREEN (shown if not logged in) ---
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
        new_name = st.text_input("Full Name", key="signup_name")
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Sign Up"):
            try:
                result = sign_up(new_email, new_password, new_name)
                st.success("Account created! Check your email to confirm, then log in.")
            except Exception as e:
                st.error(f"Sign up failed: {e}")

    with tab3:
        reset_email = st.text_input("Email", key="reset_email")
        if st.button("Send Reset Link"):
            try:
                reset_password(reset_email)
                st.success("Password reset email sent (check your inbox).")
            except Exception as e:
                st.error(f"Reset failed: {e}")

    st.stop()  # stops here if not logged in — nothing below runs


# --- LOGGED IN — everything below only runs for logged-in teachers ---
st.sidebar.write(f"Logged in as: {st.session_state['user'].email}")
if st.sidebar.button("Log Out"):
    sign_out()
    st.rerun()

st.title("Summer Task Generator")
st.write("(Your existing generator + PDF code goes here — next step)")
