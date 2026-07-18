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

# =========================================================
# 🔒 1. ระบบเชื่อมต่อ Cloud & Database (ยิงตรงผ่าน Memory)
# =========================================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))

if "GCP_JSON_TEXT" in st.secrets:
    gcp_info = json.loads(st.secrets["GCP_JSON_TEXT"])
    credentials = service_account.Credentials.from_service_account_info(gcp_info)
    bq_client = bigquery.Client(credentials=credentials, project=gcp_info["project_id"])
else:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "frm-ai-tutor-1cef93cd880b.json"
    bq_client = bigquery.Client()

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# =========================================================
# 🗄️ 2. ระบบ Auto-Sync ฐานข้อมูล (สร้างตาราง & ดึง/ส่ง/ลบข้อมูล)
# =========================================================
@st.cache_resource(show_spinner=False)
def ensure_db_tables_exist():
    dataset_ref = bq_client.dataset("FRM_DATASET", project="frm-ai-tutor")
    schema_stats = [
        bigquery.SchemaField("user_name", "STRING"), bigquery.SchemaField("book", "STRING"),
        bigquery.SchemaField("topic", "STRING"), bigquery.SchemaField("is_correct", "INTEGER"),
        bigquery.SchemaField("recorded_id", "STRING"), bigquery.SchemaField("timestamp", "FLOAT"),
    ]
    bq_client.create_table(bigquery.Table(dataset_ref.table("user_stats"), schema=schema_stats), exists_ok=True)
    schema_fc = [
        bigquery.SchemaField("user_name", "STRING"), bigquery.SchemaField("front", "STRING"), bigquery.SchemaField("back", "STRING"),
    ]
    bq_client.create_table(bigquery.Table(dataset_ref.table("flashcards"), schema=schema_fc), exists_ok=True)
    schema_mock = [
        bigquery.SchemaField("user_name", "STRING"), bigquery.SchemaField("score", "FLOAT"), bigquery.SchemaField("timestamp", "FLOAT"),
    ]
    bq_client.create_table(bigquery.Table(dataset_ref.table("mock_scores"), schema=schema_mock), exists_ok=True)

try: ensure_db_tables_exist()
except: pass

def push_stat_to_db(stat):
    try: bq_client.insert_rows_json("frm-ai-tutor.FRM_DATASET.user_stats", [{"user_name": stat["user"], "book": stat["book"], "topic": stat["topic"], "is_correct": stat["is_correct"], "recorded_id": stat["recorded_id"], "timestamp": stat["timestamp"]}])
    except: pass

def push_mock_to_db(mock_log):
    try: bq_client.insert_rows_json("frm-ai-tutor.FRM_DATASET.mock_scores", [{"user_name": mock_log["user"], "score": mock_log["score"], "timestamp": mock_log["timestamp"]}])
    except: pass

def push_flashcard_to_db(fc):
    try: bq_client.insert_rows_json("frm-ai-tutor.FRM_DATASET.flashcards", [{"user_name": fc["user"], "front": fc["front"], "back": fc["back"]}])
    except: pass

def delete_flashcard_from_db(fc):
    try:
        query = """
            DELETE FROM `frm-ai-tutor.FRM_DATASET.flashcards`
            WHERE user_name = @user_name AND front = @front AND back = @back
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("user_name", "STRING", fc.get("user")),
                bigquery.ScalarQueryParameter("front", "STRING", fc.get("front")),
                bigquery.ScalarQueryParameter("back", "STRING", fc.get("back")),
            ]
        )
        bq_client.query(query, job_config=job_config).result()
    except: pass

def fetch_user_data(username):
    stats, mocks, cards = [], [], []
    try:
        s_rows = bq_client.query(f"SELECT * FROM `frm-ai-tutor.FRM_DATASET.user_stats` WHERE user_name = '{username}'").result()
        stats = [{"user": r.user_name, "book": r.book, "topic": r.topic, "is_correct": r.is_correct, "recorded_id": r.recorded_id, "timestamp": r.timestamp} for r in s_rows]
        m_rows = bq_client.query(f"SELECT * FROM `frm-ai-tutor.FRM_DATASET.mock_scores` WHERE user_name = '{username}'").result()
        mocks = [{"user": r.user_name, "score": r.score, "timestamp": r.timestamp} for r in m_rows]
        c_rows = bq_client.query(f"SELECT * FROM `frm-ai-tutor.FRM_DATASET.flashcards` WHERE user_name = '{username}'").result()
        cards = [{"user": r.user_name, "front": r.front, "back": r.back} for r in c_rows]
    except: pass
    return stats, mocks, cards

# =========================================================
# 🎨 3. ตั้งค่าธีมโฮมสเตย์กิบลิอบอุ่น (CSS)
# =========================================================
st.set_page_config(page_title="FRM Ghibli Central", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600&display=swap');
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .stApp { background-color: #FFFDF9 !important; color: #4A3E3D !important; font-family: 'Sarabun', sans-serif; }
    .stButton>button { background-color: #8F9E8B !important; color: white !important; border-radius: 12px !important; border: none !important; padding: 8px 20px !important; transition: all 0.3s; }
    .stButton>button:hover { background-color: #72826E !important; transform: translateY(-2px); }
    .btn-delete>button { background-color: #C87A7A !important; font-size: 0.85rem !important; padding: 4px 10px !important; margin-top: 5px; }
    .btn-delete>button:hover { background-color: #B56565 !important; }
    .tool-card { background-color: #F4EFEA !important; padding: 18px; border-radius: 14px; border-left: 6px solid #8F9E8B; margin-bottom: 20px; }
    .exam-timer { font-size: 1.6rem; font-weight: 600; color: #C87A7A; background-color: #FCEAEA; padding: 12px; border-radius: 10px; text-align: center; margin-bottom: 15px; }
    .fc-card { background-color: #FFFDF9; border: 2px solid #D9C5B2; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 2px 4px 8px rgba(0,0,0,0.04); height: 100%; transition: transform 0.2s; }
    .fc-card:hover { transform: scale(1.02); }
    .fc-front { color: #8F9E8B; font-weight: 600; font-size: 1.15rem; }
    .fc-divider { border-top: 1.5px dashed #D9C5B2; margin: 12px 0; }
    .fc-back { color: #4A3E3D; font-size: 0.95rem; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 📊 4. ฟังก์ชันดึงคลังข้อสอบจาก BigQuery Cloud
# =========================================================
@st.cache_data(show_spinner=False)
def load_global_questions():
    try:
        rows = bq_client.query("SELECT * FROM `frm-ai-tutor.FRM_DATASET.questions`").result()
        pool = []
        for row in rows:
            pool.append({
                "question_id": row.question_id, "book": row.book, "topic": row.topic, "difficulty": row.difficulty,
                "question_text": row.question_text, "correct_option": row.correct_option,
                "explanation_en": row.explanation_en, "explanation_th": row.explanation_th,
                "options": json.loads(row.options) if isinstance(row.options, str) else row.options,
                "key_vocabulary": json.loads(row.key_vocabulary) if isinstance(row.key_vocabulary, str) else row.key_vocabulary
            })
        return pool
    except: return []

global_pool = load_global_questions()

# =========================================================
# ⚙️ 5. บริหารกลไกตัวแปรระบบหลัก (Session State)
# =========================================================
if "practice_idx" not in st.session_state: st.session_state.practice_idx = 0
if "practice_submitted" not in st.session_state: st.session_state.practice_submitted = False
if "practice_chat" not in st.session_state: st.session_state.practice_chat = []
if "mock_questions" not in st.session_state: st.session_state.mock_questions = []
if "mock_user_answers" not in st.session_state: st.session_state.mock_user_answers = {}
if "mock_start_time" not in st.session_state: st.session_state.mock_start_time = None
if "mock_duration_minutes" not in st.session_state: st.session_state.mock_duration_minutes = 60
if "mock_completed" not in st.session_state: st.session_state.mock_completed = False

# =========================================================
# 🧭 6. แผงควบคุมด้านข้าง Ghibli Control (อัปเกรดเป็น Gamification)
# =========================================================
with st.sidebar:
    st.title("🌿 Ghibli Control")
    current_user = st.text_input("👤 ชื่อผู้ใช้งาน (User Name):", value="Nathan").strip()

# 🚀 โหลดข้อมูลจากฐานข้อมูล
if "db_loaded_for" not in st.session_state or st.session_state.db_loaded_for != current_user:
    with st.spinner(f"☁️ กำลังซิงค์แฟ้มประวัติของ {current_user} จาก BigQuery..."):
        s_stats, s_mocks, s_cards = fetch_user_data(current_user)
        st.session_state.global_stats_log = s_stats
        st.session_state.mock_scores = s_mocks
        st.session_state.my_flashcards = s_cards
        st.session_state.db_loaded_for = current_user

# 🧮 คำนวณคะแนนสำหรับแจกเหรียญรางวัล
user_history = [d for d in st.session_state.global_stats_log if d["user"] == current_user]
total_q = len(user_history)
correct_q = sum([d["is_correct"] for d in user_history])
overall_acc = (correct_q / total_q * 100) if total_q > 0 else 0

with st.sidebar:
    # 🏅 โซนตราประทับเกียรติยศ (ย้ายขึ้นมารวมกับ Ghibli Control ไร้ตัวเลข %)
    st.markdown("---")
    st.subheader("🏅 ตราประทับเกียรติยศ")
    if overall_acc >= 70 and total_q >= 20: 
        st.markdown("🦦 **ราชาคาปิบาร่าออนเซ็น**\n(ระดับปรมาจารย์! พร้อมลุยสนามจริง)")
    elif overall_acc >= 50 and total_q >= 10: 
        st.markdown("🔥 **เปลวไฟ Calcifer**\n(ระดับกลาง! ลุยทบทวนจุดอ่อนอีกนิด)")
    elif total_q > 0: 
        st.markdown("🌰 **เมล็ดโอ๊ค Totoro**\n(นักวิเคราะห์ฝึกหัด! เก็บเกี่ยวประสบการณ์ต่อไปนะ)")
    else: 
        st.caption("ยังไม่มีตราประทับ เริ่มทำโจทย์เพื่อปลดล็อกจ้า...")

    st.markdown("---")
    app_mode = st.radio("เลือกพื้นที่ทำงาน (Menu):", ["📝 Practice Mode", "⏱️ Mock Exam Simulator", "📊 Performance & AI Insights", "🗂️ Flashcard Studio"])

    st.markdown("---")
    # 🛠️ กล่องสร้าง Flashcard ด่วนใน Sidebar
    st.header("✨ สร้าง Flashcard ด่วน")
    if "sb_front" not in st.session_state: st.session_state.sb_front = ""
    if "sb_back" not in st.session_state: st.session_state.sb_back = ""
    
    sb_front = st.text_input("ด้านหน้า (คำศัพท์/สูตร):", key="sb_front")
    sb_back = st.text_area("ด้านหลัง (คำแปล/คำอธิบาย):", height=68, key="sb_back")
    
    if st.button("💾 เซฟลงคลัง (Save)", use_container_width=True):
        if sb_front.strip() and sb_back.strip():
            new_card = {"user": current_user, "front": sb_front.strip(), "back": sb_back.strip()}
            st.session_state.my_flashcards.append(new_card)
            push_flashcard_to_db(new_card)
            st.toast("บันทึกการ์ดลงฐานข้อมูลเรียบร้อยจ้า! 🌰")
            st.session_state.sb_front = ""
            st.session_state.sb_back = ""
            st.rerun()
        else:
            st.error("กรุณากรอกให้ครบทั้งหน้าและหลังจ้า")

if not global_pool:
    st.warning("⚠️ ไม่พบข้อมูลโจทย์ในคลังข้อสอบคลาวด์ BigQuery กรุณาตรวจสอบการรันไฟล์ pipeline.py จ้า!")
else:
    # =========================================================
    # 🗂️ หน้าที่ 1: Practice Mode 
    # =========================================================
    if app_mode == "📝 Practice Mode":
        st.header(f"📝 Practice Mode (ผู้ใช้งานปัจจุบัน: {current_user})")
        
        books_available = sorted(list(set([q['book'] for q in global_pool])))
        selected_book = st.selectbox("1. เลือกเล่มหลักสูตร FRM Book:", ["Show All"] + books_available)
        
        topics_available = sorted(list(set([q['topic'] for q in global_pool if q['book'] == selected_book]))) if selected_book != "Show All" else sorted(list(set([q['topic'] for q in global_pool])))
        selected_topic = st.selectbox("2. เลือกหัวข้อเฉพาะทาง Topic:", ["Show All"] + topics_available)
        
        filtered_pool = [q for q in global_pool if (selected_book == "Show All" or q['book'] == selected_book) and (selected_topic == "Show All" or q['topic'] == selected_topic)]
            
        if not filtered_pool: st.info("🍃 หัวข้อที่คุณเลือกยังไม่มีข้อสอบบรรจุอยู่ ลองเลือกหัวข้ออื่นดูนะจ้า")
        else:
            if st.session_state.practice_idx >= len(filtered_pool): st.session_state.practice_idx = 0
            q = filtered_pool[st.session_state.practice_idx]
            
            st.markdown(f"**📌 Question {st.session_state.practice_idx + 1} / {len(filtered_pool)}**")
            st.info(f"Book: {q['book']} | Topic: {q['topic']} | Difficulty: {q['difficulty']}")
            st.write(q['question_text'])
            
            opts = [f"A: {q['options'].get('A','')}", f"B: {q['options'].get('B','')}", f"C: {q['options'].get('C','')}", f"D: {q['options'].get('D','')}"]
            u_ans = st.radio("เลือกคำตอบที่แม่นยำที่สุดตามหลักบริหารความเสี่ยง:", opts, index=0, key=f"prac_{q['question_id']}")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🚀 ส่งคำตอบตรวจทาน (Submit)", use_container_width=True): st.session_state.practice_submitted = True
            with c2:
                if st.button("⏭️ สลับข้อถัดไป (Next Random)", use_container_width=True):
                    st.session_state.practice_idx = random.randint(0, len(filtered_pool) - 1)
                    st.session_state.practice_submitted = False
                    st.session_state.practice_chat = []
                    st.rerun()
                    
            if st.session_state.practice_submitted:
                st.markdown("---")
                final_choice = u_ans[0]
                is_correct = 1 if final_choice == q['correct_option'] else 0
                
                if is_correct: st.success(f"✨ ยอดเยี่ยมมากครับเฉลยถูกต้องคือข้อ {q['correct_option']}!")
                else: st.error(f"ผิดพลาดเล็กน้อยจ้า เฉลยที่แท้จริงคือข้อ {q['correct_option']}")
                
                if not any(d.get('recorded_id') == q['question_id'] and d["user"] == current_user for d in st.session_state.global_stats_log):
                    new_stat = {"user": current_user, "book": q['book'], "topic": q['topic'], "is_correct": is_correct, "recorded_id": q['question_id'], "timestamp": time.time()}
                    st.session_state.global_stats_log.append(new_stat)
                    push_stat_to_db(new_stat)
                        
                st.markdown(f"**📖 Detailed Explanation (EN):**\n{q['explanation_en']}")
                st.markdown(f"**🇹🇭 คำอธิบายและเฉลยละเอียดภาษาไทย:**\n{q['explanation_th']}")
                
            st.markdown("---")
            st.subheader("🛠️ เครื่องมือช่วยคิดและวิเคราะห์ประจำข้อสอบ")
            
            st.markdown('<div class="tool-card"><div class="tool-title">📚 ศัพท์เฉพาะประจำข้อ (Key Vocabulary)</div></div>', unsafe_allow_html=True)
            if q['key_vocabulary']:
                for item in q['key_vocabulary']: st.markdown(f"🔹 **{item.get('word','')}** : {item.get('translation','')}")
            else: st.caption("ข้อนี้ไม่มีศัพท์เทคนิคยากเพิ่มเติมจ้า")
                    
            st.markdown('<div class="tool-card"><div class="tool-title">🧙‍♂️ ช่องแชทติวเตอร์เวทมนตร์ (AI Tutor)</div></div>', unsafe_allow_html=True)
            for m in st.session_state.practice_chat:
                with st.chat_message(m["role"]): st.write(m["text"])
            c_input = st.chat_input("💬 สอบถามข้อสงสัยเกี่ยวกับสูตรคำนวณหรือตรรกะข้อนี้...")
            if c_input:
                st.session_state.practice_chat.append({"role": "user", "text": c_input})
                with st.spinner("AI กำลังเรียบเรียงคำตอบ..."):
                    try:
                        res = ai_client.models.generate_content(model='gemini-3.1-flash-lite', contents=f"You are a warm FRM tutor. Question: {q['question_text']}. User asks: {c_input}. Answer warmly and concisely using 'ครับจ้า'")
                        st.session_state.practice_chat.append({"role": "model", "text": res.text})
                    except: st.session_state.practice_chat.append({"role": "model", "text": "ขออภัยจ้า ระบบ AI ขัดข้องชั่วคราว"})
                st.rerun()

    # =========================================================
    # ⏱️ หน้าที่ 2: Mock Exam Simulator
    # =========================================================
    elif app_mode == "⏱️ Mock Exam Simulator":
        st.header(f"⏱️ Mock Exam Simulator (ผู้ใช้งานปัจจุบัน: {current_user})")
        
        if not st.session_state.mock_questions and not st.session_state.mock_completed:
            st.subheader("🎲 การตั้งค่าจัดชุดข้อสอบจำลองสนามจริง")
            exam_size = st.slider("เลือกจำนวนข้อสอบจำลอง (Select Questions Target):", 1, 100, 20)
            duration = st.slider("เลือกเวลาทำข้อสอบ (Select Time Limit ในหน่วยนาที):", 5, 240, 60, 5)
            st.caption(f"💡 โควตาเวลาสอบสุทธิ: **{duration//60} ชั่วโมง {duration%60} นาที**")
            
            if st.button("🎬 เริ่มทำข้อสอบจำลอง (Start Exam)"):
                pool_b1, pool_b2, pool_b3, pool_b4 = [], [], [], []
                for x in global_pool:
                    if "Foundations" in x['book']: pool_b1.append(x)
                    elif "Quantitative" in x['book']: pool_b2.append(x)
                    elif "Markets" in x['book']: pool_b3.append(x)
                    elif "Valuation" in x['book']: pool_b4.append(x)
                
                sel = []
                if pool_b1: sel.extend(random.sample(pool_b1, min(len(pool_b1), max(1, int(exam_size * 0.20)))))
                if pool_b2: sel.extend(random.sample(pool_b2, min(len(pool_b2), max(1, int(exam_size * 0.20)))))
                if pool_b3: sel.extend(random.sample(pool_b3, min(len(pool_b3), max(1, int(exam_size * 0.30)))))
                if pool_b4: sel.extend(random.sample(pool_b4, min(len(pool_b4), max(1, int(exam_size * 0.30)))))
                
                random.shuffle(sel)
                st.session_state.mock_questions = sel
                st.session_state.mock_start_time = time.time()
                st.session_state.mock_duration_minutes = duration
                st.session_state.mock_user_answers = {}
                st.session_state.mock_completed = False
                st.rerun()
                
        if st.session_state.mock_questions and not st.session_state.mock_completed:
            elapsed = time.time() - st.session_state.mock_start_time
            remaining = (st.session_state.mock_duration_minutes * 60) - elapsed
            
            if remaining <= 0:
                st.session_state.mock_completed = True
                st.warning("🚨 หมดเวลาทำข้อสอบจำลองแล้ว! ระบบกำลังนำส่งคำตอบ...")
                st.rerun()
                
            h, rem = divmod(int(remaining), 3600)
            m, s = divmod(rem, 60)
            st.markdown(f'<div class="exam-timer">⏳ Remaining Time: {h:02d}:{m:02d}:{s:02d} ชั่วโมง</div>', unsafe_allow_html=True)
            
            for idx, mq in enumerate(st.session_state.mock_questions):
                st.markdown(f"**📌 Question {idx + 1}:** ({mq['book']})")
                st.write(mq['question_text'])
                m_opts = {"A": f"A: {mq['options'].get('A','')}", "B": f"B: {mq['options'].get('B','')}", "C": f"C: {mq['options'].get('C','')}", "D": f"D: {mq['options'].get('D','')}"}
                current_saved = st.session_state.mock_user_answers.get(mq['question_id'], "A")
                saved_idx = list(m_opts.keys()).index(current_saved) if current_saved in m_opts else 0
                chosen = st.radio(f"เลือกคำตอบข้อ {idx+1}:", list(m_opts.values()), index=saved_idx, key=f"mock_key_{mq['question_id']}")
                st.session_state.mock_user_answers[mq['question_id']] = chosen[0]
                st.markdown("---")
                
            if st.button("🏁 กดส่งกระดาษคำตอบ (Submit Exam Sheet)", use_container_width=True):
                st.session_state.mock_completed = True
                st.rerun()
                
        if st.session_state.mock_completed:
            st.subheader("📊 Mock Exam Result Summary (ผลการสอบรวม)")
            correct_count, mock_logs = 0, []
            
            for mq in st.session_state.mock_questions:
                u_pick = st.session_state.mock_user_answers.get(mq['question_id'], "N/A")
                is_correct = 1 if u_pick == mq['correct_option'] else 0
                if is_correct: correct_count += 1
                
                log_id = f"M_{st.session_state.mock_start_time}_{mq['question_id']}"
                if not any(d.get('recorded_id') == log_id and d["user"] == current_user for d in st.session_state.global_stats_log):
                    new_stat = {"user": current_user, "book": mq['book'], "topic": mq['topic'], "is_correct": is_correct, "recorded_id": log_id, "timestamp": time.time()}
                    st.session_state.global_stats_log.append(new_stat)
                    push_stat_to_db(new_stat)
                
                mock_logs.append({"Curriculum Book": mq['book'], "Your Pick": u_pick, "Correct Ans": mq['correct_option'], "Status": "✅ Correct" if is_correct else "❌ Incorrect"})
            
            mock_acc = (correct_count / len(st.session_state.mock_questions)) * 100
            if not any(m.get('timestamp') == st.session_state.mock_start_time for m in st.session_state.mock_scores):
                new_mock = {"user": current_user, "score": mock_acc, "timestamp": st.session_state.mock_start_time}
                st.session_state.mock_scores.append(new_mock)
                push_mock_to_db(new_mock)
                
            st.metric("Total Score", f"{correct_count} / {len(st.session_state.mock_questions)} ข้อ", delta=f"Accuracy Rate: {int(mock_acc)}%")
            st.table(pd.DataFrame(mock_logs))
            
            if st.button("🔄 ล้างหน้าจอเพื่อเริ่มทำชุดข้อสอบใหม่ (Reset Mock)"):
                st.session_state.mock_questions, st.session_state.mock_user_answers, st.session_state.mock_completed = [], {}, False
                st.rerun()

    # =========================================================
    # 📊 หน้าที่ 3: Performance Dashboard
    # =========================================================
    elif app_mode == "📊 Performance & AI Insights":
        st.header(f"📊 Performance Dashboard (ผู้ใช้งานปัจจุบัน: {current_user})")
        if not user_history: st.info(f"🍃 ยังไม่มีข้อมูลของ {current_user} ในระบบฐานข้อมูลคลาวด์จ้า ลองฝึกทำข้อสอบก่อนน้า")
        else:
            df = pd.DataFrame(user_history).sort_values(by="timestamp").reset_index(drop=True)
            summary_df = df.groupby('book')['is_correct'].agg(['count', 'sum']).reset_index()
            summary_df.columns = ['Book', 'Total Questions', 'Correct Answers']
            summary_df['Accuracy (%)'] = (summary_df['Correct Answers'] / summary_df['Total Questions'] * 100).round(1)
            
            st.subheader("📈 Summary Table")
            st.dataframe(summary_df, use_container_width=True)
            
            col_graph1, col_graph2 = st.columns(2)
            with col_graph1:
                st.markdown("#### 🕸️ Radar Chart Analysis")
                all_4_books = ["Foundations of Risk Management", "Quantitative Analysis", "Financial Markets and Products", "Valuation and Risk Models"]
                radar_data = [{"Book": b, "Accuracy (%)": summary_df[summary_df['Book'] == b].iloc[0]['Accuracy (%)'] if not summary_df[summary_df['Book'] == b].empty else 0.0} for b in all_4_books]
                radar_df = pd.DataFrame(radar_data)
                
                r_vals = radar_df['Accuracy (%)'].tolist() + [radar_df['Accuracy (%)'].tolist()[0]]
                theta_vals = radar_df['Book'].tolist() + [radar_df['Book'].tolist()[0]]
                text_vals = [f"{v}%" for v in radar_df['Accuracy (%)'].tolist()] + [""]
                
                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=r_vals, theta=theta_vals, fill='toself', fillcolor='rgba(143, 158, 139, 0.4)',
                    line=dict(color='#8F9E8B', width=2), mode='lines+markers+text',
                    text=text_vals, textposition="top center", textfont=dict(size=13, color='#4A3E3D', weight="bold")
                ))
                fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), margin=dict(l=120, r=120, t=50, b=50), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
                st.plotly_chart(fig_radar, use_container_width=True)
                
            with col_graph2:
                st.markdown("#### 📈 Mock Exam Session Progress")
                user_mocks = [m for m in st.session_state.mock_scores if m["user"] == current_user]
                if not user_mocks: st.info("🍃 กราฟนี้จะโชว์เมื่อคุณทำโหมด Mock Exam จบ 1 ครั้งขึ้นไปจ้า")
                else:
                    df_mock = pd.DataFrame(user_mocks)
                    df_mock['Attempt'] = df_mock.index + 1
                    fig_progress = px.line(df_mock, x='Attempt', y='score', title="พัฒนาการความแม่นยำสอบจำลอง (%)", markers=True, color_discrete_sequence=['#C87A7A'])
                    fig_progress.update_layout(yaxis=dict(range=[-5, 105]), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_progress, use_container_width=True)
                
            st.markdown("---")
            st.subheader("🧙‍♂️ AI Weakness Auditor")
            if st.button("✨ เจาะลึกแผนการอ่านหนังสือ (Generate AI Insights Report)"):
                stats_text = "".join([f"- Book '{r['Book']}': Answered {r['Total Questions']}, Correct {r['Correct Answers']} (Accuracy: {r['Accuracy (%)']}%)\n" for i, r in summary_df.iterrows()])
                with st.spinner("AI กำลังวิเคราะห์จุดอ่อนให้คุณ..."):
                    try:
                        res = ai_client.models.generate_content(model='gemini-3.1-flash-lite', contents=f"USER: {current_user}. STATS:\n{stats_text}\nAnalyze weak areas. Give warm risk-practitioner advice in Thai. End with 'ครับจ้า'.")
                        st.markdown('<div class="tool-card">', unsafe_allow_html=True)
                        st.markdown(f"### 📜 รายงานวิเคราะห์สำหรับ {current_user}"); st.write(res.text)
                        st.markdown('</div>', unsafe_allow_html=True)
                    except: st.error("ระบบ AI ขัดข้องชั่วคราวจ้า")

    # =========================================================
    # 🗂️ หน้าที่ 4: Flashcard Studio 
    # =========================================================
    elif app_mode == "🗂️ Flashcard Studio":
        st.header(f"🗂️ Flashcard Studio ({current_user})")
        st.caption("พื้นที่สำหรับทบทวนและบริหารจัดการคลังความจำเฉพาะตัว ✍️")
        
        st.markdown("---")
        st.subheader("📚 แผง Flashcard ของคุณ")
        user_cards = [c for c in st.session_state.my_flashcards if isinstance(c, dict) and c.get("user") == current_user]
        
        if not user_cards: st.info("ยังไม่มีการ์ดในคลังจ้า ลองพิมพ์คำศัพท์หรือสูตรสร้างใบแรกที่แถบเครื่องมือด้านซ้ายมือดูสิ!")
        else:
            for i in range(0, len(user_cards), 3):
                cols = st.columns(3)
                for j, c in enumerate(user_cards[i:i+3]):
                    with cols[j]:
                        st.markdown(f'<div class="fc-card"><div class="fc-front">{c.get("front","")}</div><hr class="fc-divider"><div class="fc-back">{c.get("back","")}</div></div>', unsafe_allow_html=True)
                        
                        st.markdown('<div class="btn-delete">', unsafe_allow_html=True)
                        if st.button("🗑️ ลบการ์ดใบนี้", key=f"del_{i}_{j}_{c.get('front','')[:5]}"):
                            delete_flashcard_from_db(c)
                            st.session_state.my_flashcards = [card for card in st.session_state.my_flashcards if not (isinstance(card, dict) and card.get("user")==c.get("user") and card.get("front")==c.get("front") and card.get("back")==c.get("back"))]
                            st.toast("🗑️ ลบการ์ดออกจากคลังเรียบร้อยจ้า!")
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)