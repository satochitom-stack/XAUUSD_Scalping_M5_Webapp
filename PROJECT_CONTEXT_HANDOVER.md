# 🧠 ANTIGRAVITY MASTER PROJECT CONTEXT & HANDOVER MEMORY
**Last Updated**: 2026-09-07 (Asia/Bangkok)
**Project Owner**: @TOM (satochitom-stack)

> 📌 **คำสั่งสำหรับ AI / Antigravity บนเครื่องอื่น (เช่น เครื่องที่บ้าน / โน๊ตบุค)**:
> เมื่อผู้ใช้เปิดโปรเจกต์นี้บนเครื่องที่บ้าน ให้อ่านเอกสารนี้เป็นอันดับแรก จะเข้าใจบริบททั้งหมด 100% ทันทีโดยที่ผู้ใช้ไม่ต้องอธิบายซ้ำ สามารถคุยงาน วิเคราะห์ผล และพัฒนาระบบต่อได้อย่างไร้รอยต่อ!

---

## 1. ภาพรวมระบบ (System Architecture Overview)
ระบบถูกแยกออกเป็น **2 โลกที่ทำงานอิสระจากกันอย่างเด็ดขาด** เพื่อความปลอดภัยของพอร์ต:

### โลกที่ 1: บอทเทรดทองคำอัตโนมัติ (Automated Scalping Bot)
* **รันอยู่ที่**: บน **Cloud VPS สิงคโปร์** (`139.180.157.124:12308`, FastAPI port `8000`)
* **บัญชี MT5 บอท**: Exness Cent `#159415028` (`Exness-MT5Real20`)
* **เว็บแอพแดชบอร์ดบอท**: [https://bot-intelligence-hub.vercel.app/](https://bot-intelligence-hub.vercel.app/)
  * เชื่อมต่อดึงข้อมูลสดผ่าน Vercel Proxy (`/api/bot-proxy`) ไปที่ VPS IP `139.180.157.124:8000`
  * Secret Access Token: `GOLD_VIP_2026`
* **Repositories**: 
  - Backend/VPS: `https://github.com/satochitom-stack/XAUUSD_Scalping_M5_Webapp`
  - Frontend Dashboard: `https://github.com/satochitom-stack/bot-intelligence-hub`

### โลกที่ 2: สมุดบันทึกการเทรดมือ (Manual Trading Journal - FXLOG PRO)
* **รันอยู่ที่**: บน **เครื่องคอมพิวเตอร์ของคุณ @TOM** (เครื่องที่บ้าน / เครื่องที่ทำงาน)
* **บัญชี MT5 เทรดมือ**: Exness Cent `#257508244` (`Exness-MT5Real36`)
* **เว็บแอพบันทึกการเทรด**: [https://trade-journal-1.vercel.app/](https://trade-journal-1.vercel.app/)
  * ดึงประวัติไม้ปิด (`/api/journal/closed_trades`) และไม้วิ่งสด (`/api/journal/open_positions`) ผ่าน `http://127.0.0.1:8000`
  * **ตัวเชื่อมในเครื่อง**: ไฟล์ `run_fxlog_bridge.py` / `run_fxlog_bridge.bat` (อยู่ใน `XAUUSD_Scalping_M5_Webapp`)
  * **ความปลอดภัย**: เป็น **Read-Only Bridge** เท่านั้น (ไม่มีระบบบอท ไม่มีโค้ดส่งออเดอร์เด็ดขาด ปลอดภัยต่อพอร์ตเทรดมือ 100%)
* **Repository**: `https://github.com/satochitom-stack/fxlog-pro-v1`

---

## 2. ทำเนียบกลยุทธ์บอทอัตโนมัติ 8 เซตอัพ (Active 8 Strategy Catalog)

| **1** | **🎯 Signature Pullback (#PullBack ร้อยล้าน)** *(ใหม่ล่าสุด)* | **M5** | `555860` - `555863` | **กลยุทธ์ 3-Confluence จากหนังสือ #PullBack ร้อยล้าน (พี่เอก / Trader Overseas)**<br>• รอคลื่น Impulse ทะลุโครงสร้าง แล้วย่อตัวเข้า 3-Confluence Zone:<br>&nbsp;&nbsp;1) Retest เส้น EMA 60<br>&nbsp;&nbsp;2) Fibonacci Retracement 38.2% - 61.8%<br>&nbsp;&nbsp;3) S/R Flip แนวรับต้านเดิมที่เบรกทะลุ<br>• แท่งเทียนทริกเกอร์: Pinbar Rejection $\ge 45\%$ หรือ Engulfing<br>• **การบริหารออเดอร์ (แบบที่ 3)**: **ความเสี่ยง Step-Up 2.0%** แบ่งปิด 50% ที่ 1.5R ยกกันทุน (BE) แล้วรันเทรนด์ด้วย **EMA 60 Trailing Stop** |
| **2** | **🛡️ RTM Quasimodo M4 (Conservative)** | **M15** | `777004`, `777014`.. | **RTM Quasimodo Confluence เกรด A/A+**<br>• โครงสร้าง QM + Kill Zones + Fib 61.8-78.6%<br>• **ความเสี่ยง Step-Up 2.0%**, TP 2.0R ล็อกทุน 1.0R |
| **3** | **👑 RTM Quasimodo M6 (Elite Growth)** | **M15** | `777006`, `777016`.. | **RTM Elite Confluence คัดหัวกะทิ A/A+**<br>• คัดเฉพาะไม้คุณภาพสูง A, A+ **ความเสี่ยง Step-Up 2.0%**, TP 2.0R ล็อกทุน 1.0R |
| **4** | **😈 SMC x STO Devil (H1)** | **H1** | `555770` - `555773` | **ระบบปีศาจ SMC x Stochastic (SMC by Bossz)**<br>• กรองเทรนด์ H1 + โซน Discount/Premium + Order Block + Stochastic<br>• **ความเสี่ยงคงที่ 1.0%**, TP 1:2.2, Safe SL 500-900 จุด |
| **5** | **⚡ News Momentum Expansion** | **M5** | `555890` - `555893` | ดักจับแท่ง Breakout ข่าวกล่องแดง + EarthETC SL (**ความเสี่ยง 0.5% ป้องกันพอร์ต**) |
| **6** | **⛩️ Asian Range Sniper** | **M5** | `555820` - `555823` | สไนเปอร์กรอบไซด์เวย์ (Mean Reversion) กรองเทรนด์ (**ความเสี่ยง 0.5% ป้องกันพอร์ต**) |
| **-** | **📦 เซตอัพที่เลิกใช้ (RETIRED_SETUPS)** | - | M5, M7, Legacy | ปลดระวาง RTM M5, M7 และเซตอัพเก่า รวมสถิติเพื่อความโปร่งใส ปิดรับออเดอร์ใหม่ 100% |

---

## 3. สรุปการปรับปรุงระบบและโค้ดล่าสุด (Latest Updates)
1. **ปลดระวาง M5 และ M7**: ตัดออกจาก `bot_engine.py` และ `config.json` เหลือ 6 เซตอัพหลัก (`max_concurrent_setups: 6`)
2. **บรรจุเซตอัพดร.เอก**: เพิ่มกลยุทธ์ `PULLBACK_DR_EKK` สมบูรณ์ทั้งระบบ Indicator, Trigger, Trailing และคำนวณ Lot Step-Up 2.0%
3. **จัดหมวดหมู่ประวัติ**: รวมประวัติไม้เทรดเก่าของ M5, M7, และ Legacy เข้าสู่ `📦 เซตอัพที่เลิกใช้` ในระบบ Analytics และหน้า Dashboard
4. **Unit Tests & Build**: ผ่านครบ 39/39 ข้อ และคอมไพล์ Frontend ผ่าน 100%

---

## 4. คำสั่งสำหรับ AI ฝั่ง VPS (Prompt for VPS Antigravity)
เมื่อเปิด Antigravity บน VPS ให้เปิดโฟลเดอร์โปรเจกต์ `XAUUSD_Scalping_M5_Webapp` แล้วส่งคำสั่งนี้ในหน้าต่างแชท:

> *"คุณคือ AI Autonomous Analyst & Sentinel ประจำบอทเทรด XAUUSD บน VPS นี้ ให้อ่านไฟล์ `PROJECT_CONTEXT_HANDOVER.md` และ `walkthrough.md` เพื่อรับบริบทระบบทั้งหมด 100% จากนั้นช่วยตรวจสอบสถานะปัจจุบันของบอท: 1) ตรวจสอบว่า `bot_engine.py` และ MT5 ทำงานปกติหรือไม่ 2) ตรวจสอบไม้ที่เปิดอยู่ (Active Positions) 3) สรุปผลงานของ 6 เซตอัพหลักและหมวดเซตอัพที่เลิกใช้ พร้อมทำหน้าที่เป็น Daily Auditor คอยมอนิเตอร์และวิเคราะห์ไม้แพ้เพื่อปรับปรุงระบบให้ดียิ่งขึ้นตามรอบเวลา"*
