# 🧠 ANTIGRAVITY MASTER PROJECT CONTEXT & HANDOVER MEMORY
**Last Updated**: 2026-10-05 16:30 (Asia/Bangkok)
**Project Owner**: @TOM (satochitom-stack)
**Active Repository**: `https://github.com/satochitom-stack/XAUUSD_Scalping_M5_Webapp`

> 📌 **คำสั่งสำหรับ AI / Antigravity ประจำเครื่องที่บ้าน (Home PC Antigravity)**:
> เมื่อผู้ใช้เปิดโปรเจกต์นี้บนเครื่องที่บ้าน ให้อ่านเอกสารนี้เป็นอันดับแรก จะเข้าใจบริบทและสถานะล่าสุดของระบบ 100% ทันทีโดยที่ผู้ใช้ไม่ต้องเล่าซ้ำ สามารถร่วมงาน ตรวจสอบบอท และพัฒนาต่อได้ทันที!

---

## 1. สถานะสถาปัตยกรรมปัจจุบัน (Current Architecture - Local MT5 Direct Mode)

เนื่องจากผู้ใช้หยุดเช่า VPS เพื่อประหยัดค่าใช้จ่าย ระบบจึงถูกปรับเปลี่ยนมารันบน **เครื่องคอมพิวเตอร์โดยตรง (Local PC Mode)**:

### 🤖 1. ระบบบอทเทรดทองคำอัตโนมัติ (Automated Scalping Bot)
* **รันอยู่ที่**: บนคอมพิวเตอร์ของผู้ใช้โดยตรง (Local Python Daemon Server)
* **พอร์ตบอท**: Exness Cent `#159415028` (`Exness-MT5Real20`)
* **MT5 Terminal Path**: `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`
* **Server Port**: `http://localhost:8000` (FastAPI + Uvicorn)
* **Access Token**: `GOLD_VIP_2026`
* **ตัวเปิดบอทอัตโนมัติ 1-Click**: ไฟล์ `START_BOT.bat` (มีคำสั่ง `git pull origin main` ซิงค์โค้ดอัตโนมัติก่อนรันบอทเสมอ)

### ✍️ 2. ระบบบันทึกการเทรดมือ (Manual Trading Journal - FXLOG PRO)
* **พอร์ตเทรดมือ**: Exness Cent `#257508244` (`Exness-MT5Real36`)
* **MT5 Terminal Path**: `C:\Users\Windows11\AppData\Local\Programs\MetaTrader 5 EXNESS 2\terminal64.exe`
* **เว็บแอพบันทึก**: [https://trade-journal-1.vercel.app/](https://trade-journal-1.vercel.app/)
* **Bridge Port แยกอิสระ**: ย้ายไปที่ Port `8001` (ไฟล์ `run_fxlog_bridge.py`) เพื่อป้องกันไม่ให้ทับซ้อนกับ Webapp หลัก Port `8000`

---

## 2. การแยกพอร์ตถาวร (Account Isolation & Drift Prevention)
* **ปัญหาที่เคยพบ**: ฟังก์ชันดึง Journal เคยสลับ MT5 ไปที่พอร์ตเทรดมือ `#257508244` ทำให้บอทเข้าใจผิดว่าติดเป้า Daily Target และเกือบยิงออเดอร์ผิดพอร์ต
* **วิธีแก้ที่ทำเสร็จแล้ว**:
  1. ใน `mt5_connector.py`: ล็อก `self.target_account = 159415028` ถาวร ใน `ensure_connected()` ถ้าตรวจพบการหลุดไปพอร์ตอื่น จะ Disconnect แล้ว Re-attach กลับมาที่ `#159415028` ทันที
  2. ใน `strategy_analytics.py`: เพิ่มบล็อก `finally:` ให้สลับกลับมาที่ MT5 Terminal ของบอทเสมอ และตัดเงื่อนไข `or True` ออกทั้งหมด
  3. ใน `account_manager.py`: เมธอด `to_dict()` รายงาน Login ของบอทตามพอร์ตที่คอนฟิกไว้เสมอ

---

## 3. ระบบความปลอดภัยทองคำยุคใหม่ (Gold New Normal Rules)
ปรับปรุงรับมือทองคำผันผวนสูง (วิ่งวันละ $50-$150 และชอบสะบัดกินไส้):
1. **Liquidity Sweep Zones (`get_market_liquidity_levels`)**: บล็อกการ Buy จ่อใต้แนว PDH/Asian High/EQH และบล็อกการ Sell เหนือแนว PDL/Asian Low/EQL
2. **Strict Rejection Confirmation**: แท่งเทียนสัญญาณต้องมีไส้ฝั่งตรงข้าม $\le 30-40\%$ และมีเนื้อแท่งเทียน Solid Body $\ge 35\%$ เพื่อกรองแท่ง False Breakout
3. **Dynamic ATR SL Floor**: ฐาน Stop Loss ลอยตัวตามความผันผวน $\text{SL Floor} = \max(2.50, \min(5.00, 0.8 \times \text{ATR}))$

---

## 4. อัปเกรดระบบด้วย MTRADERS ATR Trading Framework
ผสานหลักการ **ATR Trading 11 ข้อ** ลงใน `bot_engine.py`:
1. **Dynamic ATR SL Buffer (ข้อ 4)**:
   - เปลี่ยนจาก Buffer คงที่ ($0.30) เป็น $\text{SL Buffer} = \max(0.40, \min(1.25, 0.25 \times \text{ATR}))$
   - ช่วยให้เซตอัพ Swing เช่น `EW_WAVE3_BREAKER` และ `PULLBACK_DR_EKK` ไม่โดนสะบัดกิน SL ก่อนวิ่งถูกทาง
2. **ATR Overextension Guard (ข้อ 2 & 6)**:
   - ถ้าราคาพุ่งห่างจาก EMA50 เกิน $2.0 \times \text{ATR}$ บอทจะบล็อกการ Buy/Sell ปลายคลื่นทันที เพื่อไม่ให้ติดดอย/ติดเหว
3. **ATR TP Feasibility Clamp (ข้อ 5)**:
   - แก้ปัญหากราฟไปไม่ถึง TP แล้วย้อนกลับมากิน Break-Even โดยถ้าเป้า TP ไกลเกิน $2.5 \times \text{ATR}$ บอทจะ Clamp ระยะ TP ลงมาในระยะที่แตะถึงได้จริงในรอบ M5 นั้น
4. **Dynamic Pyramiding Step (ข้อ 8)**:
   - กำหนดระยะเพิ่มไม้รันเทรนด์ขั้นต่ำที่ $1.0 \times \text{ATR}$

---

## 5. สถานะการทดสอบ (Test Verification)
* **Unit Tests ทั้งหมด**: `109 / 109 Passed 100%` (`python -m pytest tests/ -v`)
* ครอบคลุม: Setup Triggers, Risk Isolation, ATR Rules, Account Switching, Trailing, Pyramiding, และ Benchmark Comparison

---

## 6. คำสั่งสำหรับเปิดงานที่เครื่องที่บ้าน (Prompt for Home Antigravity)

เมื่อคุณเปิด Antigravity บนเครื่องที่บ้าน ให้ก๊อปปี้ข้อความนี้ส่งให้ AI ได้เลย:

```text
สวัสดีครับ ผมเปิดโปรเจกต์ XAUUSD_Scalping_M5_Webapp ที่เครื่องบ้านแล้ว
ช่วยอ่านไฟล์ PROJECT_CONTEXT_HANDOVER.md และตรวจสอบ git pull ล่าสุด
จากนั้นตรวจสอบสถานะบอทและ MT5 บัญชี 159415028 ให้ทีครับ ว่าพร้อมรันหรือไม่
```
