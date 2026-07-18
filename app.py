import os
import json
import streamlit as st
import random
from google import genai
from google.cloud import bigquery
from google.oauth2 import service_account

# =========================================================
# 🔒 1. ระบบดึงกุญแจความลับและเชื่อมต่อ Cloud (คลาวด์เสถียร 100%)
# =========================================================
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))

if "GCP_JSON_TEXT" in st.secrets:
    # 🚀 โหมดรันบนคลาวด์สาธารณะ: แปลงเนื้อหา JSON จากกล่องความลับมาใช้ผ่าน Memory ทันที ป้องกัน Read-only File System
    gcp_info = json.loads(st.secrets["GCP_JSON_TEXT"])
    credentials = service_account.Credentials.from_service_account_info(gcp_info)
    bq_client = bigquery.Client(credentials=credentials, project=gcp_info["project_id"])
else:
    # 💻 โหมดรันในเครื่องคอมตัวเอง: ดึงไฟล์กุญแจตามปกติ
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "frm-ai-tutor-1cef93cd880b.json"
    bq_client = bigquery.Client()

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# =========================================================
# 🎨 2. ตั้งค่าธีมโฮมสเตย์กิบลิ & คาปิบาร่าสบายตา (Introvert WFH Vibe)
# =========================================================
st.set_page_config(page_title="FRM Ghibli Tutor", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600&display=swap');
    html, body, [class*="css"] {
        font-family: 'Sarabun', sans-serif;
        background-color: #FFFDF9; /* สีขาวครีมโทนอบอุ่นแบบกระดาษกิบลิ */
        color: #4A3E3D;
    }
    .stButton>button {
        background-color: #8F9E8B; /* สีเขียวใบไม้สไตล์ป่า Totoro */
        color: white;
        border-radius: 12px;
        border: none;
        padding: 8px 20px;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #72826E;
        transform: translateY(-2px);
    }
    .card-box {
        background-color: #F4EFEA;
        padding: 18px;
        border-radius: 16px;
        border-left: 5px solid #D9C5B2;
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 📊 3. ฟังก์ชันดึงคลังข้อสอบสไตล์ Business จาก BigQuery คลาวด์
# =========================================================
@st.cache_data(show_spinner=False)
def load_all_business_questions():
    table_id = "frm-ai-tutor.FRM_DATASET.questions"
    query = f"SELECT * FROM `{table_id}`"
    try:
        query_job = bq_client.query(query)
        rows = query_job.result()
        questions = []
        for row in rows:
            # ทำการแปลงข้อความ JSON ที่จัดเก็บในคลาวด์กลับมาเป็นโครงสร้าง Python
            options_dict = json.loads(row.options) if isinstance(row.options, str) else row.options
            vocab_list = json.loads(row.key_vocabulary) if isinstance(row.key_vocabulary, str) else row.key_vocabulary
            
            questions.append({
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
        return questions
    except Exception as e:
        st.error(f"ไม่สามารถเชื่อมต่อฐานข้อมูลหลักสูตรได้: {e}")
        return []

# =========================================================
# ⚙️ 4. บริหารกลไกตัวแปรระบบ (Session State Initialization)
# =========================================================
if "questions_pool" not in st.session_state:
    st.session_state.questions_pool = load_all_business_questions()
if "current_idx" not in st.session_state:
    st.session_state.current_idx = 0
if "user_choice" not in st.session_state:
    st.session_state.user_choice = None
if "is_submitted" not in st.session_state:
    st.session_state.is_submitted = False
if "my_flashcards" not in st.session_state:
    st.session_state.my_flashcards = []
if "ai_chat_history" not in st.session_state:
    st.session_state.ai_chat_history = []
if "score_tracker" not in st.session_state:
    st.session_state.score_tracker = 0

# =========================================================
# 🏛️ 5. เลย์เอาต์หน้าต่างหลักและการแสดงผลแอปพลิเคชัน
# =========================================================
st.title("🌿 FRM Part I - Ghibli Business Tutor 🌾")
st.caption("ยินดีต้อนรับคุณนาธานสู่มุมทบทวนความเสี่ยงสไตล์สถาบันการเงินจริง โฟกัส เป๊ะ และเงียบสงบ 🦦🛖")

# 🏆 แผงควบคุมด้านข้าง (Sidebar): บอร์ดสรุปคะแนนและคลังแฟลชการ์ดสะสม
with st.sidebar:
    st.header("🏆 เกียรติยศนักวิเคราะห์")
    st.metric("คะแนนสะสมความแม่นยำ", f"{st.session_state.score_tracker} ข้อ")
    
    # 🏅 กลไกปลดล็อกเกียรติยศ 3D Badge สไตล์กิบลิ
    st.subheader("🏅 ตราประทับที่ปลดล็อก")
    if st.session_state.score_tracker >= 1:
        st.markdown("🌰 **เมล็ดโอ๊ค Totoro** (นักวิเคราะห์ฝึกหัด)")
    if st.session_state.score_tracker >= 3:
        st.markdown("🔥 **เปลวไฟ Calcifer** (สูตรคำนวณทรงพลัง)")
    if st.session_state.score_tracker >= 5:
        st.markdown("🦦 **ราชาคาปิบาร่าออนเซ็น** (ปรมาจารย์ผู้บริหารความเสี่ยง)")
    if st.session_state.score_tracker == 0:
        st.caption("เริ่มตอบถูกครบเงื่อนไขเพื่อปลดล็อกตราประทับกิบลิ 3D จ้า...")
        
    st.markdown("---")
    st.header("🗂️ กล่องแฟลชการ์ดจดจำด่วน")
    if st.session_state.my_flashcards:
        for idx, card in enumerate(st.session_state.my_flashcards):
            st.info(f"📋 **ใบที่ {idx+1}**\n{card}")
    else:
        st.caption("ยังไม่มีการ์ดคำศัพท์หรือสูตรที่บันทึกไว้จ้า")

# ตรวจสอบว่ามีโจทย์พร้อมใช้งานในตารางคลาวด์หรือไม่
if not st.session_state.questions_pool:
    st.warning("⚙️ ขณะนี้ระบบคลังโจทย์สไตล์ Business บน BigQuery ว่างเปล่า พรุ่งนี้เวลาบ่ายสองอย่าลืมเปิดรัน pipeline.py เพื่อปั๊มโจทย์เข้าฐานข้อมูลนะจ้า!")
else:
    # ดึงข้อมูลโจทย์ข้อปัจจุบันขึ้นมาแจกแจง
    q = st.session_state.questions_pool[st.session_state.current_idx]
    
    # ส่วนหัวระบุพิกัดวิชาและระดับความยาก
    st.markdown(f"**📖 เล่มหลักสูตร:** {q['book']} | **🎯 หัวข้อทดสอบ:** {q['topic']} | ⚡ **ระดับ:** {q['difficulty']}")
    
    # 📝 พื้นที่แสดงเนื้อหาโจทย์ข้อสอบหลัก (Institutional Banking context)
    st.write(q['question_text'])
    
    # จัดแจงแปลงตัวเลือกข้อสอบออกเป็น Option Radio
    options_list = [
        f"A: {q['options'].get('A', '')}",
        f"B: {q['options'].get('B', '')}",
        f"C: {q['options'].get('C', '')}",
        f"D: {q['options'].get('D', '')}"
    ]
    
    selected_radio = st.radio("เลือกคำตอบที่ถูกต้องที่สุดตามหลักปฏิบัติการเงิน:", options_list, index=None, placeholder="กรุณาเลือกช้อยส์คำตอบที่นี่...")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🚀 ส่งตรวจคำตอบ", use_container_width=True) and selected_radio:
            st.session_state.user_choice = selected_radio[0] # ดึงเฉพาะตัวอักษรหน้าสุด A, B, C, D
            st.session_state.is_submitted = True
            
    with col_btn2:
        if st.button("⏭️ สุ่มข้อถัดไป", use_container_width=True):
            # รีเซ็ตสถานะตัวแปรเพื่อสลับไปข้อถัดไปแบบสุ่ม
            st.session_state.current_idx = random.randint(0, len(st.session_state.questions_pool) - 1)
            st.session_state.is_submitted = False
            st.session_state.user_choice = None
            st.session_state.ai_chat_history = []
            st.rerun()

    # แสดงแผงโพยคำเฉลยอย่างละเอียดเฉพาะเมื่อกดปุ่มตรวจคำตอบแล้วเท่านั้น
    if st.session_state.is_submitted:
        st.markdown("---")
        if st.session_state.user_choice == q['correct_option']:
            st.success(f"✨ มหัศจรรย์มากนาธาน! คำตอบของคุณถูกต้อง เฉลยคือข้อ {q['correct_option']} ครับจ้า!")
            # เพิ่มคะแนนเมื่อตอบถูกเป็นครั้งแรกในรอบนั้น
            if 'last_counted_id' not in st.session_state or st.session_state.last_counted_id != q['question_id']:
                st.session_state.score_tracker += 1
                st.session_state.last_counted_id = q['question_id']
        else:
            st.error(f"ลื่นล้มเล็กน้อยโฮมสเตย์กิบลิ! คำตอบที่เลือกคือ {st.session_state.user_choice} แต่คำตอบที่ถูกต้องตามหลักสูตรคือข้อ {q['correct_option']} จ้า")
            
        st.subheader("📖 Explanation (English)")
        st.write(q['explanation_en'])
        
        st.subheader("🇹🇭 คำอธิบายและเฉลยละเอียดภาษาไทย")
        st.write(q['explanation_th'])

    # =========================================================
    # 🏗️ 6. แท่นฟีเจอร์จัดเลย์เอาต์Persistent 3 กล่อง (กางรอตั้งแต่แรกเห็นโจทย์)
    # =========================================================
    st.markdown("---")
    st.subheader("🛠️ เครื่องมือช่วยคิดและวิเคราะห์ประจำข้อสอบ")
    
    tab_vocab, tab_flashcard, tab_ai = st.tabs([
        "📚 คำแปลศัพท์เทคนิคประจำข้อ (Vocabulary)", 
        "📝 จด Flashcard ด่วนเข้ากล่องความจำ", 
        "🧙‍♂️ แชทคุยถามคำถามสไตล์ AI Tutor"
    ])
    
    # กล่องที่ 1: ตารางคลังแปลคำศัพท์เฉพาะทางประจำข้อสอบ
    with tab_vocab:
        st.caption("💡 รวมศัพท์หรูและคำเฉพาะสไตล์สถาบันการเงินที่เจอในโจทย์ข้อนี้:")
        if q['key_vocabulary'] and isinstance(q['key_vocabulary'], list):
            for item in q['key_vocabulary']:
                st.markdown(f"🔹 **{item.get('word', '')}** : {item.get('translation', '')}")
        else:
            st.caption("ข้อนี้ไม่มีศัพท์เทคนิคยากเพิ่มเติมจ้า รันสมองได้อย่างลื่นไหล")

    # กล่องที่ 2: ระบบพิมพ์สรุปย่อแฟลชการ์ดคัดลอกสูตรได้ดั่งใจ
    with tab_flashcard:
        st.caption("✍️ คัดลอกข้อความสูตรคำนวณหรือ Note เด็ด ๆ ด้านบนมาแปะโยนเข้ากล่องสะสมเพื่อเปิดทบทวนได้ตลอดเวลา:")
        card_input = st.text_area("ข้อความบันทึกความจำสั้น:", placeholder="ตัวอย่าง: สูตร Bayes' Theorem คือ P(A|B) = [P(B|A)*P(A)] / P(B)", key="card_area")
        if st.button("💾 บันทึกการ์ดใบนี้ลงกล่องข้าง"):
            if card_input.strip():
                st.session_state.my_flashcards.append(card_input.strip())
                st.toast("บันทึกแฟลชการ์ดใบใหม่ขึ้นบอร์ดข้างเรียบร้อยแล้วจ้า! 🌰")
                st.rerun()

    # กล่องที่ 3: ช่องหน้าต่างแชท AI ติวเตอร์ปรึกษาข้อสงสัยเชิงลึกทางการเงิน
    with tab_ai:
        st.caption("🧙‍♂️ มีจุดไหนในโจทย์หรือคำอธิบายที่อ่านแล้วยังติดขัด คุยปรึกษากับที่ปรึกษาความเสี่ยงกิบลิได้เลยจ้า:")
        
        # แสดงบทสนทนาย้อนหลังภายในข้อนั้น
        for msg in st.session_state.ai_chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["text"])
                
        # กล่องรับข้อความพิมพ์คุย
        chat_input_text = st.chat_input("💬 พิมพ์คำถามสงสัยเกี่ยวกับคณิตศาสตร์หรือบริบทข้อนี้...")
        if chat_input_text:
            # พิมพ์ฝั่งผู้ใช้งานโชว์บนหน้าจอ
            st.session_state.ai_chat_history.append({"role": "user", "text": chat_input_text})
            
            # บรรจุบริบทโจทย์ส่งเข้าสมอง Gemini เพื่อให้ตอบคำถามได้ตรงจุดไม่หลุดประเด็น
            ai_context_prompt = f"""
            You are a helpful, warm Ghibli-themed FRM AI Tutor helping Nathan (a Financial Business Analyst). 
            He is looking at this question:
            Question: {q['question_text']}
            Options: {q['options']}
            Correct Answer: {q['correct_option']}
            Explanation EN: {q['explanation_en']}
            Explanation TH: {q['explanation_th']}
            
            Nathan's Question: {chat_input_text}
            
            Answer him concisely using professional financial jargon mixed with a very warm, supportive tone ("ครับจ้า", "นาธานครับ"). Keep it highly educational.
            """
            
            with st.spinner("AI กิบลิกำลังคำนวณสูตรและเรียบเรียงคำตอบสักครู่จ้า..."):
                try:
                    response = ai_client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=ai_context_prompt
                    )
                    st.session_state.ai_chat_history.append({"role": "model", "text": response.text})
                except Exception as chat_err:
                    st.session_state.ai_chat_history.append({"role": "model", "text": f"ขออภัยจ้านาธาน ระบบ API เกิดอาการสะดุดชั่วคราว: {chat_err}"})
            st.rerun()