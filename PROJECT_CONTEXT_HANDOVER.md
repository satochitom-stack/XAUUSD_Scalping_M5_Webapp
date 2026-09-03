# 🧠 ANTIGRAVITY MASTER PROJECT CONTEXT & HANDOVER MEMORY
**Last Updated**: 2026-09-04 06:55 (Asia/Bangkok)
**Project Owner**: @TOM (satochitom-stack)

> 📌 **คำสั่งสำหรับ AI / Antigravity บนเครื่องอื่น (เช่น เครื่องที่ทำงาน)**:
> เมื่อผู้ใช้เปิดโปรเจกต์นี้บนเครื่องทำงาน ให้อ่านเอกสารนี้เป็นอันดับแรก จะเข้าใจบริบททั้งหมด 100% ทันทีโดยที่ผู้ใช้ไม่ต้องอธิบายซ้ำ สามารถคุยงานและพัฒนาระบบต่อได้อย่างไร้รอยต่อ!

---

## 1. ภาพรวมระบบ (System Architecture Overview)
ระบบถูกแยกออกเป็น **2 โลกที่ทำงานอิสระจากกันอย่างเด็ดขาด** เพื่อความปลอดภัยของพอร์ต:

### โลกที่ 1: บอทเทรดทองคำอัตโนมัติ (Automated Scalping Bot)
* **รันอยู่ที่**: บน **Cloud VPS** (`139.180.157.124:12308`, FastAPI port `8000`)
* **บัญชี MT5 บอท**: Exness Cent `#159415028` (`Exness-MT5Real20`)
* **เว็บแอพแดชบอร์ดบอท**: [https://bot-intelligence-hub.vercel.app/](https://bot-intelligence-hub.vercel.app/)
  * เชื่อมต่อดึงข้อมูลสดผ่าน Vercel Proxy (`/api/bot-proxy`) ไปที่ VPS IP `139.180.157.124:8000`
  * Secret Access Token: `GOLD_VIP_2026`
* **Repository**: `https://github.com/satochitom-stack/XAUUSD_Scalping_M5_Webapp` (Public) และ `bot-intelligence-hub` (Private)

### โลกที่ 2: สมุดบันทึกการเทรดมือ (Manual Trading Journal - FXLOG PRO)
* **รันอยู่ที่**: บน **เครื่องคอมพิวเตอร์ของคุณ @TOM** (เครื่องที่บ้าน / เครื่องที่ทำงาน)
* **บัญชี MT5 เทรดมือ**: Exness Cent `#257508244` (`Exness-MT5Real36`)
* **เว็บแอพบันทึกการเทรด**: [https://trade-journal-1.vercel.app/](https://trade-journal-1.vercel.app/)
  * ดึงประวัติไม้ปิด (`/api/journal/closed_trades`) และไม้วิ่งสด (`/api/journal/open_positions`) ผ่าน `http://127.0.0.1:8000`
  * **ตัวเชื่อมในเครื่อง**: ไฟล์ `run_fxlog_bridge.py` / `run_fxlog_bridge.bat` 
  * **ความปลอดภัย**: เป็น **Read-Only Bridge** เท่านั้น (ไม่มีระบบบอท ไม่มีโค้ดส่งออเดอร์เด็ดขาด ปลอดภัยต่อพอร์ตเทรดมือ 100%)
* **Repository**: `https://github.com/satochitom-stack/fxlog-pro-v1` (Private)

---

## 2. กฎการบริหารความเสี่ยง & รูปแบบการเทรด (Risk Architecture)
1. **คุมความเสี่ยงคงที่ 1.0% ทุกเซตอัพ (Strict 1.0% Risk Per Setup)**:
   - คำนวณ Lot จากระยะ Stop Loss จริง โดยจำกัดความเสียหายสูงสุดไม่เกิน 1% ของ Equity ต่อไม้
2. **เซตอัพละ 1 ไม้เพียว ๆ (Single Position Execution)**:
   - ยกเลิกการแยกไม้ Pos1/Pos2 ห้ามออกไม้ซ้อนในเซตอัพเดิมจนกว่าไม้นั้นจะปิด เพื่อเก็บสถิติ Benchmark ที่สะอาดแม่นยำ
3. **เปิดพร้อมกันได้หลายเซตอัพ (Multi-Setup Concurrency)**:
   - แต่ละเซตอัพมี Magic Number เฉพาะตัว หากเซตอัพต่างกันเข้าเงื่อนไขพร้อมกัน สามารถถือออเดอร์พร้อมกันได้
4. **Break-Even Lock ที่ 1.0R**:
   - เมื่อไม้ใดวิ่งถูกทางถึง 1 เท่าของความเสี่ยง (1.0R) บอทจะขยับ SL มาดักกำไรหน้าทุน (+0.30 USD) อัตโนมัติทันที

---

## 3. รายละเอียดจุด Stop Loss (SL) ที่ปรับจูนแล้วสำหรับทองคำ (XAUUSD)
เพื่อป้องกันปัญหาโดนไส้เทียนสะบัดกิน SL ก่อนวิ่งถูกทาง ได้ปรับจูนระยะปลอดภัยไว้ดังนี้:

| เซตอัพ (Setup) | Timeframe | Magic Base | ระยะ Min - Max SL ปลอดภัย | อัตราส่วน R:R | พฤติกรรมเฉพาะ |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Captain SMC Signal V1.2** | M5 | 555880 | **380 – 650 จุด ($3.80 – $6.50)** | 1:1.8 | กรอง Volume $\ge 0.95x$ avg + Bar Lock |
| **TKT SMC Gold Pro v8.0** | M15 | 555810 | **500 – 850 จุด ($5.00 – $8.50)** | 1:1.8 | Order Block M15 + Bar Lock แท่ง M15 |
| **EMA 50 + 3 Candles (H1)** | H1 | 555850 | **450 – 800 จุด ($4.50 – $8.00)** | 1:2.0 | เทรดตามแนวรับ/ต้านเทรนด์ใหญ่ H1 |
| **Asian Range Sniper** | M5 | 555820 | **280 – 500 จุด ($2.80 – $5.00)** | 1:1.5 | Mean Reversion (07:00 - 14:00 น.) |
| **Flash Micro-Scalper** | M5 | 555800 | **280 – 450 จุด ($2.80 – $4.50)** | 1:1.5 | กรองเนื้อเทียน $\ge 35\%$ + EMA 9>21>50 |
| **M1 Sniper Confirmation** | M1 | 555870 | **250 – 450 จุด ($2.50 – $4.50)** | 1:2.5 | เข้าจังหวะคมกริบ M1 BOS ในโซน HTF |
| **News Momentum Expansion** | M5 | 555890 | **350 – 700 จุด ($3.50 – $7.00)** | 1:1.8 | ดักแท่งเนื้อแน่น Breakout ข่าวแรง |
| **EMA Ribbon + RSI Momentum** | M5 | 555860 | **350 – 700 จุด ($3.50 – $7.00)** | 1:1.8 | เทรดตามแถบ Ribbon EMA 20/50/100/200 |

---

## 4. บันทึกการแก้ไข UI ล่าสุดบน `bot-intelligence-hub`
1. **แก้ปัญหา M1 Sniper ไม่นับสถิติในหน้าแรก**:
   - ใน `src/App.tsx` ปรับลำดับการจำแนกให้ตรวจจับ `m1` ก่อน `asian` และตัดคำกว้าง ๆ `sniper` ออกจาก Asian Range ทำให้ไม้ของ M1 กลับมาแสดงสถิติถูกต้อง
2. **แก้ปัญหาชื่อป้ายสลับระหว่าง TKT SMC กับ Captain SMC**:
   - ใน `src/components/ActivePositionsTable.tsx` แยกการตรวจจับ Magic `555811` (`Gold_TKT_SMC_`) ให้ขึ้นป้ายสีม่วง **TKT SMC Gold Pro v8.0** ก่อนที่จะตรวจจับ Captain SMC

---

## 5. คู่มือปฏิบัติงานสำหรับเครื่องที่ทำงาน (Work Machine Guide)
เมื่อผู้ใช้ @TOM ไปนั่งที่เครื่องทำงาน:
1. **การดูและคุมบอทอัตโนมัติ**:
   - ไม่ต้องทำอะไรกับเครื่องที่ทำงาน เพราะบอทรันอยู่บน VPS แล้ว
   - เปิดดูผลงานได้ที่ [https://bot-intelligence-hub.vercel.app/](https://bot-intelligence-hub.vercel.app/)
2. **การเทรดมือและบันทึกเข้า FXLOG PRO**:
   - เปิด MT5 บัญชีเทรดมือ `#257508244`
   - รันตัวเชื่อม `run_fxlog_bridge.bat` บนเครื่องที่ทำงาน เพื่อเปิดพอร์ต `8000` (Read-Only)
   - เปิด [https://trade-journal-1.vercel.app/](https://trade-journal-1.vercel.app/) แล้วกดปุ่มดึงไม้ปิด หรือไม้วิ่งอยู่ได้ทันที
3. **คำสั่งสั่งรันต่อสำหรับ AI บนเครื่องทำงาน**:
   > *"ช่วยอ่านไฟล์ `PROJECT_CONTEXT_HANDOVER.md` แล้วสรุปสถานะปัจจุบันให้ฟังหน่อย"*
   AI จะเข้าใจและทำงานต่อได้ทันทีโดยไม่มีสะดุด!
