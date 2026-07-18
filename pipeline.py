import os
import json
import time
import io
import random
from pydantic import BaseModel
from google import genai
from google.genai import types
from google.cloud import bigquery

# 🔒 1. ดึงกุญแจความลับผ่านระบบ Streamlit Secrets 
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# ☁️ ระบบสลับท่อเชื่อมต่ออัจฉริยะ (ใช้งานได้ทั้งบนคอมพิวเตอร์เครื่องตัวเอง และบนคลาวด์สาธารณะ)
if "GCP_JSON_TEXT" in st.secrets:
    # หากรันบนคลาวด์ ให้ดึงเนื้อหา JSON จากกล่องความลับมาสร้างไฟล์ชั่วคราวในเซิร์ฟเวอร์
    with open("frm-ai-tutor-1cef93cd880b.json", "w", encoding="utf-8") as f:
        f.write(st.secrets["GCP_JSON_TEXT"])

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "frm-ai-tutor-1cef93cd880b.json"

bq_client = bigquery.Client()
ai_client = genai.Client(api_key=GEMINI_API_KEY)
# =========================================================
# 🏛️ โครงสร้าง Pydantic สำหรับล็อกรูปแบบข้อมูล AI
# =========================================================
class VocabItem(BaseModel):
    word: str
    translation: str

class FRMQuestionSchema(BaseModel):
    question_text: str
    options_A: str
    options_B: str
    options_C: str
    options_D: str
    correct_option: str 
    explanation_en: str
    explanation_th: str
    key_vocabulary: list[VocabItem]

class ValidationSchema(BaseModel):
    status: str  
    reason: str  

# =========================================================
# 📂 ผังหลักสูตร FRM Part I กระจายน้ำหนักครบ 4 เล่มเพื่อความหลากหลาย
# =========================================================
FRM_CURRICULUM = [
    # Book 1: Foundations of Risk Management
    {"book": "Foundations of Risk Management", "topic": "Corporate Risk Governance & ERM"},
    {"book": "Foundations of Risk Management", "topic": "CAPM & Arbitrage Pricing Theory (APT)"},
    {"book": "Foundations of Risk Management", "topic": "Risk Management Failures & Financial Disasters"},
    {"book": "Foundations of Risk Management", "topic": "GARP Code of Conduct & Ethics"},
    
    # Book 2: Quantitative Analysis
    {"book": "Quantitative Analysis", "topic": "Bayes' Theorem & Conditional Probability"},
    {"book": "Quantitative Analysis", "topic": "Linear Regression & OLS Diagnostics"},
    {"book": "Quantitative Analysis", "topic": "Time Series Forecasting & ARMA Models"},
    {"book": "Quantitative Analysis", "topic": "Simulation Methods & Monte Carlo Techniques"},
    
    # Book 3: Financial Markets and Products
    {"book": "Financial Markets and Products", "topic": "Options Hedging Strategies & Greeks"},
    {"book": "Financial Markets and Products", "topic": "Futures and Forwards Pricing Mechanics"},
    {"book": "Financial Markets and Products", "topic": "Interest Rate Swaps & Currency Swaps"},
    {"book": "Financial Markets and Products", "topic": "Fixed Income Bonds & Foreign Exchange Risk"},
    
    # Book 4: Valuation and Risk Models
    {"book": "Valuation and Risk Models", "topic": "Value at Risk (VaR) & Expected Shortfall (ES)"},
    {"book": "Valuation and Risk Models", "topic": "Stress Testing & Scenario Analysis"},
    {"book": "Valuation and Risk Models", "topic": "Option Valuation via Binomial Trees & Black-Scholes"},
    {"book": "Valuation and Risk Models", "topic": "Country Risk & Operational Risk Frameworks"}
]

# 📊 ฟังก์ชันตรวจสอบจำนวนข้อสอบปัจจุบันในฐานข้อมูลคลาวด์
def get_current_question_count():
    table_id = "frm-ai-tutor.FRM_DATASET.questions"
    query = f"SELECT COUNT(*) as total FROM `{table_id}`"
    try:
        query_job = bq_client.query(query)
        results = query_job.result()
        for row in results:
            return row.total
    except Exception:
        return 0 

# 🧠 ฟังก์ชันผลิตโจทย์ประยุกต์เชิงธุรกิจระดับสูง
def generate_business_frm_question(book_name, topic_name):
    generation_prompt = f"""
    You are an expert Senior Risk Management Practitioner and an elite GARP FRM Exam Writer.
    Generate ONE highly realistic, exam-quality multiple-choice question for the FRM Part I Curriculum:
    - Book: {book_name}
    - Topic: {topic_name}

    CRITICAL INSTRUCTIONS:
    1. USE INSTITUTIONAL BUSINESS STYLE: Frame around credit risk committee reviews, portfolio adjustments, or banking events.
    2. ABSOLUTE MATHEMATICAL PRECISION: Double-check all numbers. The final division in your math MUST EXACTLY equal the designated correct option. Do NOT hallucinate or alter rounding steps to justify a wrong option.
    3. CONCISE EXPLANATIONS: Keep explanations brief, highly professional, and direct to the point.
    4. COMPLETE THAI TRANSLATION: Ensure the explanation_th is punchy, precise, and completely finishes its thought/sentence cleanly without cutting off mid-sentence.
    """
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=generation_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FRMQuestionSchema,
                temperature=0.75 
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        return str(e) 

# 🛡️ AI ตรวจทานความถูกต้องระดับมหาโหด (ขจัด Math Gaslighting)
def validate_question_with_ai(question_data):
    review_prompt = f"""
    You are an uncompromising, ultra-strict Senior FRM Mathematics Auditor. Your sole job is to catch mathematical hallucinations, bad rounding, and "math gaslighting".

    QUESTION TO AUDIT:
    - Text: {question_data['question_text']}
    - Options: A: {question_data['options_A']}, B: {question_data['options_B']}, C: {question_data['options_C']}, D: {question_data['options_D']}
    - Correct Option Designated: {question_data['correct_option']}
    - English Explanation: {question_data['explanation_en']}
    - Thai Explanation: {question_data['explanation_th']}

    CRITERIA:
    If there is even a 0.01% math error, forced rounding excuse, or truncated/incomplete Thai sentence, you MUST set status to 'REJECTED' and explain the exact error. Only approve ('APPROVED') if it is absolute perfection.
    """
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=review_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ValidationSchema,
                temperature=0.0 
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        return {"status": "REJECTED", "reason": "System validation error"}

# 📤 อัปโหลดข้อมูลรายข้อขึ้นฐานข้อมูลคลาวด์ต่อท้ายตาราง (WRITE_APPEND)
def upload_question_to_bq(clean_data):
    table_id = "frm-ai-tutor.FRM_DATASET.questions"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND 
    )
    try:
        ndjson_line = json.dumps(clean_data, ensure_ascii=False) + "\n"
        data_stream = io.BytesIO(ndjson_line.encode('utf-8'))
        load_job = bq_client.load_table_from_file(data_stream, table_id, job_config=job_config)
        load_job.result()
        return True
    except Exception as e:
        print(f"❌ อัปโหลดลงคลาวด์ล้มเหลว: {e}")
        return False

# =========================================================
# ⚙️ แท่นควบคุมลูปการทำงานหลัก (Incremental 500 Target)
# =========================================================
if __name__ == "__main__":
    print("🎬 เริ่มเปิดระบบแท่นเครื่องจักรผลิตข้อสอบอัตโนมัติ (Dual-AI Engine)...")
    
    TARGET_TOTAL = 500
    current_existing = get_current_question_count()
    print(f"📊 ตรวจพบคลังข้อสอบปัจจุบันบน BigQuery: {current_existing} / {TARGET_TOTAL} ข้อ")
    
    needed_questions = TARGET_TOTAL - current_existing
    
    if needed_questions <= 0:
        print("✨ ยินดีด้วยครับ! คลังข้อสอบของคุณสะสมครบเป้าหมาย 500 ข้อเรียบร้อยบริบูรณ์แล้วจ้า!")
    else:
        print(f"🎯 ระบบจะทำการผลิตโจทย์กระจายหัวข้อเพิ่มอีก: {needed_questions} ข้อ เพื่อให้ครบเป้าหมาย")
        print("----------------------------------------------------------------------")
        
        success_count = 0
        loop_attempts = 0
        max_loop_limits = needed_questions * 3 
        
        while success_count < needed_questions and loop_attempts < max_loop_limits:
            loop_attempts += 1
            
            target_lesson = random.choice(FRM_CURRICULUM)
            print(f"\n🛸 [คัดเลือกบทเรียน] วิชา: {target_lesson['book']} | หัวข้อ: {target_lesson['topic']}")
            print(f"⏳ กำลังผลิตข้อสอบข้อที่ {current_existing + success_count + 1} จากทั้งหมด {TARGET_TOTAL} ข้อ...")
            
            raw_q = generate_business_frm_question(target_lesson['book'], target_lesson['topic'])
            
            if isinstance(raw_q, str):
                if "Requests per day" in raw_q or "daily" in raw_q.lower():
                    print("\n🛑 [Daily Quota Exhausted] บัญชีฟรีของคุณใช้งานครบโควตารายวันของวันนี้แล้วจ้า!")
                    print("💡 ความคืบหน้าทั้งหมดถูกเซฟลงคลาวด์อย่างปลอดภัยแล้ว พรุ่งนี้ค่อยกลับมากดรันต่อจากจุดนี้ได้เลยครับ")
                    break
                
                elif "429" in raw_q or "RESOURCE_EXHAUSTED" in raw_q:
                    print(f"\n⚠️ [Rate Limit 429] ชนเพดานปริมาณคำรายนาที (TPM) สั่งนอนพักผ่อนล้างโควตา 65 วินาที...")
                    time.sleep(65.0)
                    continue
                
                else:
                    print(f"❌ เจอการแจ้งเตือนปฏิเสธจากระะบบ API: {raw_q}")
                    print("⏳ ข้ามรอบนี้เพื่อความปลอดภัย และเตรียมสุ่มหัวข้อใหม่ในรอบถัดไป...")
                    time.sleep(8.0)
                    continue
                    
            if not raw_q:
                print("⚠️ ข้อมูลส่งมาเป็นค่าว่างเปล่า กำลังข้ามไปรอบถัดไป...")
                time.sleep(5.0)
                continue
                
            check_res = validate_question_with_ai(raw_q)
            
            if check_res["status"] == "APPROVED":
                print(f"✅ ตรวจสอบผ่านเกณฑ์สมบูรณ์แบบ: {check_res['reason']}")
                
                clean_insert_row = {
                    "question_id": f"Q_BIZ_{int(time.time())}_{random.randint(100,999)}",
                    "source": "Gemini Business Certified",
                    "book": target_lesson['book'],
                    "topic": target_lesson['topic'],
                    "difficulty": random.choice(["Medium", "Hard"]),
                    "question_text": raw_q["question_text"],
                    "options": json.dumps({
                        "A": raw_q["options_A"],
                        "B": raw_q["options_B"],
                        "C": raw_q["options_C"],
                        "D": raw_q["options_D"]
                    }, ensure_ascii=False),
                    "correct_option": raw_q["correct_option"],
                    "explanation_en": raw_q["explanation_en"],
                    "explanation_th": raw_q["explanation_th"],
                    "key_vocabulary": json.dumps(raw_q["key_vocabulary"], ensure_ascii=False)
                }
                
                if upload_question_to_bq(clean_insert_row):
                    success_count += 1
                    print(f"✨ บันทึกข้อที่ {current_existing + success_count} ขึ้น BigQuery คลาวด์สำเร็จ!")
            else:
                print(f"🚨 ข้อสอบถูกคัดออกเนื่องจากตัวเลขไม่เป๊ะหรือไทยตัดจบ: {check_res['reason']}")
                
            # ⏱️ [จุดอัปเกรดสำคัญ] ขยับ Pacing ก้าวเดินให้เนียนขึ้นเป็น 14.0 วินาที เพื่อกระจายตัว Token ไม่ให้กระจุกตัวหนาแน่นเกินไป
            time.sleep(14.0)
            
        print(f"\n🏁 [ปิดสเตชั่นการทำงาน] จบรอบนี้ผลิตโจทย์สไตล์ Business เพิ่มได้สำเร็จ: {success_count} ข้อ")
        print(f"📊 ยอดรวมสะสมปัจจุบันบนระบบคลาวด์: {get_current_question_count()} / {TARGET_TOTAL} ข้อ")