import os
import json
import time
import random 
import io  
import textwrap  
import streamlit as st  
import pandas as pd  
import plotly.graph_objects as go  
from google import genai
from google.genai import types
from google.cloud import bigquery

# 🔒 1. ดึงกุญแจความลับผ่านระบบ Streamlit Secrets 
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "frm-ai-tutor-1cef93cd880b.json"

bq_client = bigquery.Client()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 🔄 โหลดข้อมูลข้อสอบจาก BigQuery
@st.cache_data
def load_frm_questions():
    query = """
        SELECT question_id, source, book, topic, difficulty, question_text, options, correct_option, explanation_en, explanation_th, key_vocabulary
        FROM `frm-ai-tutor.FRM_DATASET.questions`
    """
    query_job = bq_client.query(query)
    results = query_job.result()
    
    questions = []
    seen_ids = set()
    for row in results:
        if row.question_id in seen_ids:
            continue
        seen_ids.add(row.question_id)
        questions.append({
            "id": row.question_id,
            "source": row.get("source", "Unknown"),
            "book": row.book,
            "topic": row.topic,
            "difficulty": row.difficulty,
            "text": row.question_text,
            "options": json.loads(row.options),
            "correct": row.correct_option,
            "exp_en": row.explanation_en,
            "exp_th": row.explanation_th,
            "vocab": json.loads(row.key_vocabulary) if row.key_vocabulary else []
        })
    return questions

# 📥 ฟังก์ชันดึงประวัติจริงจาก BigQuery ถาวร
def load_user_history_from_bq(username):
    query = """
        SELECT question_id, book, topic, is_correct, mode, timestamp
        FROM `frm-ai-tutor.FRM_DATASET.user_history`
        WHERE username = @username
        ORDER BY timestamp ASC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("username", "STRING", username)]
    )
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()
        history = []
        for row in results:
            history.append({
                "q_id": row.question_id,
                "book": row.book,
                "topic": row.topic,
                "is_correct": row.is_correct,
                "mode": row.mode,
                "timestamp": row.timestamp
            })
        return history
    except Exception as e:
        return []

# 📤 บันทึกข้อมูลแบบ Load Job (NDJSON) รองรับ BigQuery Sandbox บัญชีฟรี 100%
def save_history_to_bq(rows_list):
    table_id = "frm-ai-tutor.FRM_DATASET.user_history"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND
    )
    try:
        ndjson_string = ""
        for row in rows_list:
            ndjson_string += json.dumps(row, ensure_ascii=False) + "\n"
        data_stream = io.BytesIO(ndjson_string.encode('utf-8'))
        load_job = bq_client.load_table_from_file(data_stream, table_id, job_config=job_config)
        load_job.result() 
        return True
    except Exception as e:
        st.error(f"❌ เซฟประวัติลงคลาวด์ไม่สำเร็จ: {e}")
        return False

# 📥 ฟังก์ชันดึงข้อมูล Flashcard จาก BigQuery คลาวด์
def load_flashcards_from_bq(username):
    query = """
        SELECT front, back, timestamp
        FROM `frm-ai-tutor.FRM_DATASET.flashcards`
        WHERE username = @username
        ORDER BY timestamp DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("username", "STRING", username)]
    )
    try:
        query_job = bq_client.query(query, job_config=job_config)
        return [{"front": row.front, "back": row.back} for row in query_job.result()]
    except Exception as e:
        return []

# 📤 ฟังก์ชันบันทึก Flashcard ใหม่ลง BigQuery คลาวด์
def save_flashcard_to_bq(username, front, back):
    table_id = "frm-ai-tutor.FRM_DATASET.flashcards"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND
    )
    row_data = {
        "username": username,
        "front": front,
        "back": back,
        "timestamp": float(time.time())
    }
    try:
        ndjson_string = json.dumps(row_data, ensure_ascii=False) + "\n"
        data_stream = io.BytesIO(ndjson_string.encode('utf-8'))
        load_job = bq_client.load_table_from_file(data_stream, table_id, job_config=job_config)
        load_job.result()
        return True
    except Exception as e:
        st.error(f"❌ บันทึก Flashcard ลงคลาวด์ล้มเหลว: {e}")
        return False

# 🎖️ ฟังก์ชันแจกของรางวัล Badge สไตล์กิบลิ 3D
def get_ghibli_badge(score_percent):
    if score_percent >= 85:
        return "🎖️ ตราเกียรติยศผู้พิทักษ์ความเสี่ยงขั้นสูงสุด (Grand Risk Archmage)", "สไตล์พ่อมดฮาวล์ผู้ควบคุมเวทมนตร์การเงินและปิดประตูความเสี่ยงได้ดั่งใจนึก! ✨☁️"
    elif score_percent >= 70:
        return "🛡️ เหรียญอัศวินแห่งป่ากิบลิ (Ghibli Forest Knight)", "ผ่านเกณฑ์มาตรฐานความเสี่ยงสากลอย่างงดงาม พร้อมปกป้องพอร์ตการลงทุนอย่างปลอดภัย 🌳🍃"
    elif score_percent >= 50:
        return "🌱 หน่อไม้ผู้กล้าเพิ่งเริ่มงอก (Sprouting Risk Hero)", "นักเดินทางผู้กำลังสะสมชั่วโมงบิน อีกนิดเดียวต้นกล้าจะเติบโตเป็นต้นไม้ใหญ่ที่แข็งแกร่งแล้วจ้า! 🍄🐾"
    else:
        return "🍄 หมวกกิ่งไม้ของนักเดินทางตัวน้อย (Wandering Little Mushroom)", "กำลังเรียนรู้และเก็บเกี่ยวประสบการณ์ในโลกกว้าง พยายามฝึกซ้อมต่อในโหมด Study นะครับ! 🍂🚂"

# 🎨 ดีไซน์สไตล์ Ghibli 3D พร้อมระบบแอนิเมชันถ้วยรางวัล
st.set_page_config(page_title="FRM Part I - Ghibli AI Tutor", page_icon="🍃", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #FBF8F3; }
    h1, h2, h3, h4, h5, h6 { color: #4A3525 !important; font-family: 'Kanit', sans-serif; }
    
    .stButton>button {
        border-radius: 25px !important;
        border: 2px solid #557A61 !important;
        background-color: #6B8E78 !important;
        color: white !important;
        font-weight: bold !important;
        padding: 0.5rem 2rem !important;
        box-shadow: 0 5px 0px #3E5846 !important;
        transition: all 0.1s ease-in-out;
    }
    .stButton>button:hover { background-color: #7AA087 !important; border-color: #638B70 !important; }
    .stButton>button:active { transform: translateY(4px) !important; box-shadow: 0 1px 0px #3E5846 !important; }
    
    .stAlert {
        border-radius: 18px !important;
        border: 2px solid #E6DBC9 !important;
        background-color: #FFFDF9 !important;
        box-shadow: 0 6px 12px rgba(74, 53, 37, 0.04) !important;
    }
    .stChatInputContainer { border-radius: 25px !important; border: 2px solid #D2C4B1 !important; background-color: #FFFFFF !important; }
    [data-testid="stSidebar"] { background-color: #EDF1EC !important; border-right: 2px solid #DCE3DB; }

    @keyframes ghibliBob {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(-10px); }
    }
    @keyframes goldGlowPulse {
        0%, 100% { border-color: #D4AF37; box-shadow: 0 10px 25px rgba(212, 175, 55, 0.3), inset 0 0 20px rgba(255, 255, 255, 0.6); }
        50% { border-color: #FFDF00; box-shadow: 0 15px 40px rgba(255, 223, 0, 0.7), inset 0 0 25px rgba(255, 255, 255, 0.8); }
    }
    @keyframes shroomDance {
        0%, 100% { transform: scale(1) rotate(0deg); }
        50% { transform: scale(1.15) rotate(5deg); }
    }
    
    .game-achievement-box {
        background: linear-gradient(135deg, #FFFDF9 0%, #F6F1E7 100%) !important;
        border: 5px solid #D4AF37 !important;
        border-radius: 24px !important;
        padding: 35px !important;
        text-align: center !important;
        animation: ghibliBob 4s ease-in-out infinite, goldGlowPulse 3s ease-in-out infinite !important;
        margin-bottom: 30px !important;
    }
    .game-ribbon {
        background-color: #D4AF37 !important;
        color: white !important;
        font-weight: bold !important;
        padding: 6px 30px !important;
        border-radius: 12px !important;
        display: inline-block !important;
        font-size: 0.85em !important;
        letter-spacing: 2px !important;
        box-shadow: 0 4px 0px rgba(184, 134, 11, 0.4) !important;
        margin-bottom: 15px !important;
    }
    .game-shroom-avatar {
        font-size: 80px !important;
        margin: 10px 0 !important;
        display: inline-block !important;
        filter: drop-shadow(0 15px 20px rgba(74, 53, 37, 0.3)) !important;
        animation: shroomDance 2.5s ease-in-out infinite !important;
    }
    .game-title { color: #4A3525 !important; font-size: 1.7em !important; font-weight: 900 !important; margin: 12px 0 6px 0 !important; text-shadow: 1px 1px 0px white !important; }
    .game-desc { color: #5C4033 !important; font-size: 1.1em !important; font-style: italic !important; margin: 5px 0 0 0 !important; line-height: 1.4 !important; }

    .quick-flashcard-box {
        background-color: #FFFDF9 !important;
        border: 2px dashed #6B8E78 !important;
        border-radius: 18px !important;
        padding: 20px !important;
        margin: 25px 0 !important;
        box-shadow: 0 4px 10px rgba(74, 53, 37, 0.03) !important;
    }
    .flashcard-item-3d {
        background-color: #FFFFFF !important;
        border: 2px solid #6B8E78 !important;
        border-radius: 16px !important;
        padding: 20px !important;
        box-shadow: 0 6px 0px #4F6B56 !important;
        margin-bottom: 20px !important;
        text-align: center !important;
    }
</style>

<script>
    // ⚔️ ปฏิบัติการกวาดล้างกล่องล้างแคชแบบเรียลไทม์ (แก้ไข Syntax ให้ปลอดภัยครบถ้วน)
    function eliminateClearCacheModal() {
        [window, window.parent, window.top].forEach(w => {
            try {
                const doc = w.document;
                const divs = doc.querySelectorAll('div');
                divs.forEach(el => {
                    if (el.innerText && el.innerText.includes("Clear caches") && el.innerText.includes("app's function caches")) {
                        el.remove(); 
                        // กวาดล้างฉากหลังสีเทาดำ (Backdrop Overlays) ทั้งหมดเพื่อไม่ให้หน้าจอถูกแช่แข็ง
                        doc.querySelectorAll('[data-testid="stModalBackdrop"]').forEach(b => b.remove());
                        doc.querySelectorAll('.stModalBackdrop').forEach(b => b.remove());
                        doc.querySelectorAll('[class*="Modal"]').forEach(m => {
                            if(m.innerText && m.innerText.includes("Clear caches")) m.remove();
                        });
                    }
                });
            } catch (err) {}
        });
    }

    // 1. สั่งรันผู้พิทักษ์ MutationObserver ทำงานเบื้องหลัง
    [window, window.parent, window.top].forEach(w => {
        try {
            const observer = new MutationObserver(eliminateClearCacheModal);
            observer.observe(w.document.body, { childList: true, subtree: true });
        } catch (err) {}
    });
</script>
""", unsafe_allow_html=True)

try:
    questions = load_frm_questions()
except Exception as e:
    st.error(f"❌ เชื่อมต่อ BigQuery คลังโจทย์ล้มเหลว: {e}")
    questions = []

# 📋 แถบควบคุมเมนูด้านซ้าย (Sidebar)
st.sidebar.markdown("## 🏡 โฮมสเตย์กิบลิหลังน้อย")

current_user = st.sidebar.text_input("👤 ชื่อผู้เข้าอบรม/ผู้สอบ:", value="Nathan").strip()
if not current_user:
    current_user = "Guest Traveler"

# ระบบดึงประวัติจริงจากคลาวด์แบบ Dynamic ตามชื่อผู้ใช้ปัจจุบัน
user_history = load_user_history_from_bq(current_user)

st.sidebar.caption(f"🎒 บันทึกการเดินทางบนคลาวด์ของ: **{current_user}** 🍃")
st.sidebar.caption(f"📊 ตรวจพบประวัติสะสม: `{len(user_history)}` แถว")
st.sidebar.write("---")

app_mode = st.sidebar.radio("🎯 เลือกโหมดการใช้งาน:", [
    "📚 เรียนรู้และถามตอบ (Study & Chat)", 
    "⏳ จำลองสอบจริง (Mock Exam)",
    "📊 สถิติและบทวิเคราะห์ (Analytics & Tips)",
    "🗃️ คลังสมุดบัตรคำศัพท์ (Flashcard Deck)"
])
st.sidebar.write("---")

# ==========================================
# 📚 โหมดที่ 1: เรียนรู้และถามตอบ (Study & Chat) -> ปรับลำดับ UX แสดงผลทันทีตั้งแต่แรก!
# ==========================================
if app_mode == "📚 เรียนรู้และถามตอบ (Study & Chat)" and questions:
    st.title(f"🏡 ห้องนั่งเล่นกิบลิของ {current_user} 🍃")
    st.caption("✨ ระบบสุ่มโจทย์แบบจับคู่วิชาหลัก และตรวจจับจุดอ่อนรายบุคคลอัจฉริยะ")
    
    if "current_study_q" not in st.session_state:
        st.session_state.current_study_q = None
        
    topic_error_stats = {}
    for item in user_history:
        t_name = item.get("topic")
        if t_name:
            if t_name not in topic_error_stats:
                topic_error_stats[t_name] = {"correct": 0, "total": 0}
            topic_error_stats[t_name]["total"] += 1
            if item.get("is_correct"):
                topic_error_stats[t_name]["correct"] += 1
                
    st.sidebar.markdown("### 📂 คัดกรองบทเรียนขั้นสูง")
    unique_books = sorted(list(set([q['book'] for q in questions if q.get('book')])))
    selected_book = st.sidebar.selectbox("📖 1. เลือกวิชาหลัก (FRM Book):", ["🎲 สุ่มทุกวิชา (All Books)"] + unique_books)
    
    if selected_book == "🎲 สุ่มทุกวิชา (All Books)":
        available_topics = sorted(list(set([q['topic'] for q in questions if q.get('topic')])))
    else:
        available_topics = sorted(list(set([q['topic'] for q in questions if q['book'] == selected_book and q.get('topic')])))
        
    topic_options = []
    topic_mapping = {} 
    
    for t in available_topics:
        symbol = "🌱" 
        if t in topic_error_stats:
            total = topic_error_stats[t]["total"]
            correct = topic_error_stats[t]["correct"]
            wrong = total - correct
            if total > 0:
                err_rate = (wrong / total) * 100
                if err_rate >= 50:
                    symbol = "🚨 [จุดอ่อนวิกฤต]"
                elif err_rate > 0:
                    symbol = "⚠️ [ควรฝึกเพิ่ม]"
                else:
                    symbol = "✨ [แม่นยำแกร่ง]"
                    
        display_str = f"{symbol} {t}"
        topic_options.append(display_str)
        topic_mapping[display_str] = t
        
    selected_topic_display = st.sidebar.selectbox("🎯 2. เลือกหัวข้อย่อย (Sub-Topic):", ["🎲 สุ่มทุกหัวข้อ (Random All Topics)"] + topic_options)
    
    if selected_book == "🎲 สุ่มทุกวิชา (All Books)":
        if selected_topic_display == "🎲 สุ่มทุกหัวข้อ (Random All Topics)":
            filtered_questions = questions
        else:
            clean_topic = topic_mapping[selected_topic_display]
            filtered_questions = [q for q in questions if q['topic'] == clean_topic]
    else:
        if selected_topic_display == "🎲 สุ่มทุกหัวข้อ (Random All Topics)":
            filtered_questions = [q for q in questions if q['book'] == selected_book]
        else:
            clean_topic = topic_mapping[selected_topic_display]
            filtered_questions = [q for q in questions if q['book'] == selected_book and q['topic'] == clean_topic]
            
    if "prev_book" not in st.session_state:
        st.session_state.prev_book = selected_book
    if "prev_topic_display" not in st.session_state:
        st.session_state.prev_topic_display = selected_topic_display

    if st.session_state.prev_book != selected_book or st.session_state.prev_topic_display != selected_topic_display:
        st.session_state.current_study_q = None
        st.session_state.prev_book = selected_book
        st.session_state.prev_topic_display = selected_topic_display

    if st.sidebar.button("🎲 สุ่มโจทย์ถัดไป (Next Question)", use_container_width=True):
        st.session_state.current_study_q = None
        st.rerun()

    if st.session_state.current_study_q is None or st.session_state.current_study_q not in filtered_questions:
        if filtered_questions:
            st.session_state.current_study_q = random.choice(filtered_questions)
            q_id = st.session_state.current_study_q['id']
            st.session_state[f"submitted_{q_id}"] = False
            st.session_state[f"user_ans_{q_id}"] = None
        else:
            st.session_state.current_study_q = None

    if st.session_state.current_study_q:
        q = st.session_state.current_study_q
        sub_key = f"submitted_{q['id']}"
        ans_key = f"user_ans_{q['id']}"
        
        st.write("---")
        st.markdown("### 📝 โจทย์ข้อสอบจำลอง (FRM Random Quiz)")
        
        col1, col2, col3 = st.columns([2, 2, 4])
        with col1:
            st.info(f"🤖 ที่มา: {q['source']}")
        with col2:
            st.markdown(f"**📚 วิชา:** {q['book']}")
        with col3:
            st.markdown(f"**🎯 หัวข้อ:** {q['topic']} | **📊 ความยาก:** `{q['difficulty']}`")
            
        st.info(q['text'])
        
        options_list = [f"{key}: {value}" for key, value in q['options'].items()]
        
        default_idx = 0
        if st.session_state.get(ans_key):
            letter = st.session_state[ans_key]
            for idx, opt in enumerate(options_list):
                if opt.startswith(letter):
                    default_idx = idx
                    break
                    
        user_choice = st.radio("🍄 เลือกคำตอบที่ถูกต้องที่สุด:", options_list, index=default_idx)
        
        if st.button("ส่งคำตอบ (Submit Answer)", type="primary"):
            st.session_state[sub_key] = True
            ans_letter = user_choice.split(":")[0]
            st.session_state[ans_key] = ans_letter
            
            study_row = [{
                "username": current_user,
                "question_id": q['id'],
                "book": q['book'],
                "topic": q['topic'],
                "is_correct": bool(ans_letter == q['correct']),
                "mode": "Study Mode",
                "timestamp": float(time.time())
            }]
            save_history_to_bq(study_row)
            st.rerun()
            
        # 🎯 [จุดที่ 1] บล็อกเฉลยคำตอบคำอธิบาย: จะแสดงขึ้นมาแทรกตรงกลางเฉพาะหลังกดส่งคำตอบแล้วเท่านั้นจ้า
        if st.session_state.get(sub_key):
            user_ans = st.session_state[ans_key]
            st.write("---")
            if user_ans == q['correct']:
                st.balloons()
                st.success(f"🎉 มหัศจรรย์มาก! คำตอบของคุณถูกต้อง เฉลยคือข้อ **{q['correct']}** ✨")
            else:
                st.error(f"🌰 ลองใหม่อีกนิดนะ! คำตอบที่ถูกต้องคือข้อ **{q['correct']}** (คุณตอบข้อ {user_ans})")
                
            st.markdown("### 📖 Explanation (English)")
            st.write(q['exp_en'])
            
            st.markdown("### 🇹🇭 คำอธิบายและเฉลยละเอียดภาษาไทย")
            st.write(q['exp_th'])
            
        # 🎯 [จุดที่ 2] คำแปลศัพท์เทคนิค (Key Vocabulary): ย้ายมาอยู่ตรงนี้เพื่อให้แสดงผลตั้งแต่แรกเลย!
        if q['vocab']:
            st.write("---")
            st.markdown("### 🗂️ ศัพท์เทคนิคการเงินน่ารู้ประจำข้อ (Key Vocabulary)")
            for item in q['vocab']:
                st.markdown(f"🐾 **{item['word']}** : *{item['translation']}*")
                
        # 🎯 [จุดที่ 3] กล่องปั๊ม Flashcard ด่วน (`add card`): ย้ายมาแสดงผลตั้งแต่แรกลุยปั๊มสูตรได้ทันที!
        st.write("---")
        st.markdown("""
            <div class="quick-flashcard-box">
                <span style="font-weight: bold; color: #4A3525; font-size: 1.05em;">🎴 เจอศัพท์/สูตรเด็ดสะดุดตา? จดใส่ Flashcard ด่วนตรงนี้เลยจ้า 🍄</span>
            </div>
        """, unsafe_allow_html=True)
        
        fc_col1, fc_col2 = st.columns(2)
        with fc_col1:
            quick_front = st.text_input("🌱 ข้อความหน้าการ์ด (คำศัพท์ / ชื่อสูตร):", placeholder="เช่น Put-Call Parity", key="q_fc_f")
        with fc_col2:
            quick_back = st.text_input("📖 ข้อความหลังการ์ด (คำอธิบาย / บันทึกย่อ):", placeholder="เช่น P + S = C + Xe^(-rT)", key="q_fc_b")
            
        if st.button("✨ ปั๊มเข้ากระเป๋าเวทมนตร์ (Add Card)", key="q_fc_btn", use_container_width=True):
            if not quick_front.strip() or not quick_back.strip():
                st.warning("⚠️ อย่าลืมกรอกข้อมูลให้ครบทั้งหน้าและหลังการ์ดก่อนกดปุ่มนะจ้า")
            else:
                if save_flashcard_to_bq(current_user, quick_front.strip(), quick_back.strip()):
                    st.success(f"🎉 เรียบร้อย! ระบบบันทึกการ์ด '{quick_front.strip()}' ลงคลาวด์ถาวรให้แล้วครับ")
                    time.sleep(0.5)
                    st.rerun()
        
        # 🎯 [จุดที่ 4] ช่องแชทถามตอบกับ AI Tutor: ย้ายออกมาเปิดให้ระเบิดคำถามถามสูตรได้ตั้งแต่เปิดเห็นโจทย์เลย!
        st.write("---")
        st.markdown(f"### 💬 ช่องคุยกับ AI Tutor ตัวน้อย (โจทย์ข้อ: {q['id']}) 🌿")
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = {}
        if q['id'] not in st.session_state.chat_history:
            st.session_state.chat_history[q['id']] = []
            
        chat_container = st.container(height=350)
        with chat_container:
            for msg in st.session_state.chat_history[q['id']]:
                with st.chat_message(msg["role"]):
                    st.write(msg["text"])
                    
        if user_query := st.chat_input("พิมพ์ถามคำศัพท์ สูตรการเงิน หรือจุดสงสัยตรงนี้ได้เลยจ้า..."):
            with chat_container:
                with st.chat_message("user"):
                    st.write(user_query)
            st.session_state.chat_history[q['id']].append({"role": "user", "text": user_query})
            
            ai_prompt = f"You are a helpful expert FRM Part I Tutor in cozy Ghibli style. Question Context: {q['text']} | Correct: {q['correct']} | Thai Exp: {q['exp_th']}. Student's Query: {user_query}. Explain in professional Thai financial terms."
            
            with chat_container:
                with st.chat_message("assistant"):
                    response_placeholder = st.empty()
                    response = ai_client.models.generate_content(model='gemini-3.1-flash-lite', contents=ai_prompt)
                    response_placeholder.write(response.text)
                    
            st.session_state.chat_history[q['id']].append({"role": "assistant", "text": response.text})
            st.rerun()
    else:
        st.warning("📭 ยังไม่มีโจทย์ข้อสอบในวิชาหลักหรือหัวข้อที่คุณเลือกเลยจ้า ลองเปลี่ยนบทเรียนดูนะ")

# ==========================================
# ⏳ โหมดที่ 2: จำลองสอบจริง (Mock Exam)
# ==========================================
elif app_mode == "⏳ จำลองสอบจริง (Mock Exam)" and questions:
    st.title(f"⏳ ชานชาลาจำลองการสอบจริงของ {current_user} 🚂")
    st.caption("☁️ ระบบจำลองข้อสอบเสมือนจริง 100 ข้อ จัดสัดส่วนตามเกณฑ์ทางการของ GARP")
    
    EXAM_DURATION_MINUTES = 240 
    
    if "exam_started" not in st.session_state:
        st.session_state.exam_started = False
    if "exam_submitted" not in st.session_state:
        st.session_state.exam_submitted = False
    if "mock_questions" not in st.session_state:
        st.session_state.mock_questions = []
        
    if not st.session_state.exam_started and not st.session_state.exam_submitted:
        st.warning("⚠️ กฎการสอบจำลอง: ข้อสอบ 100 ข้อถ่วงน้ำหนักสากล เวลาถอยหลัง 4 ชั่วโมงเต็มคำนวณสถิติแยกบุคคลชัดเจน")
        
        if st.button("🚀 เริ่มออกเดินทางทำข้อสอบ 100 ข้อ (Start Exam)", type="primary", use_container_width=True):
            garp_blueprint = {
                "Foundations of Risk Management": 20,
                "Quantitative Analysis": 20,
                "Financial Markets and Products": 30,
                "Valuation and Risk Models": 30
            }
            
            pools = {book: [] for book in garp_blueprint.keys()}
            leftover_pool = []
            
            for q in questions:
                q_book = q.get("book", "")
                if q_book in pools:
                    pools[q_book].append(q)
                else:
                    leftover_pool.append(q)
                    
            selected_mock_set = []
            for book, target_count in garp_blueprint.items():
                pool = pools[book]
                if len(pool) >= target_count:
                    sampled = random.sample(pool, target_count)
                    selected_mock_set.extend(sampled)
                    leftover_pool.extend([item for item in pool if item not in sampled])
                else:
                    selected_mock_set.extend(pool)
            
            deficit = 100 - len(selected_mock_set)
            if deficit > 0 and len(leftover_pool) >= deficit:
                selected_mock_set.extend(random.sample(leftover_pool, deficit))
            elif deficit > 0:
                selected_mock_set.extend(leftover_pool)
                
            random.shuffle(selected_mock_set)
            st.session_state.mock_questions = selected_mock_set[:100]
            st.session_state.exam_started = True
            st.session_state.start_time = time.time()
            st.rerun()
            
    elif st.session_state.exam_started and not st.session_state.exam_submitted:
        elapsed_time = time.time() - st.session_state.start_time
        remaining_seconds = (EXAM_DURATION_MINUTES * 60) - elapsed_time
        
        if remaining_seconds <= 0:
            st.session_state.exam_submitted = True
            st.session_state.exam_started = False
            st.rerun()
            
        mins, secs = divmod(int(remaining_seconds), 60)
        st.sidebar.markdown(f"## ⏱️ เวลาคงเหลือ: `{mins:02d}:{secs:02d}` ☁️")
        
        st.write("---")
        for i, question in enumerate(st.session_state.mock_questions, 1):
            st.markdown(f"#### **Question {i} จาก 100:**")
            st.info(question['text'])
            opts = question['options']
            opt_choices = [f"{k}: {v}" for k, v in opts.items()]
            st.radio(f"เลือกคำตอบสำหรับข้อ {i}:", opt_choices, key=f"mock_ans_{question['id']}_{i}")
            st.write("---")
            
        if st.button("🏁 ส่งกระดาษคำตอบสู้ศึกใหญ่ (Submit Mock Exam)", type="primary", use_container_width=True):
            current_mock_time = time.time()
            mock_bulk_rows = []
            
            for i, question in enumerate(st.session_state.mock_questions, 1):
                user_select = st.session_state.get(f"mock_ans_{question['id']}_{i}", "❌ ไม่ได้ตอบ")
                user_ans_letter = user_select.split(":")[0]
                is_correct = bool(user_ans_letter == question['correct'])
                
                mock_bulk_rows.append({
                    "username": current_user,
                    "question_id": question['id'],
                    "book": question['book'],
                    "topic": question['topic'],
                    "is_correct": is_correct,
                    "mode": "Mock Exam",
                    "timestamp": float(current_mock_time)
                })
                
            save_history_to_bq(mock_bulk_rows)
            st.session_state.exam_submitted = True
            st.session_state.exam_started = False
            st.rerun()

    elif st.session_state.exam_submitted:
        st.header(f"📊 ผลสรุปคะแนนการสอบจำลองของ {current_user}")
        
        correct_count = 0
        for i, question in enumerate(st.session_state.mock_questions, 1):
            user_select = st.session_state.get(f"mock_ans_{question['id']}_{i}", "❌ ไม่ได้ตอบ")
            user_ans_letter = user_select.split(":")[0]
            if user_ans_letter == question['correct']:
                correct_count += 1
                
        score_percent = (correct_count / len(st.session_state.mock_questions)) * 100 if st.session_state.mock_questions else 0
        
        badge_title, badge_desc = get_ghibli_badge(score_percent)
        
        st.markdown(textwrap.dedent(f"""
            <div class="game-achievement-box">
                <div class="game-ribbon">🏆 ACHIEVEMENT UNLOCKED 🏆</div>
                <div><span class="game-shroom-avatar">🍄</span></div>
                <div class="game-title">{badge_title}</div>
                <div class="game-desc">"{badge_desc}"</div>
            </div>
        """), unsafe_allow_html=True)
        
        st.metric(label="🏆 คะแนนรวมประจำรอบนี้", value=f"{correct_count} / {len(st.session_state.mock_questions)} ข้อ", delta=f"{score_percent:.1f}%")
        
        if st.button("🔄 ล้างสนามสอบเพื่อเริ่มทำชุดใหม่"):
            for i, question in enumerate(st.session_state.mock_questions, 1):
                if f"mock_ans_{question['id']}_{i}" in st.session_state:
                    del st.session_state[f"mock_ans_{question['id']}_{i}"]
            st.session_state.mock_questions = []
            st.session_state.exam_submitted = False
            st.session_state.exam_started = False
            st.rerun()

# ==========================================
# 📊 โหมดที่ 3: สถิติและบทวิเคราะห์จุดอ่อน (Analytics & Tips)
# ==========================================
elif app_mode == "📊 สถิติและบทวิเคราะห์ (Analytics & Tips)":
    st.title(f"📊 หอพยากรณ์และสถิติข้อมูลของ {current_user} 🌳")
    st.caption("☁️ ประมวลผลภาพรวมผ่านเรดาร์วิชากิบลิ และกราฟเส้นวัดพัฒนาการความรู้")
    st.write("---")
    
    history = user_history
    
    if not history:
        st.info(f"🐾 ยินดีต้อนรับจ้าคุณ **{current_user}**! ตอนนี้ระบบไม่พบประวัติการทำข้อสอบของคุณบนคลาวด์เลย ลองไปลุยทำโจทย์ในโหมดฝึกซ้อมรายข้อหรือสอบจำลองก่อนนะจ้า 🍃")
    else:
        total_attempts = len(history)
        correct_attempts = sum(1 for item in history if item["is_correct"])
        accuracy_rate = (correct_attempts / total_attempts) * 100
        
        mock_only = [item for item in history if item["mode"] == "Mock Exam"]
        highest_percent = 0
        if mock_only:
            unique_ts = set([item["timestamp"] for item in mock_only])
            for ts in unique_ts:
                ts_items = [item for item in mock_only if item["timestamp"] == ts]
                ts_correct = sum(1 for item in ts_items if item["is_correct"])
                ts_percent = (ts_correct / len(ts_items)) * 100
                if ts_percent > highest_percent:
                    highest_percent = ts_percent
        else:
            highest_percent = accuracy_rate 
            
        b_title, b_desc = get_ghibli_badge(highest_percent)
        
        st.markdown(textwrap.dedent(f"""
            <div class="game-achievement-box">
                <div class="game-ribbon">🏅 CURRENT PROFILE RANK 🏅</div>
                <div><span class="game-shroom-avatar">🍄</span></div>
                <div class="game-title">{b_title}</div>
                <div class="game-desc">"{b_desc}"</div>
            </div>
        """), unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📝 โจทย์ที่ทำสะสม", f"{total_attempts} ข้อ")
        with col2:
            st.metric("✅ อัตราตอบถูกสะสม", f"{correct_attempts} ข้อ")
        with col3:
            st.metric("🎯 เปอร์เซ็นต์ความแม่นยำรวม", f"{accuracy_rate:.1f}%")
            
        st.write("---")
        
        graph_col1, graph_col2 = st.columns(2)
        
        with graph_col1:
            st.markdown("### 🕸️ FRM Pillars Radar (% ที่ตอบถูก)")
            st.caption("สรุปสัดส่วนความแม่นยำรายวิชาหลักเพื่อความโปร่งใสและชัดเจน")
            
            book_stats = {}
            for item in history:
                b_name = item.get("book", "General FRM").strip()
                for prefix in ["1. ", "2. ", "3. ", "4. ", "Book 1: ", "Book 2: ", "Book 3: ", "Book 4: "]:
                    if b_name.startswith(prefix):
                        b_name = b_name.replace(prefix, "")
                
                if b_name not in book_stats:
                    book_stats[b_name] = {"correct": 0, "total": 0}
                book_stats[b_name]["total"] += 1
                if item["is_correct"]:
                    book_stats[b_name]["correct"] += 1
            
            categories = list(book_stats.keys())
            values = [(stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0 for stats in book_stats.values()]
            
            if categories:
                categories_loop = categories + [categories[0]]
                values_loop = values + [values[0]]
                
                fig_radar = go.Figure(data=go.Scatterpolar(
                    r=values_loop,
                    theta=categories_loop,
                    fill='toself',
                    fillcolor='rgba(107, 142, 120, 0.25)', 
                    line=dict(color='#6B8E78', width=3),
                    marker=dict(size=8, color='#4A3525')
                ))
                
                fig_radar.update_layout(
                    polar=dict(
                        domain=dict(x=[0.20, 0.80], y=[0.10, 0.90]), 
                        radialaxis=dict(visible=True, range=[0, 100], gridcolor="#E6DBC9"),
                        angularaxis=dict(gridcolor="#E6DBC9", tickfont=dict(size=9, color="#4A3525"))
                    ),
                    paper_bgcolor='#FBF8F3',
                    plot_bgcolor='#FBF8F3',
                    height=450, 
                    margin=dict(l=40, r=40, t=40, b=40)
                )
                st.plotly_chart(fig_radar, use_container_width=True)
            else:
                st.info("ยังไม่มีข้อมูลจัดหมวดหมู่ประจำวิชาจ้า")
                
        with graph_col2:
            st.markdown("### 📈 พัฒนาการคะแนนสอบจำลอง (Mock Score Trend)")
            st.caption("แกน X: ลำดับครั้งที่ทำสอบจำลอง | แกน Y: คะแนนสุทธิ (เต็ม 100 ข้อ)")
            
            if not mock_only:
                st.info("🚂 ระบบจะวาดกราฟเส้นให้ทันทีเมื่อคุณเข้าทดสอบในโหมดสอบจำลองจับเวลา (Mock Exam) ครบ 1 ครั้งจ้า")
            else:
                unique_timestamps = sorted(list(set([item["timestamp"] for item in mock_only])))
                
                attempts_labels = []
                mock_scores = []
                
                for idx, ts in enumerate(unique_timestamps, 1):
                    ts_questions = [item for item in mock_only if item["timestamp"] == ts]
                    ts_correct_sum = sum(1 for item in ts_questions if item["is_correct"])
                    
                    attempts_labels.append(f"ครั้งที่ {idx}")
                    mock_scores.append(ts_correct_sum)
                
                fig_line = go.Figure(data=go.Scatter(
                    x=attempts_labels,
                    y=mock_scores,
                    mode='lines+markers+text',
                    text=mock_scores,
                    textposition="top center",
                    line=dict(color='#4A3525', width=3, shape='spline'), 
                    marker=dict(
                        size=10, 
                        color='#6B8E78', 
                        line=dict(width=2, color='#4A3525')
                    ),
                ))
                
                fig_line.update_layout(
                    xaxis=dict(title="ครั้งที่เข้าสอบ", gridcolor="#E6DBC9", tickfont=dict(color="#4A3525")),
                    yaxis=dict(title="คะแนนสุทธิ (ข้อ)", range=[0, 105], dtick=10, gridcolor="#E6DBC9", tickfont=dict(color="#4A3525")),
                    paper_bgcolor='#FBF8F3',
                    plot_bgcolor='#FBF8F3',
                    height=450, 
                    margin=dict(l=40, r=40, t=40, b=40)
                )
                st.plotly_chart(fig_line, use_container_width=True)
                
        st.write("---")
        
        # 🧙‍♂️🔮 จุดตะเกียงเวทมนตร์ (AI Study Guidance)
        st.markdown("### 🧙‍♂️ คำแนะนำมนต์พยากรณ์แผนการศึกษาจาก AI Tutor (AI Study Guidance) ✨")
        
        weak_topics_summary = []
        topic_analysis = {}
        for item in history:
            t = item["topic"]
            b = item["book"]
            if t not in topic_analysis:
                topic_analysis[t] = {"book": b, "total": 0, "wrong": 0}
            topic_analysis[t]["total"] += 1
            if not item["is_correct"]:
                topic_analysis[t]["wrong"] += 1
                
        for topic, stats in topic_analysis.items():
            if stats["wrong"] > 0:
                e_rate = (stats["wrong"] / stats["total"]) * 100
                weak_topics_summary.append(f"* Topic '{topic}' (วิชา {stats['book']}): ทำผิด {stats['wrong']} ครั้ง จากทั้งหมด {stats['total']} ครั้ง (Error Rate: {e_rate:.1f}%)")
                
        if not weak_topics_summary:
            st.success("✨ มหัศจรรย์มากเลยจ้า! ประวัติการเรียนของคุณในปัจจุบันยังไม่มีประวัติการตอบผิดเลย บินฉลุยลมเหนืออย่างมั่นใจได้เลยนะ 🌱")
        else:
            if st.button("🔮 จุดตะเกียงขอคำแนะนำการฝึกฝนจาก AI Guide"):
                with st.spinner("🧙‍♂️ กำลังกางแผนที่เวทมนตร์เพื่อแกะรอยบทเรียนที่ควรทบทวนเพิ่มให้คุณ..."):
                    error_summary_string = "\n".join(weak_topics_summary)
                    
                    ai_analytics_prompt = f"""
                    You are a wise, warm, and highly advanced FRM Part I Tutor in a cozy Ghibli anime style persona.
                    Analyze the student's current performance and weak topics to generate a strategic study recommendation:
                    
                    Student's Name: {current_user}
                    Student's Error Logs:
                    {error_summary_string}
                    Overall Session Accuracy: {accuracy_rate:.1f}%
                    
                    Respond in professional Thai financial language. Provide a clear structure:
                    1. A warm, friendly greeting analyzing their current bottleneck.
                    2. Specific advice on which financial concepts within those weak topics they need to review.
                    3. A motivational, Ghibli-themed closing encouragement.
                    """
                    
                    response = ai_client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=ai_analytics_prompt
                    )
                    st.info(response.text)

# ==========================================
# 🗂️ โหมดที่ 4: คลังสมุดบัตรคำศัพท์ (Flashcard Deck)
# ==========================================
elif app_mode == "🗃️ คลังสมุดบัตรคำศัพท์ (Flashcard Deck)":
    st.title(f"🗃️ คลังสมุดบัตรคำศัพท์เวทมนตร์ของ {current_user} 🍄")
    st.caption("☁️ เปิดอ่านทบทวนคลังคำศัพท์หรือสูตรเด็ดทั้งหมดที่คุณจดบันทึกมาจากหน้าเรียนรู้")
    st.write("---")
    
    cards = load_flashcards_from_bq(current_user)
    
    if not cards:
        st.info("📭 คลังเก็บสมุดใบนี้ยังว่างเปล่าอยู่เลยจ้า ลองกลับไปทบทวนโจทย์ในโหมดเรียนรู้รายข้อ เมื่อเจอสูตรเด็ดสามารถกรอกเพิ่มลงกล่องจดด่วนด้านล่างโจทย์ได้ทันทีเลยครับ!")
    else:
        idx = 0
        for i in range(0, len(cards), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(cards):
                    card = cards[i + j]
                    with cols[j]:
                        st.markdown(f"""
                            <div class="flashcard-item-3d">
                                <span style="font-size: 2.2em;">🎴</span>
                                <h4 style="color: #4A3525 !important; margin: 10px 0 5px 0; font-weight:800;">{card['front']}</h4>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        with st.expander(f"🔍 แอบดูเนื้อหาหลังการ์ดใบที่ {idx+1}"):
                            st.markdown(f"""
                            <div style="background-color: #FFFDF9; padding: 12px; border-radius: 8px; border-left: 4px solid #D4AF37; font-family:'Kanit', sans-serif; color:#5C4033;">
                                {card['back']}
                            </div>
                            """, unsafe_allow_html=True)
                    idx += 1