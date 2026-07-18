import os
import json
import time
import random
import streamlit as st
import pandas as pd
import plotly.express as px
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
# 🎨 2. ตั้งค่าธีมโฮมสเตย์กิบลิอบอุ่น (CSS เจาะระบบล็อก)
# =========================================================
st.set_page_config(page_title="FRM Ghibli Central", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600&display=swap');
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .stApp {
        background-color: #FFFDF9 !important;
        color: #4A3E3D !important;
        font-family: 'Sarabun', sans-serif;
    }
    .stButton>button {
        background-color: #8F9E8B !important; 
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        padding: 8px 20px !important;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #72826E !important;
        transform: translateY(-2px);
    }
    .tool-card {
        background-color: #F4EFEA !important;
        padding: 18px;
        border-radius: 14px;
        border-left: 6px solid #8F9E8B;
        margin-bottom: 20px;
    }
    .exam-timer {
        font-size: 1.6rem;
        font-weight: 600;
        color: #C87A7A;
        background-color: #FCEAEA;
        padding: 12px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 📊 3. ฟังก์ชันดึงคลังข้อสอบทั้งหมดจาก BigQuery Cloud
# =========================================================
@st.cache_data(show_spinner=False)
def load_global_questions():
    table_id = "frm-ai-tutor.FRM_DATASET.questions"
    query = f"SELECT * FROM `{table_id}`"
    try:
        query_job = bq_client.query(query)
        rows = query_job.result()
        pool = []
        for row in rows:
            options_dict = json.loads(row.options) if isinstance(row.options, str) else row.options
            vocab_list = json.loads(row.key_vocabulary) if isinstance(row.key_vocabulary, str) else row.key_vocabulary
            pool.append({
                "question_id": row.question_id,
                "book": row.book,
                "topic": row.topic,
                "difficulty": row.difficulty,
                "question_text": row.question_text,
                "options": options_dict,
                "correct_option": row.correct_option,
                "explanation_en": row.explanation_en,
                "explanation_th": row.explanation_th,
                "key_vocabulary": vocab_list
            })
        return pool
    except Exception:
        return []

global_pool = load_global_questions()

# =========================================================
# ⚙️ 4. บริหารกลไกตัวแปรระบบหลัก (Session State)
# =========================================================
if "my_flashcards" not in st.session_state:
    st.session_state.my_flashcards = []
if "practice_idx" not in st.session_state:
    st.session_state.practice_idx = 0
if "practice_submitted" not in st.session_state:
    st.session_state.practice_submitted = False
if "practice_chat" not in st.session_state:
    st.session_state.practice_chat = []
if "stats_history" not in st.session_state:
    st.session_state.stats_history = []

# ตัวแปรสำหรับโหมดจำลองสอบ (Mock Exam)
if "mock_questions" not in st.session_state:
    st.session_state.mock_questions = []
if "mock_user_answers" not in st.session_state:
    st.session_state.mock_user_answers = {}
if "mock_start_time" not in st.session_state:
    st.session_state.mock_start_time = None
if "mock_duration_minutes" not in st.session_state:
    st.session_state.mock_duration_minutes = 60
if "mock_completed" not in st.session_state:
    st.session_state.mock_completed = False

# =========================================================
# 🧭 5. แผงควบคุมด้านข้างและเมนูสลับหน้า (Sidebar Navigation)
# =========================================================
with st.sidebar:
    st.title("🌿 Ghibli Control")
    app_mode = st.radio("เลือกพื้นที่ทำงาน (Menu):", [
        "📝 Practice Mode", 
        "⏱️ Mock Exam Simulator", 
        "📊 Performance & AI Insights"
    ])
    
    st.markdown("---")
    st.header("🗂️ Flashcards สะสมด่วน")
    if st.session_state.my_flashcards:
        for i, card in enumerate(st.session_state.my_flashcards):
            st.info(f"📋 **Card {i+1}**\n{card}")
    else:
        st.caption("ยังไม่มีแฟลชการ์ดสะสมจ้า")

if not global_pool:
    st.warning("⚠️ ไม่พบข้อมูลโจทย์ในคลังข้อสอบคลาวด์ BigQuery กรุณาตรวจสอบการรันไฟล์ pipeline.py จ้า!")
else:
    # =========================================================
    # 🗂️ หน้าที่ 1: Practice Mode (ฝึกฝนแยกหัวข้อ)
    # =========================================================
    if app_mode == "📝 Practice Mode":
        st.header("📝 Practice Mode (ฝึกฝนรายหัวข้อ)")
        
        books_available = sorted(list(set([q['book'] for q in global_pool])))
        selected_book = st.selectbox("1. เลือกเล่มหลักสูตร FRM Book:", ["Show All"] + books_available)
        
        if selected_book != "Show All":
            topics_available = sorted(list(set([q['topic'] for q in global_pool if q['book'] == selected_book])))
        else:
            topics_available = sorted(list(set([q['topic'] for q in global_pool])))
        selected_topic = st.selectbox("2. เลือกหัวข้อเฉพาะทาง Topic:", ["Show All"] + topics_available)
        
        filtered_pool = global_pool
        if selected_book != "Show All":
            filtered_pool = [q for q in filtered_pool if q['book'] == selected_book]
        if selected_topic != "Show All":
            filtered_pool = [q for q in filtered_pool if q['topic'] == selected_topic]
            
        if not filtered_pool:
            st.info("🍃 หัวข้อที่คุณเลือกยังไม่มีข้อสอบบรรจุอยู่ ลองเลือกหัวข้ออื่นดูนะจ้า")
        else:
            if st.session_state.practice_idx >= len(filtered_pool):
                st.session_state.practice_idx = 0
                
            q = filtered_pool[st.session_state.practice_idx]
            
            st.markdown(f"**📌 Question {st.session_state.practice_idx + 1} / {len(filtered_pool)}**")
            st.info(f"Book: {q['book']} | Topic: {q['topic']} | Difficulty: {q['difficulty']}")
            st.write(q['question_text'])
            
            # 🛠️ เคลียร์เศษข้อความออกเกลี้ยงชิ้นช้อยส์ D รันฉลุยแน่นอนครับ
            opts = [
                f"A: {q['options'].get('A','')}", 
                f"B: {q['options'].get('B','')}", 
                f"C: {q['options'].get('C','')}", 
                f"D: {q['options'].get('D','')}"
            ]
            u_ans = st.radio("เลือกคำตอบที่แม่นยำที่สุดตามหลักบริหารความเสี่ยง:", opts, index=0, key=f"prac_{q['question_id']}")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🚀 ส่งคำตอบตรวจทาน (Submit)", use_container_width=True):
                    st.session_state.practice_submitted = True
            with c2:
                if st.button("⏭️ สลับข้อถัดไป (Next Random)", use_container_width=True):
                    st.session_state.practice_idx = random.randint(0, len(filtered_pool) - 1)
                    st.session_state.practice_submitted = False
                    st.session_state.practice_chat = []
                    st.rerun()
                    
            if st.session_state.practice_submitted:
                st.markdown("---")
                final_choice = u_ans[0]
                if final_choice == q['correct_option']:
                    st.success(f"✨ ยอดเยี่ยมมากครับเฉลยถูกต้องคือข้อ {q['correct_option']}!")
                    if not any(d.get('recorded_id') == q['question_id'] for d in st.session_state.stats_history):
                        st.session_state.stats_history.append({"book": q['book'], "topic": q['topic'], "is_correct": 1, "recorded_id": q['question_id']})
                else:
                    st.error(f"ผิดพลาดเล็กน้อยจ้า เฉลยที่แท้จริงคือข้อ {q['correct_option']}")
                    if not any(d.get('recorded_id') == q['question_id'] for d in st.session_state.stats_history):
                        st.session_state.stats_history.append({"book": q['book'], "topic": q['topic'], "is_correct": 0, "recorded_id": q['question_id']})
                        
                st.markdown(f"**📖 Detailed Explanation (EN):**\n{q['explanation_en']}")
                st.markdown(f"**🇹🇭 คำอธิบายและเฉลยละเอียดภาษาไทย:**\n{q['explanation_th']}")
                
            # กางแผงเครื่องมือช่วยคิดวิเคราะห์ 3 ชิ้นพร้อมกันแบบเปิดเผย
            st.markdown("---")
            st.subheader("🛠️ เครื่องมือช่วยคิดและวิเคราะห์ประจำข้อสอบ")
            
            st.markdown('<div class="tool-card"><div class="tool-title">📚 ศัพท์เฉพาะประจำข้อ (Key Vocabulary)</div></div>', unsafe_allow_html=True)
            if q['key_vocabulary']:
                for item in q['key_vocabulary']:
                    st.markdown(f"🔹 **{item.get('word','')}** : {item.get('translation','')}")
            else:
                st.caption("ข้อนี้ไม่มีศัพท์เทคนิคยากเพิ่มเติมจ้า")
                
            st.markdown('<div class="tool-card"><div class="tool-title">📝 บันทึกแฟลชการ์ดเข้ากล่องความจำ</div></div>', unsafe_allow_html=True)
            txt_input = st.text_area("สรุปย่อหรือคัดสูตรเด็ดมาวางที่นี่เพื่อบันทึกไปที่บอร์ดซ้ายมือ:", key="note_area", placeholder="พิมพ์โน้ตส่วนตัว...")
            if st.button("💾 เซฟแฟลชการ์ด (Save Card)"):
                if txt_input.strip():
                    st.session_state.my_flashcards.append(txt_input.strip())
                    st.toast("บันทึกแฟลชการ์ดใบใหม่ขึ้นบอร์ดเรียบร้อยแล้วจ้า! 🌰")
                    st.rerun()
                    
            st.markdown('<div class="tool-card"><div class="tool-title">🧙‍♂️ ช่องแชทติวเตอร์เวทมนตร์ (AI Tutor)</div></div>', unsafe_allow_html=True)
            for m in st.session_state.practice_chat:
                with st.chat_message(m["role"]): 
                    st.write(m["text"])
            c_input = st.chat_input("💬 สอบถามข้อสงสัยเกี่ยวกับสูตรคำนวณหรือตรรกะข้อนี้...")
            if c_input:
                st.session_state.practice_chat.append({"role": "user", "text": c_input})
                ctx = f"You are a warm FRM tutor. Question: {q['question_text']}. User asks: {c_input}. Answer warmly and concisely using 'ครับจ้า'"
                with st.spinner("AI กำลังเรียบเรียงคำตอบ..."):
                    res = ai_client.models.generate_content(model='gemini-3.1-flash-lite', contents=ctx)
                    st.session_state.practice_chat.append({"role": "model", "text": res.text})
                st.rerun()

    # =========================================================
    # ⏱️ หน้าที่ 2: Mock Exam Simulator (100 ข้อ & 4 ชั่วโมงเสถียร)
    # =========================================================
    elif app_mode == "⏱️ Mock Exam Simulator":
        st.header("⏱️ Mock Exam Simulator (จำลองการสอบแข่งขันจริง)")
        st.caption("ดึงโจทย์สลับวิชาตามโควตาน้ำหนักสากลของ GARP (Foundations 20%, Quant 20%, Markets 30%, Models 30%)")
        
        if not st.session_state.mock_questions and not st.session_state.mock_completed:
            st.subheader("🎲 การตั้งค่าจัดชุดข้อสอบจำลองสนามจริง")
            
            exam_size = st.slider("เลือกจำนวนข้อสอบจำลอง (Select Questions Target):", min_value=1, max_value=100, value=20, step=1)
            duration = st.slider("เลือกเวลาทำข้อสอบ (Select Time Limit ในหน่วยนาที):", min_value=5, max_value=240, value=60, step=5)
            
            h_label, m_label = divmod(duration, 60)
            st.caption(f"💡 โควตาเวลาสอบสุทธิ: **{h_label} ชั่วโมง {m_label} นาที (Total: {duration} Mins)**")
            
            if st.button("🎬 เริ่มทำข้อสอบจำลอง (Start Exam)"):
                w_b1 = max(1, int(exam_size * 0.20))
                w_b2 = max(1, int(exam_size * 0.20))
                w_b3 = max(1, int(exam_size * 0.30))
                w_b4 = max(1, int(exam_size * 0.30))
                
                pool_b1 = [x for x in global_pool if "Foundations" in x['book']]
                pool_b2 = [x for x in global_pool if "Quantitative" in x['book']]
                pool_b3 = [x for x in global_pool if "Markets" in x['book']]
                pool_b4 = [x for x in global_pool if "Valuation" in x['book']]
                
                selected_mock = []
                if pool_b1: selected_mock.extend(random.sample(pool_b1, min(len(pool_b1), w_b1)))
                if pool_b2: selected_mock.extend(random.sample(pool_b2, min(len(pool_b2), w_b2)))
                if pool_b3: selected_mock.extend(random.sample(pool_b3, min(len(pool_b3), w_b3)))
                if pool_b4: selected_mock.extend(random.sample(pool_b4, min(len(pool_b4), w_b4)))
                
                random.shuffle(selected_mock)
                st.session_state.mock_questions = selected_mock
                st.session_state.mock_start_time = time.time()
                st.session_state.mock_duration_minutes = duration
                st.session_state.mock_user_answers = {}
                st.session_state.mock_completed = False
                st.rerun()
                
        if st.session_state.mock_questions and not st.session_state.mock_completed:
            elapsed = time.time() - st.session_state.mock_start_time
            total_seconds = st.session_state.mock_duration_minutes * 60
            remaining = total_seconds - elapsed
            
            if remaining <= 0:
                st.session_state.mock_completed = True
                st.warning("🚨 หมดเวลาทำข้อสอบจำลองแล้ว! ระบบทำการรวบรวมและตัดเกรดส่งคะแนนอัตโนมัติ...")
                st.rerun()
                
            hours, remainder = divmod(int(remaining), 3600)
            mins, secs = divmod(remainder, 60)
            st.markdown(f'<div class="exam-timer">⏳ Remaining Time: {hours:02d}:{mins:02d}:{secs:02d} ชั่วโมง</div>', unsafe_allow_html=True)
            
            for idx, mq in enumerate(st.session_state.mock_questions):
                st.markdown(f"**📌 Question {idx + 1}:** ({mq['book']})")
                st.write(mq['question_text'])
                
                m_opts = {
                    "A": f"A: {mq['options'].get('A','')}",
                    "B": f"B: {mq['options'].get('B','')}",
                    "C": f"C: {mq['options'].get('C','')}",
                    "D": f"D: {mq['options'].get('D','')}"
                }
                
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
            correct_count = 0
            mock_logs = []
            
            for mq in st.session_state.mock_questions:
                u_pick = st.session_state.mock_user_answers.get(mq['question_id'], "N/A")
                is_correct = 1 if u_pick == mq['correct_option'] else 0
                if is_correct: correct_count += 1
                
                if not any(d.get('recorded_id') == f"M_{mq['question_id']}" for d in st.session_state.stats_history):
                    st.session_state.stats_history.append({"book": mq['book'], "topic": mq['topic'], "is_correct": is_correct, "recorded_id": f"M_{mq['question_id']}"})
                
                mock_logs.append({
                    "Curriculum Book": mq['book'],
                    "Your Pick": u_pick,
                    "Correct Ans": mq['correct_option'],
                    "Status": "✅ Correct" if is_correct else "❌ Incorrect"
                })
                
            st.metric("Total Score", f"{correct_count} / {len(st.session_state.mock_questions)} ข้อ", 
                      delta=f"Accuracy Rate: {int(correct_count/len(st.session_state.mock_questions)*100)}%")
            
            st.table(pd.DataFrame(mock_logs))
            
            if st.button("🔄 ล้างหน้าจอเพื่อเริ่มทำชุดข้อสอบใหม่ (Reset Mock)"):
                st.session_state.mock_questions = []
                st.session_state.mock_user_answers = {}
                st.session_state.mock_completed = False
                st.rerun()

    # =========================================================
    # 📊 หน้าที่ 3: Performance & AI Insights (สยบบั๊ก KeyError สมบูรณ์)
    # =========================================================
    elif app_mode == "📊 Performance & AI Insights":
        st.header("📊 Performance Dashboard & AI Weakness Analysis")
        st.caption("แดชบอร์ดประมวลผลแยกตามกลุ่มวิชา เพื่อวิเคราะห์หาจุดบกพร่องเชิงลึกรายบุคคล")
        
        if not st.session_state.stats_history:
            st.info("🍃 แผงสถิติยังไม่มีข้อมูลสะสมจ้า ลองเข้าทำข้อสอบจำลองหรือโหมดฝึกฝนก่อนเพื่อให้ระบบบันทึกคะแนนนะจ้า")
        else:
            df = pd.DataFrame(st.session_state.stats_history)
            
            # 🚀 [THE ULTIMATE FIX] จัดกลุ่มด้วยคอลัมน์ภาษาอังกฤษแท้ ป้องกัน KeyError ตัวแดงบนเซิร์ฟเวอร์คลาวด์ 100%
            summary_df = df.groupby('book')['is_correct'].agg(['count', 'sum']).reset_index()
            summary_df.columns = ['Book', 'Total Questions', 'Correct Answers']
            
            # คำนวณร้อยละความแม่นยำด้วยตัวแปรภาษาอังกฤษสากล
            summary_df['Accuracy (%)'] = (summary_df['Correct Answers'] / summary_df['Total Questions'] * 100).round(1)
            
            st.subheader("📈 Summary Table (สรุปตารางรายวิชาหลักสูตร)")
            st.dataframe(summary_df, use_container_width=True)
            
            # แสดงแผนภูมิแท่งความเที่ยงตรงด้วยสีกิบลิมินิมอลสบายตา
            fig = px.bar(summary_df, x='Book', y='Accuracy (%)', 
                         title="📊 Accuracy Rate by Curriculum Book (%)",
                         labels={'Book': 'Curriculum วิชาหลักสูตร', 'Accuracy (%)': 'Accuracy ความแม่นยำ (%)'},
                         color='Accuracy (%)', color_continuous_scale=px.colors.sequential.Mint)
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            st.subheader("🧙‍♂️ AI Weakness Auditor (กล่องคำแนะนำแผนการเรียนจากติวเตอร์กิบลิ)")
            st.write("กดปุ่มด้านล่างเพื่อสั่งให้ระบบวิเคราะห์ประวัติการสอบทั้งหมดของคุณ และจัดเตรียมแนวทางการทบทวนวิชาเฉพาะด้าน")
            
            if st.button("✨ เจาะลึกแผนการอ่านหนังสือ (Generate AI Insights Report)"):
                stats_text = ""
                for index, row in summary_df.iterrows():
                    stats_text += f"- Book '{row['Book']}': Answered {row['Total Questions']} questions, Correct {row['Correct Answers']} (Accuracy: {row['Accuracy (%)']}%)\n"
                    
                ai_analysis_prompt = f"""
                You are an elite, warm Ghibli-themed FRM Risk Management Executive and a Senior Tutor. 
                Analyze Nathan's current performance metrics below and generate a professional, highly strategic study guidance report.
                
                NATHAN'S ACCURACY PROFILE:
                {stats_text}
                
                INSTRUCTIONS FOR REPORT STRUCTURE:
                1. Identify which books require immediate critical attention based on low accuracy scores.
                2. Provide concrete risk-practitioner advice (e.g., focus more on Delta hedging formulas, OLS diagnostics, or Basel framework depending on the weak fields).
                3. Deliver the advice in a very warm, supportive, peer-like tone mixed with financial expertise. Use standard professional Thai banking terminology where appropriate. End sentences with 'ครับจ้า'.
                """
                
                with st.spinner("AI กำลังคำนวณสูตรและประมวลผลรายงานพิเศษให้คุณนาธานสักครู่จ้า..."):
                    try:
                        ai_report = ai_client.models.generate_content(
                            model='gemini-3.1-flash-lite',
                            contents=ai_analysis_prompt
                        )
                        st.markdown('<div class="tool-card">', unsafe_allow_html=True)
                        st.markdown("### 📜 รายงานผลสัมฤทธิ์และกลยุทธ์เตรียมสอบฉบับเฉพาะบุคคล (AI Study Report)")
                        st.write(ai_report.text)
                        st.markdown('</div>', unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"ระบบ AI ขัดข้องชั่วคราว: {e}")