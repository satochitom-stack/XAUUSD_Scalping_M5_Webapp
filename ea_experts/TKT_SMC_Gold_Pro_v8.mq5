//+------------------------------------------------------------------+
//|                                       TKT_SMC_Gold_Pro_v8.mq5    |
//|                         Based on TKT SMC Gold Pro v8.0           |
//|                    Reverse-Engineered for Professional MT5 Bot   |
//+------------------------------------------------------------------+
#property copyright "TKT SMC Gold Pro / Antigravity Pro"
#property link      "https://tradingview.com"
#property version   "8.00"
#property description "TKT SMC Gold Pro v8.0 - Institutional Confluence Scoring EA"
#property description "Recommended Timeframe: M15 (15 Minutes)"
#property description "Features: Structure (BOS/CHoCH), FVG Mitigation, Order Blocks, Kill Zones & Score >= 60%"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>

//--- Enums
enum ENUM_KILLZONE
{
   KZ_NONE,
   KZ_ASIA,
   KZ_LONDON,
   KZ_NY_AM
};

//--- INPUT PARAMETERS ---
input group "=== 1. TIMEFRAME & INSTITUTIONAL SCORING ==="
input ENUM_TIMEFRAMES InpTradingTF         = PERIOD_M15;       // Timeframe แนะนำ (M15 Sweet Spot)
input int              InpScoreThreshold   = 60;               // Signal Score Threshold (%) [>= 60%]
input bool             InpUseHTFFilter     = true;             // กรองแนวโน้มร่วมกับ Timeframe ใหญ่ (H1)

input group "=== 2. SMART MONEY CONCEPTS & FVG ==="
input bool             InpShowStructure    = true;             // ตรวจจับ Market Structure (BOS / CHoCH)
input bool             InpShowFVG          = true;             // ตรวจจับ Fair Value Gaps (FVG)
input double           InpMinFVGSizePts    = 50.0;             // Min FVG Size (points)
input bool             InpShowOrderBlocks  = true;             // ตรวจจับ Internal Order Blocks (OB)
input int              InpPDLookback       = 50;               // Premium / Discount Lookback (Bars)

input group "=== 3. KILL ZONES (SESSION UTC+7) ==="
input bool             InpUseKillZones     = true;             // ให้คะแนนโบนัส Kill Zone Session
input int              InpTimezoneOffset   = 7;                // Timezone (UTC+)
input bool             InpAsiaKZ           = true;             // Asia Kill Zone (07:00 - 14:00)
input bool             InpLondonKZ         = true;             // London Kill Zone (14:00 - 18:00)
input bool             InpNYKZ             = true;             // NY AM Kill Zone (19:00 - 23:00)

input group "=== 4. TRADE MANAGEMENT (POINTS) ==="
input double           InpStopLossPts      = 1000.0;           // Stop Loss (points) [ค่ามาตรฐาน v8.0]
input double           InpTP1Pts           = 1000.0;           // Take Profit 1 (points) [1:1 RRR]
input double           InpTP2Pts           = 1500.0;           // Take Profit 2 (points) [1:1.5 RRR]
input bool             InpAutoBreakEven    = true;             // ขยับ SL มากันทุนเมื่อ TP1 สำเร็จ
input double           InpBEBufferPts      = 50.0;             // BE Profit Buffer (points)

input group "=== 5. MONEY MANAGEMENT ==="
input bool             InpAutoLot          = true;             // เปิดคำนวณ Lot Size อัตโนมัติ (Risk %)
input double           InpRiskPercent      = 1.5;              // Risk (%) ต่อรอบสัญญาณ
input double           InpFixedLot         = 0.02;             // Fixed Lot Size (ถ้าไม่ใช้ Auto Lot)
input double           InpMaxSpreadPts     = 450.0;            // Max Spread Filter (Points)

input group "=== 6. EA IDENTITY ==="
input ulong            InpMagicNumber      = 999150;           // Base Magic Number
input string           InpTradeComment     = "TKT_SMC_v8";     // Trade Comment

//--- Global Trade Objects
CTrade         m_trade;
CPositionInfo  m_position;
CAccountInfo   m_account;

//--- Internal State
datetime m_last_bar_time = 0;
double   m_point_mult = 1.0;

ulong    m_magic_p1;
ulong    m_magic_p2;

struct FVGZone
{
   double top;
   double bottom;
   bool   is_bullish;
   datetime time;
   bool   mitigated;
};
FVGZone m_fvgs[];

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   m_point_mult = (_Digits == 3 || _Digits == 5) ? 10.0 : 1.0;

   m_magic_p1 = InpMagicNumber + 1; // Order 1 (TP1)
   m_magic_p2 = InpMagicNumber + 2; // Order 2 (TP2 / Runner)

   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetTypeFilling(ORDER_FILLING_FOK);
   if(!m_trade.SetTypeFillingBySymbol(_Symbol))
      m_trade.SetTypeFilling(ORDER_FILLING_IOC);

   ArrayResize(m_fvgs, 0);
   CreateDashboardUI();
   Print("🚀 TKT SMC Gold Pro v8.0 EA initialized successfully on ", EnumToString(InpTradingTF));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, "TKTSMC_");
   Comment("");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Position Management (Break-Even when TP1 is hit)
   ManageActivePositions();

   // 2. Bar Close Trigger (Evaluate at close of M15 candle)
   datetime current_bar_time = iTime(_Symbol, InpTradingTF, 0);
   if(current_bar_time == m_last_bar_time) return;

   // Check spread filter
   double spread = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPts * m_point_mult)
   {
      UpdateDashboard("SPREAD_WAIT", "Spread high: " + DoubleToString(spread, 1), 0, "None");
      return;
   }

   // 3. Scan & Update FVGs and Order Blocks
   ScanFVGs();

   // 4. Calculate Confluence Score
   int buy_score = 0;
   int sell_score = 0;
   string factor_details = "";

   CalculateConfluenceScores(buy_score, sell_score, factor_details);

   // 5. Check Active Positions
   int open_positions = CountOpenPositions();

   // 6. Execute Signals if Score >= Threshold
   if(open_positions == 0)
   {
      if(buy_score >= InpScoreThreshold && buy_score > sell_score)
      {
         ExecuteBuyOrder(buy_score, factor_details);
      }
      else if(sell_score >= InpScoreThreshold && sell_score > buy_score)
      {
         ExecuteSellOrder(sell_score, factor_details);
      }
   }

   m_last_bar_time = current_bar_time;
   int highest_score = MathMax(buy_score, sell_score);
   string trend_str = (buy_score > sell_score) ? "BULLISH" : (sell_score > buy_score ? "BEARISH" : "NEUTRAL");
   UpdateDashboard("MONITORING", factor_details, highest_score, trend_str);
}

//+------------------------------------------------------------------+
//| Scan for Fair Value Gaps (3-Candle Imbalance)                    |
//+------------------------------------------------------------------+
void ScanFVGs()
{
   ArrayResize(m_fvgs, 0);
   MqlRates rates[60];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, InpTradingTF, 1, 60, rates) < 60) return;

   double min_size = InpMinFVGSizePts * _Point * m_point_mult;

   for(int i = 1; i < 50 && ArraySize(m_fvgs) < 10; i++)
   {
      // Bullish FVG: Low of candle[i-1] > High of candle[i+1]
      if(rates[i-1].low > rates[i+1].high + min_size)
      {
         int sz = ArraySize(m_fvgs);
         ArrayResize(m_fvgs, sz + 1);
         m_fvgs[sz].top = rates[i-1].low;
         m_fvgs[sz].bottom = rates[i+1].high;
         m_fvgs[sz].is_bullish = true;
         m_fvgs[sz].time = rates[i].time;
         m_fvgs[sz].mitigated = (rates[0].low <= m_fvgs[sz].top);
      }
      // Bearish FVG: High of candle[i-1] < Low of candle[i+1]
      else if(rates[i-1].high < rates[i+1].low - min_size)
      {
         int sz = ArraySize(m_fvgs);
         ArrayResize(m_fvgs, sz + 1);
         m_fvgs[sz].top = rates[i+1].low;
         m_fvgs[sz].bottom = rates[i-1].high;
         m_fvgs[sz].is_bullish = false;
         m_fvgs[sz].time = rates[i].time;
         m_fvgs[sz].mitigated = (rates[0].high >= m_fvgs[sz].bottom);
      }
   }
}

//+------------------------------------------------------------------+
//| Calculate Institutional Confluence Scores (0-100%)               |
//+------------------------------------------------------------------+
void CalculateConfluenceScores(int &buy_score, int &sell_score, string &factors)
{
   buy_score = 0;
   sell_score = 0;

   MqlRates rates[60];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, InpTradingTF, 1, 60, rates) < 60) return;

   MqlRates b1 = rates[0];

   // 1. Structure Trend Score (SS: 25%)
   double swing_high = rates[5].high;
   double swing_low  = rates[5].low;
   for(int i = 6; i < 25; i++)
   {
      if(rates[i].high > swing_high) swing_high = rates[i].high;
      if(rates[i].low < swing_low)   swing_low  = rates[i].low;
   }

   bool bullish_structure = (b1.close > swing_high || (rates[1].close > rates[2].high));
   bool bearish_structure = (b1.close < swing_low  || (rates[1].close < rates[2].low));

   if(bullish_structure) buy_score += 25;
   if(bearish_structure) sell_score += 25;

   // 2. FVG & Order Block Reaction Score (OB: 25%)
   bool touched_bull_fvg = false;
   bool touched_bear_fvg = false;
   for(int i = 0; i < ArraySize(m_fvgs); i++)
   {
      if(m_fvgs[i].is_bullish && b1.low <= m_fvgs[i].top && b1.close >= m_fvgs[i].bottom)
      {
         touched_bull_fvg = true;
         break;
      }
      if(!m_fvgs[i].is_bullish && b1.high >= m_fvgs[i].bottom && b1.close <= m_fvgs[i].top)
      {
         touched_bear_fvg = true;
         break;
      }
   }
   if(touched_bull_fvg) buy_score += 25;
   if(touched_bear_fvg) sell_score += 25;

   // 3. Kill Zone Session Bonus (KZ: 20%)
   ENUM_KILLZONE kz = GetCurrentKillZone();
   if(kz != KZ_NONE)
   {
      buy_score += 20;
      sell_score += 20;
   }

   // 4. Premium / Discount Location Score (PD: 15%)
   double pd_high = rates[0].high;
   double pd_low  = rates[0].low;
   for(int i = 1; i < InpPDLookback && i < 60; i++)
   {
      if(rates[i].high > pd_high) pd_high = rates[i].high;
      if(rates[i].low < pd_low)   pd_low  = rates[i].low;
   }
   double equilibrium = (pd_high + pd_low) / 2.0;

   // Buy in Discount (< 50% equilibrium)
   if(b1.close < equilibrium) buy_score += 15;
   // Sell in Premium (> 50% equilibrium)
   if(b1.close > equilibrium) sell_score += 15;

   // 5. Candlestick Rejection / Volume Confirmation (PA: 15%)
   double candle_range = b1.high - b1.low;
   if(candle_range > 0.30 * m_point_mult)
   {
      double lower_wick = MathMin(b1.open, b1.close) - b1.low;
      double upper_wick = b1.high - MathMax(b1.open, b1.close);

      if((lower_wick / candle_range) >= 0.30 && b1.close > b1.open) buy_score += 15;
      if((upper_wick / candle_range) >= 0.30 && b1.close < b1.open) sell_score += 15;
   }

   // 6. Higher Timeframe H1 Filter (Optional alignment bonus)
   if(InpUseHTFFilter)
   {
      MqlRates h1_rates[5];
      ArraySetAsSeries(h1_rates, true);
      if(CopyRates(_Symbol, PERIOD_H1, 1, 5, h1_rates) >= 5)
      {
         if(h1_rates[0].close > h1_rates[2].close) buy_score += 10;
         else if(h1_rates[0].close < h1_rates[2].close) sell_score += 10;
      }
   }

   factors = StringFormat("SS:%d%% | OB:%s | KZ:%s | PD:%s", 
      (buy_score > sell_score ? buy_score : sell_score),
      (touched_bull_fvg || touched_bear_fvg ? "YES" : "NO"),
      (kz == KZ_ASIA ? "Asia" : (kz == KZ_LONDON ? "London" : (kz == KZ_NY_AM ? "NY" : "None"))),
      (b1.close < equilibrium ? "Discount" : "Premium"));
}

//+------------------------------------------------------------------+
//| Get Current Active Kill Zone (UTC+7)                             |
//+------------------------------------------------------------------+
ENUM_KILLZONE GetCurrentKillZone()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   int hour = dt.hour + 4; // Broker time offset approximation to Thai UTC+7
   if(hour >= 24) hour -= 24;

   if(InpAsiaKZ && hour >= 7 && hour < 14) return KZ_ASIA;
   if(InpLondonKZ && hour >= 14 && hour < 18) return KZ_LONDON;
   if(InpNYKZ && hour >= 19 && hour < 23) return KZ_NY_AM;

   return KZ_NONE;
}

//+------------------------------------------------------------------+
//| Execute BUY Orders (Multi-TP: TP1 1000 pts, TP2 1500 pts)        |
//+------------------------------------------------------------------+
void ExecuteBuyOrder(int score, string reason)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl_pts = InpStopLossPts * _Point * m_point_mult;
   double tp1_pts = InpTP1Pts * _Point * m_point_mult;
   double tp2_pts = InpTP2Pts * _Point * m_point_mult;

   double sl  = ask - sl_pts;
   double tp1 = ask + tp1_pts;
   double tp2 = ask + tp2_pts;

   double total_lot = CalculateLotSize(sl_pts);
   double lot1 = NormalizeDouble(total_lot * 0.50, 2);
   double lot2 = NormalizeDouble(total_lot * 0.50, 2);
   if(lot1 < 0.01) lot1 = 0.01;
   if(lot2 < 0.01) lot2 = 0.01;

   m_trade.SetExpertMagicNumber(m_magic_p1);
   m_trade.Buy(lot1, _Symbol, ask, sl, tp1, InpTradeComment + "_TP1_Score" + IntegerToString(score));

   m_trade.SetExpertMagicNumber(m_magic_p2);
   m_trade.Buy(lot2, _Symbol, ask, sl, tp2, InpTradeComment + "_TP2_Score" + IntegerToString(score));

   PrintFormat("🟢 [TKT SMC BUY] Score: %d%% | Ask: %.2f | SL: %.2f | TP1: %.2f | TP2: %.2f | Lot: %.2f", score, ask, sl, tp1, tp2, total_lot);
}

//+------------------------------------------------------------------+
//| Execute SELL Orders (Multi-TP: TP1 1000 pts, TP2 1500 pts)       |
//+------------------------------------------------------------------+
void ExecuteSellOrder(int score, string reason)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl_pts = InpStopLossPts * _Point * m_point_mult;
   double tp1_pts = InpTP1Pts * _Point * m_point_mult;
   double tp2_pts = InpTP2Pts * _Point * m_point_mult;

   double sl  = bid + sl_pts;
   double tp1 = bid - tp1_pts;
   double tp2 = bid - tp2_pts;

   double total_lot = CalculateLotSize(sl_pts);
   double lot1 = NormalizeDouble(total_lot * 0.50, 2);
   double lot2 = NormalizeDouble(total_lot * 0.50, 2);
   if(lot1 < 0.01) lot1 = 0.01;
   if(lot2 < 0.01) lot2 = 0.01;

   m_trade.SetExpertMagicNumber(m_magic_p1);
   m_trade.Sell(lot1, _Symbol, bid, sl, tp1, InpTradeComment + "_TP1_Score" + IntegerToString(score));

   m_trade.SetExpertMagicNumber(m_magic_p2);
   m_trade.Sell(lot2, _Symbol, bid, sl, tp2, InpTradeComment + "_TP2_Score" + IntegerToString(score));

   PrintFormat("🔴 [TKT SMC SELL] Score: %d%% | Bid: %.2f | SL: %.2f | TP1: %.2f | TP2: %.2f | Lot: %.2f", score, bid, sl, tp1, tp2, total_lot);
}

//+------------------------------------------------------------------+
//| Position Management (Lock Break-Even when TP1 is hit)            |
//+------------------------------------------------------------------+
void ManageActivePositions()
{
   if(!InpAutoBreakEven) return;

   double be_buffer = InpBEBufferPts * _Point * m_point_mult;

   // Check if TP1 closed and TP2 is still open
   bool tp1_open = false;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i) && m_position.Symbol() == _Symbol && m_position.Magic() == m_magic_p1)
      {
         tp1_open = true;
         break;
      }
   }

   // If TP1 is closed (hit TP), move TP2 to Break-Even + buffer
   if(!tp1_open)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!m_position.SelectByIndex(i)) continue;
         if(m_position.Symbol() != _Symbol) continue;
         if(m_position.Magic() != m_magic_p2) continue;

         double open_p = m_position.PriceOpen();
         double sl = m_position.StopLoss();
         ENUM_POSITION_TYPE ptype = m_position.PositionType();

         if(ptype == POSITION_TYPE_BUY && (sl < open_p || sl == 0))
         {
            double new_sl = open_p + be_buffer;
            m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
            Print("🛡️ [TKT SMC BE] Locked Break-Even for Order #", m_position.Ticket());
         }
         else if(ptype == POSITION_TYPE_SELL && (sl > open_p || sl == 0))
         {
            double new_sl = open_p - be_buffer;
            m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
            Print("🛡️ [TKT SMC BE] Locked Break-Even for Order #", m_position.Ticket());
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Helpers & Calculations                                           |
//+------------------------------------------------------------------+
double CalculateLotSize(double sl_dist)
{
   if(!InpAutoLot) return InpFixedLot;

   double balance = m_account.Balance();
   double risk_money = balance * (InpRiskPercent / 100.0);
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);

   double lot = risk_money / (sl_dist * (tick_value / (tick_size + 1e-9)));
   lot = NormalizeDouble(lot, 2);
   if(lot < 0.01) lot = 0.01;
   if(lot > 20.0) lot = 20.0;
   return lot;
}

int CountOpenPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i) && m_position.Symbol() == _Symbol)
      {
         ulong m = m_position.Magic();
         if(m >= InpMagicNumber && m <= InpMagicNumber + 5) count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| On-Chart HUD Dashboard                                           |
//+------------------------------------------------------------------+
void CreateDashboardUI()
{
   ObjectCreate(0, "TKTSMC_Bg", OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, "TKTSMC_Bg", OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, "TKTSMC_Bg", OBJPROP_XDISTANCE, 240);
   ObjectSetInteger(0, "TKTSMC_Bg", OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, "TKTSMC_Bg", OBJPROP_XSIZE, 230);
   ObjectSetInteger(0, "TKTSMC_Bg", OBJPROP_YSIZE, 270);
   ObjectSetInteger(0, "TKTSMC_Bg", OBJPROP_BGCOLOR, C'12,18,28');
   ObjectSetInteger(0, "TKTSMC_Bg", OBJPROP_BORDER_COLOR, C'50,80,140');

   UpdateDashboard("INITIALIZED", "Ready", 0, "NEUTRAL");
}

void UpdateDashboard(string status, string factors, int score, string trend)
{
   string text = "\n" +
      "  ⚜️ TKT SMC Gold Pro v8.0\n" +
      "  ────────────────────────\n" +
      "  • TF:      M15 (Sweet Spot)\n" +
      "  • Trend:   " + trend + "\n" +
      "  • Score:   " + IntegerToString(score) + "% (Min: " + IntegerToString(InpScoreThreshold) + "%)\n" +
      "  • Status:  " + status + "\n" +
      "  • Active:  " + IntegerToString(CountOpenPositions()) + " orders\n" +
      "  • Targets: TP1 1000 | TP2 1500\n" +
      "  • Factors: " + factors + "\n" +
      "  ────────────────────────\n" +
      "  Institutional Confluence";

   Comment(text);
}
