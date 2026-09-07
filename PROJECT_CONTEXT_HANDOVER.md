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

| ลำดับ | เซตอัพ (Setup Name) | Timeframe | Magic Number | คำอธิบาย & กฎการเข้าเทรด |
|:---:|---|:---:|:---:|---|
| **1** | **😈 SMC x STO Devil (H1)** | **H1** | `555770` - `555773` | **ระบบปีศาจ SMC x Stochastic (SMC by Bossz)**<br>• กรองเทรนด์ใหญ่ H1: EMA 50 > EMA 200 (Buy Only), EMA 50 < EMA 200 (Sell Only)<br>• กรองโซนย่อ Discount/Premium: ระยะย่อ $\ge 1.0 \times \text{ATR}(14)$<br>• กฎข้อเดียว Order Block: แท่งสีตรงข้ามแท่งสุดท้ายก่อนคลื่น Expansion สร้าง Swing High/Low<br>• จุดเข้าทริกเกอร์: Stochastic (14,3,3) Oversold $\le 28$ (%K ตัดขึ้น %D) หรือ Overbought $\ge 72$ (%K ตัดลง %D)<br>• Risk/Reward: TP 1:2.0, Safe SL 500-900 จุด, Bar Lock 1 ไม้/แท่ง H1 |
| **2** | **🛡️ RTM Quasimodo M4 (Conservative)** *(ใหม่)* | **M15** | `777004`, `777014`.. | **RTM Quasimodo Confluence เกรด A/A+**<br>• โครงสร้าง QM ($HH \rightarrow LL$ / $LL \rightarrow HH$) + Kill Zones + Fib 61.8-78.6%<br>• เสี่ยงคงที่ 1.0% ทุกไม้, TP 3.0R (Backtest Winrate 53.8%, กำไร +117.1%, DD 24.4%) |
| **3** | **🌊 RTM Quasimodo M5 (All-Weather)** *(ใหม่)* | **M15** | `777005`, `777015`.. | **RTM Quasimodo ปรับความเสี่ยงตามเกรด**<br>• เล่นทุกเกรด B=0.5%, A=1.0%, A+=2.0%, TP 3.0R (Backtest กำไร +119.9%) |
| **4** | **👑 RTM Quasimodo M6 (Elite Growth)** *(ใหม่)* | **M15** | `777006`, `777016`.. | **RTM Elite Confluence คัดหัวกะทิ A=1.0%, A+=2.0%**<br>• คัดเฉพาะไม้คุณภาพสูง A, A+ TP 3.0R ล็อกทุน 1.0R (Backtest กำไร +180.9%, DD 33.2%) |
| **5** | **🎯 RTM Quasimodo M7 (Max Alpha)** *(ใหม่)* | **M15** | `777007`, `777017`.. | **RTM Elite Confluence รันเทรนด์เป้าไกล 3.5R**<br>• คัดเฉพาะไม้คุณภาพ A=1.0%, A+=2.0% TP 3.5R (Backtest Winrate 54.6%, กำไร +229.0%, PF 1.22) |
| **6** | **⭐ Captain SMC Signal V1.2** | M5 | `555880` - `555883` | Smart Money Concept อัตโนมัติ เข้าทั้ง Fast (ไส้ปฏิเสธ S/R 35%) และ Confirmed (CHoCH Break) |
| **7** | **⚜️ TKT SMC Gold Pro v8.0** | M15 | `555810` - `555813` | Confluence Score $\ge 60\%$ กรอง FVG Imbalance + Order Block + Kill Zone บน M15 |
| **8** | **⛩️ Asian Range Sniper** | M5 | `555820` - `555823` | สไนเปอร์กรอบตลาดเอเชีย (07:00-14:00) แตะขอบ Bollinger Band + Fast RSI 7 ดีดกลับหา SMA 20 |
| **9** | **📈 EMA 50 + 3 Candles** | H1 | `555850` - `555853` | ตามเทรนด์ H1 เมื่อเกิดแท่งเทียนสีเดียวกัน 3 แท่งติดเหนือ/ใต้เส้น EMA 50 + ความชัน |
| **10** | **⚡ Flash Micro-Scalper** | M5 | `555800` - `555803` | เกาะคลื่น EMA 9 ขาเดียว ปิดเก็บรอบสั้น Safe SL 450 จุด |
| **11** | **🎯 M1 Sniper Confirmation** | M1 | `555870` - `555873` | ย่อยโซน M15/M5 รอคอนเฟิร์ม M1 Internal BOS เข้าจุดคมกริบ ดัน R:R สูง 1:2.5 - 1:3 |
| **12** | **⚡ News Momentum Breakout** | M5 | `555890` - `555893` | ดักจับแท่ง Breakout ข่าวกล่องแดง (CPI, NFP, FOMC) พร้อม Trailing กว้าง |

---

## 3. สรุปการปรับปรุงระบบและโค้ดล่าสุด

### 3.1 บอทเทรด (`XAUUSD_Scalping_M5_Webapp`)
1. **เพิ่มโมเดล RTM Quasimodo Multi-Model Institutional Engine ใน `bot_engine.py`**:
   - วิเคราะห์กราฟบนแท่งเทียน **M15 + H1 Filter** (จุดเข้า Left Shoulder QML, ICT Kill Zones, Fib 61.8-78.6%, Rejection Candle)
   - รองรับพารามิเตอร์ `rtm_mode`: `"ALL"`, `"MODEL_4"`, `"MODEL_5"`, `"MODEL_6"`, `"MODEL_7"`
   - โหมด `"ALL"` ทำงานด้วยสมองกลตัวเดียวแต่กระจายยิงออเดอร์แยก 4 Magic Numbers อิสระ (`777004`, `777005`, `777006`, `777007`)
   - ระบบ Dynamic Risk Sizing ตามเกรดคุณภาพ (Grade A+ = 2.0%, Grade A = 1.0%, Grade B = 0.5%)
2. **อัปเดต `strategy_analytics.py`**:
   - เพิ่ม RTM M4, M5, M6, M7 ใน `STRATEGY_REGISTRY` และตรรกะแยกไม้เทรดใน `_classify_deal_strategy`
   - เพิ่ม Unit Test ครบชุดใน `tests/test_rtm_engine.py` (ผ่าน 100%)

### 3.2 เว็บแอพแดชบอร์ด (`bot-intelligence-dashboard`)
1. **`src/services/botDataService.ts`**: เพิ่มทั้ง 4 โมเดล RTM เข้าทำเนียบกลยุทธ์หลัก
2. **`src/components/SetupPerformanceAnalytics.tsx`**: เพิ่มการวิเคราะห์เจาะลึก Why Win / Why Loss / Fix Action ของ RTM M4-M7
3. **`src/App.tsx`**: อัปเดตการจับคู่ Trade Journal และสถิติ Real-Time
4. **Build & Deploy**: คอมไพล์ผ่าน 100% (0 errors) และ Deploy ขึ้น Vercel เรียบร้อย

---

## 4. คำสั่งสำหรับ AI เมื่อเปิดเครื่องที่บ้าน (Prompt for Home AI)
เมื่อกลับไปที่บ้านและเปิด Antigravity บนเครื่องที่บ้าน คุณ @TOM สามารถพิมพ์คำสั่งนี้ได้ทันที:
> *"อ่านไฟล์ PROJECT_CONTEXT_HANDOVER.md ในโปรเจกต์ XAUUSD_Scalping_M5_Webapp แล้วสรุปสถานะล่าสุดของระบบบอท RTM Quasimodo Multi-Model (M4-M7) และ SMCxSTO ให้ฟังหน่อย"*
