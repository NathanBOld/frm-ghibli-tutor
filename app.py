# ... (ส่วนบนของโค้ดให้คงเดิมไว้ จนถึงช่วง Sidebar ส่วน Flashcard) ...

    st.markdown("---")
    # 🛠️ [FIXED] แก้ไขกลไกการเซฟและล้างค่าช่องข้อความ ไม่ให้ชนกับ Streamlit Widget State
    st.header("✨ สร้าง Flashcard ด่วน")
    
    # 1. ใช้ form เพื่อจัดการ state ของ widget ให้จบในตัวเดียว
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
                # clear_on_submit=True จะเคลียร์ค่าให้เองอัตโนมัติ ไม่ต้องสั่ง st.session_state
            else:
                st.error("กรุณากรอกให้ครบทั้งหน้าและหลังจ้า")

# ... (ส่วนล่างของโค้ดให้คงเดิมไว้) ...