import os
import json
import time
import random
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google import genai
from google.cloud import bigquery
from google.oauth2 import service_account

# (คงเดิม - เริ่มเชื่อมต่อ Cloud & Database)
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))

if "GCP_JSON_TEXT" in st.secrets:
    gcp_info = json.loads(st.secrets["GCP_JSON_TEXT"])
    credentials = service_account.Credentials.from_service_account_info(gcp_info)
    bq_client = bigquery.Client(credentials=credentials, project=gcp_info["project_id"])
    PROJECT_ID = gcp_info["project_id"]
else:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "frm-ai-tutor-1cef93cd880b.json"
    bq_client = bigquery.Client()
    PROJECT_ID = bq_client.project

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# (คงเดิม - ฟังก์ชันฐานข้อมูล ensure_db_tables_exist, push_stat_to_db, ฯลฯ)
# ... [ใช้ฟังก์ชันฐานข้อมูลเดิมของคุณนาธานได้เลยครับ] ...

# =========================================================
# 🧭 แผงควบคุมด้านข้าง (Sidebar) ที่แก้ไข Indentation แล้ว
# =========================================================
with st.sidebar:
    st.title("🌿 Ghibli Control")
    current_user = st.text_input("👤 ชื่อผู้ใช้งาน (User Name):", value="Nathan").strip()

if "db_loaded_for" not in st.session_state or st.session_state.db_loaded_for != current_user:
    with st.spinner(f"☁️ กำลังซิงค์แฟ้มประวัติของ {current_user} จาก BigQuery..."):
        s_stats, s_mocks, s_cards = fetch_user_data(current_user)
        st.session_state.global_stats_log = s_stats
        st.session_state.mock_scores = s_mocks
        st.session_state.my_flashcards = s_cards
        st.session_state.db_loaded_for = current_user

user_history = [d for d in st.session_state.global_stats_log if d["user"] == current_user]
total_q = len(user_history)
correct_q = sum([d["is_correct"] for d in user_history])
overall_acc = (correct_q / total_q * 100) if total_q > 0 else 0

with st.sidebar:
    # 🏅 ตราประทับเกียรติยศ (3D Animated in Gold Frame)
    if overall_acc >= 90 and total_q >= 10: 
        gif_url = "https://media1.tenor.com/m/7H-O7G8a1YcAAAAC/the-cat-returns-baron.gif"
        level_txt = "Level 5"; title = "จ้าวแห่งสวนสวรรค์"; desc = "The Baron (from The Cat Returns)"
    elif overall_acc >= 75 and total_q >= 5: 
        gif_url = "https://media1.tenor.com/m/W2hVn4E7dO0AAAAC/castle-in-the-sky-laputa.gif"
        level_txt = "Level 4"; title = "ผู้พิทักษ์ปราสาทลอยฟ้า"; desc = "Guardian of the floating Castle (Laputa)"
    elif overall_acc >= 60 and total_q >= 3: 
        gif_url = "https://media1.tenor.com/m/0iI2O01C46EAAAAC/kiki-kikis-delivery-service.gif"
        level_txt = "Level 3"; title = "นักสำรวจเวทมนตร์"; desc = "A young student of Magic"
    elif overall_acc >= 40 and total_q > 0: 
        gif_url = "https://media1.tenor.com/m/R_Z1l4F7Cg8AAAAC/laputa-robot.gif"
        level_txt = "Level 2"; title = "นักบินฝึกหัด"; desc = "Friendly Laputan robot | apprentice pilot"
    elif total_q > 0: 
        gif_url = "https://media1.tenor.com/m/qLh2P8-tYJcAAAAC/kodama-princess-mononoke.gif"
        level_txt = "Level 1"; title = "ต้นกล้าแห่งความเพียร"; desc = "A tiny Kodama from Princess Mononoke"
    else: gif_url = None

    if gif_url:
        st.markdown(f'''
            <div class="gold-frame-container">
                <div class="gold-frame">
                    <img src="{gif_url}">
                </div>
                <div class="badge-text-outside">
                    <div class="badge-level">{level_txt}</div>
                    <div class="badge-title">{title}</div>
                    <div>{desc}</div>
                </div>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown("---")
    app_mode = st.radio("เลือกพื้นที่ทำงาน (Menu):", ["📝 Practice Mode", "⏱️ Mock Exam Simulator", "📊 Performance & AI Insights", "🗂️ Flashcard Studio"])

    st.markdown("---")
    # 🛠️ [FIXED] แก้ไขโครงสร้าง Indentation ของ Form
    st.header("✨ สร้าง Flashcard ด่วน")
    with st.form("quick_add_form", clear_on_submit=True):
        sb_front = st.text_input("ด้านหน้า (คำศัพท์/สูตร):")
        sb_back = st.text_area("ด้านหลัง (คำแปล/คำอธิบาย):", height=68)
        submitted = st.form_submit_button("💾 เซฟลงคลัง (Save)")
        
        if submitted:
            if sb_front.strip() and sb_back.strip():
                new_card = {"user": current_user, "front": sb_front.strip(), "back": sb_back.strip()}
                st.session_state.my_flashcards.append(new_card)
                push_flashcard_to_db(new_card)
                st.toast("บันทึกการ์ดลงฐานข้อมูลเรียบร้อยจ้า! 🌰")
            else:
                st.error("กรุณากรอกให้ครบทั้งหน้าและหลังจ้า")