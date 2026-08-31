# 🌐 XAUUSD Scalping M5 Secret System - Python WebApp & Bot Runner

Web Application สำหรับควบคุมและรันบอทเทรดทองคำ (XAUUSD M5) พัฒนาด้วย **Python (FastAPI)** เชื่อมต่อกับ **MetaTrader 5 (MT5)** พร้อมระบบรักษาความปลอดภัยด้วย **Access Token** และหน้าเว็บ Dashboard สดระดับพรีเมียม

---

## ✨ ฟีเจอร์หลัก (Key Features)

1. **🔐 Token-Protected Access**: ระบบล็อกหน้าเว็บด้วย Token / License Key ก่อนเข้าใช้งาน ป้องกันการเข้าถึงโดยไม่ได้รับอนุญาต (Default Key: `GOLD_VIP_2026`)
2. **⚡ Real-Time Live Dashboard**:
   - รายงานสถานะบอท: `RUNNING`, `STOPPED`, `PAUSED`
   - ตรวจจับแนวโน้มและวิเคราะห์ความชัน EMA 50 & EMA 150 แบบสดๆ
   - อัปเดตราคา Gold (Ask/Bid), Spread, ยอดเงิน Balance, Equity, และ Floating Profit/Loss
   - แสดงสถิติการแพ้ติดกัน (Consecutive Losses) และสถานะลดขนาด Lot
3. **🎮 Bot Controls**:
   - ปุ่ม `START BOT` / `STOP BOT` สั่งงานบอทได้ทันทีผ่านหน้าเว็บ
   - ปุ่ม `Emergency Close All` ปิดทุกออเดอร์ทันทีเมื่อเกิดเหตุฉุกเฉิน
   - ปุ่มปิดออเดอร์รายไม้ (Manual Close)
4. **⚙️ Live Strategy Config**: ปรับตั้งค่า Risk %, Take Profit, Stop Loss, EMA Period, Spread Filter ได้จากหน้าเว็บโดยไม่ต้องแก้โค้ด
5. **📜 Live Terminal Log Feed**: แสดงประวัติสัญญาณ, การเปิด-ปิดออเดอร์ และแจ้งเตือนของบอทแบบเรียลไทม์
6. **🔄 Smart Simulation Mode**: หากยังไม่ได้เปิดโปรแกรม MT5 บอทจะเข้าสู่โหมดจำลอง (Paper Trading) อัตโนมัติ เพื่อให้คุณสามารถทดสอบหน้าเว็บและระบบได้อย่างราบรื่น

---

## 🚀 วิธีการติดตั้งและเริ่มใช้งาน (Getting Started)

### ขั้นตอนที่ 1: ติดตั้ง Dependencies
เปิด Terminal หรือ Command Prompt ในโฟลเดอร์นี้ แล้วรันคำสั่ง:
```bash
pip install -r requirements.txt
```
*(หรือดับเบิลคลิกไฟล์ `run_webapp.bat`)*

### ขั้นตอนที่ 2: เริ่มต้นรัน WebApp
รันคำสั่ง:
```bash
python run_webapp.py
```
*(หรือคลิกเปิดไฟล์ `run_webapp.bat`)*

ระบบจะเปิดหน้าต่างเบราว์เซอร์ไปยัง `http://127.0.0.1:8000` โดยอัตโนมัติ

---

## 🔑 การเข้าสู่ระบบด้วย Access Token

เมื่อเปิดหน้าเว็บขึ้นมา จะพบหน้าต่างล็อกอิน ให้กรอก Access Token:
- **Default Token**: `GOLD_VIP_2026`
- หรือกดปุ่ม **"ใช้งาน"** เพื่อกรอกให้อัตโนมัติ แล้วกด **"ปลดล็อกเข้าสู่ระบบ"**

> 💡 **การเพิ่มหรือเปลี่ยน Token**: คุณสามารถเพิ่ม Token ใหม่ได้ในไฟล์ `config.json` ในส่วน `"access_tokens": ["YOUR_NEW_TOKEN_HERE"]`

---

## ⚙️ การเชื่อมต่อกับ MetaTrader 5 (Live Trading)
1. เปิดโปรแกรม **MetaTrader 5 (MT5)** บนเครื่องคอมพิวเตอร์ของคุณ
2. เข้าสู่ระบบบัญชีเทรดของโบรกเกอร์ และเปิดกราฟ **XAUUSD**
3. ไปที่เมนู `Tools` -> `Options` -> แท็บ `Expert Advisors` -> ติ๊กถูกที่ **"Allow Algo Trading"**
4. ใน WebApp เมื่อรัน `python run_webapp.py` บอทจะตรวจจับ MT5 และเชื่อมต่อเพื่อส่งคำสั่งเทรดจริงโดยอัตโนมัติ

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)
```
XAUUSD_Scalping_M5_Webapp/
├── main.py              # FastAPI Web Server & Token Auth API
├── bot_engine.py        # กลยุทธ์ Scalping M5 Secret System ใน Python
├── mt5_connector.py     # ตัวเชื่อมต่อ MT5 API & Simulation Engine
├── config.json          # ไฟล์ตั้งค่า Token, MT5, และกลยุทธ์
├── requirements.txt     # ไลบรารี Python ที่ต้องใช้
├── run_webapp.py        # ตัวเปิดเซิร์ฟเวอร์และเปิดเบราว์เซอร์อัตโนมัติ
├── run_webapp.bat       # ไฟล์คลิกรันสำหรับ Windows
├── templates/
│   └── index.html       # หน้าเว็บ Dashboard (Dark Mode / Tailwind CSS)
└── README_WEBAPP.md     # เอกสารคู่มือการใช้งาน
```
