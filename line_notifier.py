"""
LINE Notification Module for XAUUSD Scalping M5 Bot
Supports both LINE Messaging API (Channel Access Token + User/Group ID) 
and LINE Notify API with rich formatting and instant alerts.
"""

import logging
import requests
import json
from datetime import datetime

logger = logging.getLogger("LineNotifier")

class LineNotifier:
    def __init__(self, config: dict):
        self.config = config.get("line_notification", {})
        self.enabled = self.config.get("enabled", False)
        self.channel_access_token = self.config.get("channel_access_token", "")
        self.user_id = self.config.get("user_id", "")
        self.notify_token = self.config.get("notify_token", "")

    def update_config(self, line_cfg: dict):
        """Update notification settings dynamically."""
        self.config.update(line_cfg)
        self.enabled = self.config.get("enabled", False)
        self.channel_access_token = self.config.get("channel_access_token", "")
        self.user_id = self.config.get("user_id", "")
        self.notify_token = self.config.get("notify_token", "")

    def send_message(self, message: str) -> dict:
        """Send message via LINE Messaging API or LINE Notify API."""
        if not self.enabled:
            return {"status": False, "message": "LINE Notification is disabled in settings."}

        sent = False
        errors = []

        # 1. Try LINE Messaging API (Official Bot)
        if self.channel_access_token and self.user_id:
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.channel_access_token}"
                }
                payload = {
                    "to": self.user_id,
                    "messages": [
                        {
                            "type": "text",
                            "text": message
                        }
                    ]
                }
                res = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload, timeout=8)
                if res.status_code == 200:
                    sent = True
                    logger.info("LINE Messaging API alert sent successfully.")
                else:
                    errors.append(f"Messaging API error ({res.status_code}): {res.text}")
            except Exception as e:
                errors.append(f"Messaging API exception: {e}")

        # 2. Try LINE Notify API (Alternative / Legacy)
        if self.notify_token and not sent:
            try:
                headers = {
                    "Authorization": f"Bearer {self.notify_token}"
                }
                payload = {"message": message}
                res = requests.post("https://notify-api.line.me/api/notify", headers=headers, data=payload, timeout=8)
                if res.status_code == 200:
                    sent = True
                    logger.info("LINE Notify alert sent successfully.")
                else:
                    errors.append(f"LINE Notify error ({res.status_code}): {res.text}")
            except Exception as e:
                errors.append(f"LINE Notify exception: {e}")

        if sent:
            return {"status": True, "message": "Notification sent successfully"}
        else:
            err_msg = " | ".join(errors) if errors else "No valid LINE tokens configured (Need Channel Access Token + User ID or Notify Token)"
            logger.warning(f"Failed to send LINE notification: {err_msg}")
            return {"status": False, "message": err_msg}

    # --- Pre-formatted Alert Templates ---

    def notify_order_opened(self, order_type: str, symbol: str, lot: float, price: float, sl: float, tp: float, reason: str, is_multi: bool = False, lot2: float = 0.0):
        """Notify when new order is opened."""
        if not self.config.get("notify_on_open", True):
            return

        icon = "🟢" if order_type.upper() == "BUY" else "🔴"
        tp_str = f"${tp:.2f} (1:1 RR)" if tp > 0 else "Runner (EMA Trailing)"

        msg = f"\n{icon} [XAUUSD M5 BOT - ORDER OPENED]\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📌 สินทรัพย์: {symbol}\n"
        msg += f"📊 คำสั่ง: {order_type.upper()}\n"
        msg += f"💡 รูปแบบ: {reason}\n"
        if is_multi:
            msg += f"📦 Multi-Order: ไม้1={lot:.2f} lot / ไม้2={lot2:.2f} lot\n"
        else:
            msg += f"📦 ขนาด: {lot:.2f} lot\n"
        msg += f"💵 ราคาเปิด: ${price:.2f}\n"
        msg += f"🛑 Stop Loss: ${sl:.2f}\n"
        msg += f"🎯 Take Profit: {tp_str}\n"
        msg += f"⏰ เวลา: {datetime.now().strftime('%H:%M:%S')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━"

        return self.send_message(msg)

    def notify_breakeven_moved(self, ticket: int, new_sl: float):
        """Notify when SL is moved to Break-Even."""
        if not self.config.get("notify_on_be", True):
            return

        msg = f"\n🛡️ [XAUUSD M5 BOT - BREAK-EVEN LOCKED]\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"✅ ไม้ที่ 1 ชน TP 1:1 เรียบร้อยแล้ว!\n"
        msg += f"🔒 ไม้ที่ 2 (#{ticket}) ขยับ SL มากันทุนที่: ${new_sl:.2f}\n"
        msg += f"📈 สถานะ: กำลังรันเทรนด์ด้วย Trailing Stop ตาม EMA 50\n"
        msg += f"⏰ เวลา: {datetime.now().strftime('%H:%M:%S')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━"

        return self.send_message(msg)

    def notify_order_closed(self, ticket: int, profit: float, reason: str = ""):
        """Notify when position is closed."""
        if not self.config.get("notify_on_close", True):
            return

        is_win = profit >= 0
        icon = "💰" if is_win else "❌"
        status_text = "PROFIT (กำไร)" if is_win else "LOSS (ขาดทุน)"

        msg = f"\n{icon} [XAUUSD M5 BOT - ORDER CLOSED]\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🎫 ออเดอร์: #{ticket}\n"
        msg += f"📊 ผลลัพธ์: {status_text}\n"
        msg += f"💵 กำไร/ขาดทุน: {'+' if is_win else ''}${profit:.2f}\n"
        if reason:
            msg += f"📌 สาเหตุ: {reason}\n"
        msg += f"⏰ เวลา: {datetime.now().strftime('%H:%M:%S')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━"

        return self.send_message(msg)

    def notify_daily_target(self, profit_pct: float, total_profit: float, is_target: bool):
        """Notify on Daily Target or Max Loss."""
        if not self.config.get("notify_on_safety", True):
            return

        if is_target:
            msg = f"\n🏆 [XAUUSD M5 BOT - DAILY TARGET HIT!]\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🎉 ทำกำไรถึงเป้าหมายประจำวันแล้ว!\n"
            msg += f"💰 กำไรวันนี้: +{profit_pct:.2f}% (+${total_profit:.2f})\n"
            msg += f"🛑 บอทหยุดการเทรดอัตโนมัติเพื่อรักษากำไร\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━"
        else:
            msg = f"\n⚠️ [XAUUSD M5 BOT - DAILY MAX LOSS HIT]\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🛑 ขาดทุนถึงเกณฑ์ความเสี่ยงรายวัน: {profit_pct:.2f}% (${total_profit:.2f})\n"
            msg += f"🛡️ บอทหยุดการเทรดอัตโนมัติเพื่อรักษาเงินต้น\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━"

        return self.send_message(msg)

    def notify_consecutive_loss_pause(self, losses: int, pause_hours: int):
        """Notify on Consecutive Loss Pause."""
        if not self.config.get("notify_on_safety", True):
            return

        msg = f"\n⏸️ [XAUUSD M5 BOT - TRADING PAUSED]\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"⚠️ ตรวจพบการขาดทุนติดกัน {losses} ครั้ง\n"
        msg += f"🛡️ ระบบสั่งหยุดพักการเทรดชั่วคราวเป็นเวลา {pause_hours} ชั่วโมง\n"
        msg += f"เพื่อหลีกเลี่ยงสภาวะตลาด Sideway บีบตัว\n"
        msg += f"⏰ เวลา: {datetime.now().strftime('%H:%M:%S')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━"

        return self.send_message(msg)

    def send_test_notification(self) -> dict:
        """Send a test message to verify LINE setup."""
        msg = f"\n🔔 [XAUUSD M5 BOT - TEST NOTIFICATION]\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"✅ เชื่อมต่อระบบแจ้งเตือน LINE สำเร็จเรียบร้อย!\n"
        msg += f"🤖 ระบบบอทเทรดทองคำ Scalping M5 (Secret System) พร้อมส่งการแจ้งเตือนสดให้คุณตลอด 24 ชั่วโมง\n"
        msg += f"⏰ เวลาทดสอบ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━"

        return self.send_message(msg)
