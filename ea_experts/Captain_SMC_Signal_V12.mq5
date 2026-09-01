//+------------------------------------------------------------------+
//|                                     Captain_SMC_Signal_V12.mq5   |
//|                         Based on SMC Signal V.1.2 & Hybrid V.3.3 |
//|                                           [Captain Trading LAB]  |
//|                    Reverse-Engineered for Professional MT5 Bot   |
//+------------------------------------------------------------------+
#property copyright "Captain Trading LAB / Antigravity Pro"
#property link      "https://tradingview.com"
#property version   "1.20"
#property description "SMC Signal V1.2 Dual-Model Auto Execution EA"
#property description "Features: Fast (Wick Rejection) + Confirmed (CHoCH/BoS) Models"
#property description "Multi-TP (1R, 2R, 3R), Break-Even at 50%, and Dynamic TSL"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>

//--- Enums
enum ENUM_PRESET_MODE
{
   PRESET_SCALPER,   // Scalper (M5 Fast TSL, 0.3x ATR SL)
   PRESET_BALANCED,  // Balanced (Swing SL, Wider Targets)
   PRESET_CUSTOM     // กำหนดเอง (Custom)
};

enum ENUM_SIGNAL_MODE
{
   SIGNAL_DUAL_AUTO, // 🌟 Dual Auto (เข้าทั้ง Fast & Confirmed อัตโนมัติ)
   SIGNAL_FAST,      // Fast Model (Wick Rejection At S/R)
   SIGNAL_CONFIRMED  // Confirmed Model (Structure Break CHoCH)
};

//--- INPUT PARAMETERS ---
input group "=== 1. PRESET & SIGNAL MODEL ==="
input ENUM_PRESET_MODE InpPresetMode       = PRESET_SCALPER;   // เลือก Preset
input ENUM_SIGNAL_MODE InpSignalModel      = SIGNAL_DUAL_AUTO; // รูปแบบสัญญาณ (Dual เข้าทั้งคู่)

input group "=== 2. SUPPORT & RESISTANCE (S/R ZONES) ==="
input int              InpFineTuner        = 10;               // Fine Tuner (Pivot Lookback)
input int              InpMaxZones         = 5;                // จำนวนโซนสูงสุด (Max Zones)
input bool             InpShowZones        = true;             // แสดง Support/Resistance Zone
input color            InpColorSupport     = C'20,40,90';      // สี Support Zone (Demand)
input color            InpColorResistance  = C'90,20,40';      // สี Resistance Zone (Supply)

input group "=== 3. RISK:REWARD & MULTI-TP ==="
input double           InpRiskRewardRatio  = 2.0;              // Risk:Reward Ratio
input int              InpATRLength        = 14;               // ATR Length
input double           InpSLBufferATR      = 0.3;              // SL Buffer (ATR x)
input bool             InpEnableMultiTP    = true;             // เปิด Multi-TP
input double           InpTP1_R            = 1.0;              // TP1 (Rx)
input double           InpTP2_R            = 2.0;              // TP2 (Rx)
input double           InpTP3_R            = 3.0;              // TP3 (Rx) Runner

input group "=== 4. RISK MANAGEMENT & TSL ==="
input double           InpBETriggerPct     = 50.0;             // BE Trigger (%) เมื่อวิ่งถึง % ของ TP1
input double           InpTSLBufferATR     = 0.1;              // TSL Buffer (ATR x)

input group "=== 5. MONEY MANAGEMENT ==="
input bool             InpAutoLot          = true;             // เปิดคำนวณ Lot Size อัตโนมัติ
input double           InpRiskPercent      = 2.0;              // Risk (%) ต่อไม้
input double           InpFixedLot         = 0.02;             // Fixed Lot Size (ถ้าปิด Auto Lot)
input double           InpMaxSpreadPts     = 450.0;            // Max Spread Filter (Points)

input group "=== 6. EA IDENTITY ==="
input ulong            InpMagicNumber      = 888120;           // Base Magic Number
input string           InpTradeComment     = "Captain_SMC_V12";// Trade Comment

//--- Global Objects
CTrade         m_trade;
CPositionInfo  m_position;
CAccountInfo   m_account;

//--- Indicators Handles
int      m_handle_atr = INVALID_HANDLE;
datetime m_last_bar_time = 0;
double   m_point_mult = 1.0;

//--- Internal State
struct SRZone
{
   double high;
   double low;
   bool   is_support;
   datetime time;
};
SRZone m_zones[];

ulong  m_magic_p1;
ulong  m_magic_p2;
ulong  m_magic_p3;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   m_point_mult = (_Digits == 3 || _Digits == 5) ? 10.0 : 1.0;

   m_magic_p1 = InpMagicNumber + 1; // TP1 Order
   m_magic_p2 = InpMagicNumber + 2; // TP2 Order
   m_magic_p3 = InpMagicNumber + 3; // TP3 Runner Order

   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetTypeFilling(ORDER_FILLING_FOK);
   if(!m_trade.SetTypeFillingBySymbol(_Symbol))
      m_trade.SetTypeFilling(ORDER_FILLING_IOC);

   m_handle_atr = iATR(_Symbol, _Period, InpATRLength);
   if(m_handle_atr == INVALID_HANDLE)
   {
      Print("❌ Failed to initialize ATR handle");
      return INIT_FAILED;
   }

   ArrayResize(m_zones, 0);
   CreateDashboardUI();
   Print("🚀 Captain Trading LAB - SMC Signal V1.2 EA initialized successfully.");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(m_handle_atr);
   ObjectsDeleteAll(0, "CaptainSMC_");
   Comment("");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Manage Active Orders (Break-Even & Trailing Stop)
   ManageActivePositions();

   // 2. Bar Close Trigger (Evaluate signals at start of new bar)
   datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == m_last_bar_time) return;

   // Check spread filter
   double spread = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPts * m_point_mult)
   {
      UpdateDashboard("SPREAD_WAIT", "Spread high: " + DoubleToString(spread, 1));
      return;
   }

   // 3. Update Support & Resistance Zones
   UpdateSRZones();

   // 4. Check Dual Signals (Fast & Confirmed)
   bool buy_fast = false, sell_fast = false;
   bool buy_conf = false, sell_conf = false;

   CheckFastSignal(buy_fast, sell_fast);
   CheckConfirmedSignal(buy_conf, sell_conf);

   // 5. Execute Trades based on selected mode
   int open_bot_positions = CountOpenPositions();

   if(open_bot_positions == 0)
   {
      if(InpSignalModel == SIGNAL_DUAL_AUTO || InpSignalModel == SIGNAL_FAST)
      {
         if(buy_fast)  ExecuteBuy("Fast_Rejection");
         if(sell_fast) ExecuteSell("Fast_Rejection");
      }

      if(InpSignalModel == SIGNAL_DUAL_AUTO || InpSignalModel == SIGNAL_CONFIRMED)
      {
         if(!buy_fast && buy_conf)   ExecuteBuy("Confirmed_CHoCH");
         if(!sell_fast && sell_conf) ExecuteSell("Confirmed_CHoCH");
      }
   }
   else if(open_bot_positions <= 3 && InpSignalModel == SIGNAL_DUAL_AUTO)
   {
      // Optional Pyramid Scale-In if Fast entry is already at Break-Even and Confirmed signal fires
      if(buy_conf && IsInitialPositionProtected(POSITION_TYPE_BUY))
      {
         ExecutePyramidBuy("Confirmed_ScaleIn");
      }
      else if(sell_conf && IsInitialPositionProtected(POSITION_TYPE_SELL))
      {
         ExecutePyramidSell("Confirmed_ScaleIn");
      }
   }

   m_last_bar_time = current_bar_time;
   UpdateDashboard("ACTIVE", "Monitoring M5 Candles");
}

//+------------------------------------------------------------------+
//| Update Support & Resistance (Order Block) Zones                  |
//+------------------------------------------------------------------+
void UpdateSRZones()
{
   int lookback = InpFineTuner;
   int bars_to_scan = 120;
   
   ArrayResize(m_zones, 0);

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 1, bars_to_scan, rates) < bars_to_scan) return;

   for(int i = lookback; i < bars_to_scan - lookback && ArraySize(m_zones) < InpMaxZones * 2; i++)
   {
      bool is_pivot_high = true;
      bool is_pivot_low = true;

      for(int j = 1; j <= lookback; j++)
      {
         if(rates[i].high <= rates[i - j].high || rates[i].high < rates[i + j].high) is_pivot_high = false;
         if(rates[i].low >= rates[i - j].low || rates[i].low > rates[i + j].low) is_pivot_low = false;
      }

      if(is_pivot_high)
      {
         int sz = ArraySize(m_zones);
         ArrayResize(m_zones, sz + 1);
         m_zones[sz].high = rates[i].high;
         m_zones[sz].low = MathMax(rates[i].open, rates[i].close);
         m_zones[sz].is_support = false;
         m_zones[sz].time = rates[i].time;
      }
      else if(is_pivot_low)
      {
         int sz = ArraySize(m_zones);
         ArrayResize(m_zones, sz + 1);
         m_zones[sz].high = MathMin(rates[i].open, rates[i].close);
         m_zones[sz].low = rates[i].low;
         m_zones[sz].is_support = true;
         m_zones[sz].time = rates[i].time;
      }
   }

   if(InpShowZones) DrawZonesOnChart();
}

//+------------------------------------------------------------------+
//| Draw Support & Resistance Boxes on Chart                         |
//+------------------------------------------------------------------+
void DrawZonesOnChart()
{
   ObjectsDeleteAll(0, "CaptainSMC_Zone_");

   datetime now_t = TimeCurrent() + (PeriodSeconds(_Period) * 15);
   int drawn = 0;
   for(int i = 0; i < ArraySize(m_zones) && drawn < InpMaxZones; i++)
   {
      string name = "CaptainSMC_Zone_" + IntegerToString(i);
      color clr = m_zones[i].is_support ? InpColorSupport : InpColorResistance;

      ObjectCreate(0, name, OBJ_RECTANGLE, 0, m_zones[i].time, m_zones[i].high, now_t, m_zones[i].low);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, clr);
      ObjectSetInteger(0, name, OBJPROP_FILL, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      drawn++;
   }
}

//+------------------------------------------------------------------+
//| Check Fast Signal (Wick Rejection at S/R Zone)                   |
//+------------------------------------------------------------------+
void CheckFastSignal(bool &buy_sig, bool &sell_sig)
{
   buy_sig = false;
   sell_sig = false;

   MqlRates b1;
   MqlRates rates[2];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 1, 2, rates) < 2) return;
   b1 = rates[0];

   double candle_range = b1.high - b1.low;
   if(candle_range <= 0.20 * m_point_mult) return;

   double upper_wick = b1.high - MathMax(b1.open, b1.close);
   double lower_wick = MathMin(b1.open, b1.close) - b1.low;

   for(int i = 0; i < ArraySize(m_zones); i++)
   {
      // Buy: Tests Support Zone + Lower Wick >= 35% + Bullish close
      if(m_zones[i].is_support && b1.low <= m_zones[i].high && b1.close >= m_zones[i].low)
      {
         if((lower_wick / candle_range) >= 0.35 && b1.close > b1.open)
         {
            buy_sig = true;
            return;
         }
      }

      // Sell: Tests Resistance Zone + Upper Wick >= 35% + Bearish close
      if(!m_zones[i].is_support && b1.high >= m_zones[i].low && b1.close <= m_zones[i].high)
      {
         if((upper_wick / candle_range) >= 0.35 && b1.close < b1.open)
         {
            sell_sig = true;
            return;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check Confirmed Signal (CHoCH / Market Structure Break)          |
//+------------------------------------------------------------------+
void CheckConfirmedSignal(bool &buy_sig, bool &sell_sig)
{
   buy_sig = false;
   sell_sig = false;

   MqlRates rates[25];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 1, 25, rates) < 25) return;

   MqlRates b1 = rates[0];
   double recent_high = rates[2].high;
   double recent_low  = rates[2].low;

   for(int i = 3; i < 15; i++)
   {
      if(rates[i].high > recent_high) recent_high = rates[i].high;
      if(rates[i].low < recent_low)   recent_low  = rates[i].low;
   }

   // Bullish CHoCH Break: Close breaks swing high with bullish candle
   if(b1.close > recent_high && b1.close > b1.open)
   {
      buy_sig = true;
   }
   // Bearish CHoCH Break: Close breaks swing low with bearish candle
   else if(b1.close < recent_low && b1.close < b1.open)
   {
      sell_sig = true;
   }
}

//+------------------------------------------------------------------+
//| Execute BUY Order with Multi-TP Split                            |
//+------------------------------------------------------------------+
void ExecuteBuy(string entry_model)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double atr = GetATR();

   double sl_distance = InpSLBufferATR * atr * 3.0; // Scalper buffer
   if(sl_distance < 1.00) sl_distance = 1.00;
   if(sl_distance > 5.00) sl_distance = 5.00;

   double sl = ask - sl_distance;
   double tp1 = ask + (sl_distance * InpTP1_R);
   double tp2 = ask + (sl_distance * InpTP2_R);
   double tp3 = ask + (sl_distance * InpTP3_R);

   double total_lot = CalculateLotSize(sl_distance);
   double lot1 = NormalizeDouble(total_lot * 0.40, 2);
   double lot2 = NormalizeDouble(total_lot * 0.30, 2);
   double lot3 = NormalizeDouble(total_lot * 0.30, 2);
   if(lot1 < 0.01) lot1 = 0.01;
   if(lot2 < 0.01) lot2 = 0.01;
   if(lot3 < 0.01) lot3 = 0.01;

   m_trade.SetExpertMagicNumber(m_magic_p1);
   m_trade.Buy(lot1, _Symbol, ask, sl, tp1, InpTradeComment + "_P1_" + entry_model);

   m_trade.SetExpertMagicNumber(m_magic_p2);
   m_trade.Buy(lot2, _Symbol, ask, sl, tp2, InpTradeComment + "_P2_" + entry_model);

   m_trade.SetExpertMagicNumber(m_magic_p3);
   m_trade.Buy(lot3, _Symbol, ask, sl, 0.0, InpTradeComment + "_P3_Runner");

   PrintFormat("🟢 [BUY EXECUTED] Model: %s | Ask: %.2f | SL: %.2f | TP1: %.2f | Total Lot: %.2f", entry_model, ask, sl, tp1, total_lot);
}

//+------------------------------------------------------------------+
//| Execute SELL Order with Multi-TP Split                           |
//+------------------------------------------------------------------+
void ExecuteSell(string entry_model)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double atr = GetATR();

   double sl_distance = InpSLBufferATR * atr * 3.0;
   if(sl_distance < 1.00) sl_distance = 1.00;
   if(sl_distance > 5.00) sl_distance = 5.00;

   double sl = bid + sl_distance;
   double tp1 = bid - (sl_distance * InpTP1_R);
   double tp2 = bid - (sl_distance * InpTP2_R);
   double tp3 = bid - (sl_distance * InpTP3_R);

   double total_lot = CalculateLotSize(sl_distance);
   double lot1 = NormalizeDouble(total_lot * 0.40, 2);
   double lot2 = NormalizeDouble(total_lot * 0.30, 2);
   double lot3 = NormalizeDouble(total_lot * 0.30, 2);
   if(lot1 < 0.01) lot1 = 0.01;
   if(lot2 < 0.01) lot2 = 0.01;
   if(lot3 < 0.01) lot3 = 0.01;

   m_trade.SetExpertMagicNumber(m_magic_p1);
   m_trade.Sell(lot1, _Symbol, bid, sl, tp1, InpTradeComment + "_P1_" + entry_model);

   m_trade.SetExpertMagicNumber(m_magic_p2);
   m_trade.Sell(lot2, _Symbol, bid, sl, tp2, InpTradeComment + "_P2_" + entry_model);

   m_trade.SetExpertMagicNumber(m_magic_p3);
   m_trade.Sell(lot3, _Symbol, bid, sl, 0.0, InpTradeComment + "_P3_Runner");

   PrintFormat("🔴 [SELL EXECUTED] Model: %s | Bid: %.2f | SL: %.2f | TP1: %.2f | Total Lot: %.2f", entry_model, bid, sl, tp1, total_lot);
}

//+------------------------------------------------------------------+
//| Execute Scale-In Pyramid Orders                                  |
//+------------------------------------------------------------------+
void ExecutePyramidBuy(string reason)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double lot = 0.01;
   m_trade.SetExpertMagicNumber(InpMagicNumber + 4);
   m_trade.Buy(lot, _Symbol, ask, 0.0, 0.0, InpTradeComment + "_ScaleIn");
}

void ExecutePyramidSell(string reason)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lot = 0.01;
   m_trade.SetExpertMagicNumber(InpMagicNumber + 4);
   m_trade.Sell(lot, _Symbol, bid, 0.0, 0.0, InpTradeComment + "_ScaleIn");
}

//+------------------------------------------------------------------+
//| Manage Active Positions (BE Trigger at 50% & Trailing Stop)      |
//+------------------------------------------------------------------+
void ManageActivePositions()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double atr = GetATR();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!m_position.SelectByIndex(i)) continue;
      if(m_position.Symbol() != _Symbol) continue;
      ulong magic = m_position.Magic();
      if(magic < InpMagicNumber || magic > InpMagicNumber + 5) continue;

      double open_p = m_position.PriceOpen();
      double curr_sl = m_position.StopLoss();
      double curr_tp = m_position.TakeProfit();
      ENUM_POSITION_TYPE ptype = m_position.PositionType();

      // Break-Even Trigger (50% progress to TP1)
      if(magic == m_magic_p2 || magic == m_magic_p3)
      {
         if(ptype == POSITION_TYPE_BUY)
         {
            if(bid > open_p + (0.50 * atr) && (curr_sl < open_p || curr_sl == 0))
            {
               double new_sl = open_p + (0.10 * m_point_mult);
               m_trade.PositionModify(m_position.Ticket(), new_sl, curr_tp);
               Print("🛡️ [BE LOCKED] Moved SL to BE for ticket #", m_position.Ticket());
            }
         }
         else if(ptype == POSITION_TYPE_SELL)
         {
            if(ask < open_p - (0.50 * atr) && (curr_sl > open_p || curr_sl == 0))
            {
               double new_sl = open_p - (0.10 * m_point_mult);
               m_trade.PositionModify(m_position.Ticket(), new_sl, curr_tp);
               Print("🛡️ [BE LOCKED] Moved SL to BE for ticket #", m_position.Ticket());
            }
         }
      }

      // Trailing Stop on P3 Runner
      if(magic == m_magic_p3)
      {
         double tsl_dist = InpTSLBufferATR * atr * 3.0;
         if(ptype == POSITION_TYPE_BUY)
         {
            double new_sl = bid - tsl_dist;
            if(new_sl > curr_sl && new_sl > open_p)
            {
               m_trade.PositionModify(m_position.Ticket(), new_sl, 0.0);
            }
         }
         else if(ptype == POSITION_TYPE_SELL)
         {
            double new_sl = ask + tsl_dist;
            if((new_sl < curr_sl || curr_sl == 0) && new_sl < open_p)
            {
               m_trade.PositionModify(m_position.Ticket(), new_sl, 0.0);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Helpers & Calculations                                           |
//+------------------------------------------------------------------+
double GetATR()
{
   double atr_val[];
   ArraySetAsSeries(atr_val, true);
   if(CopyBuffer(m_handle_atr, 0, 1, 1, atr_val) < 1) return 1.50;
   return atr_val[0];
}

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

bool IsInitialPositionProtected(ENUM_POSITION_TYPE type)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i) && m_position.Symbol() == _Symbol)
      {
         if(m_position.Magic() == m_magic_p3 && m_position.PositionType() == type)
         {
            if(type == POSITION_TYPE_BUY && m_position.StopLoss() >= m_position.PriceOpen()) return true;
            if(type == POSITION_TYPE_SELL && m_position.StopLoss() <= m_position.PriceOpen() && m_position.StopLoss() > 0) return true;
         }
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| On-Chart HUD Dashboard                                           |
//+------------------------------------------------------------------+
void CreateDashboardUI()
{
   // Background Panel
   ObjectCreate(0, "CaptainSMC_Bg", OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, "CaptainSMC_Bg", OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, "CaptainSMC_Bg", OBJPROP_XDISTANCE, 240);
   ObjectSetInteger(0, "CaptainSMC_Bg", OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, "CaptainSMC_Bg", OBJPROP_XSIZE, 220);
   ObjectSetInteger(0, "CaptainSMC_Bg", OBJPROP_YSIZE, 260);
   ObjectSetInteger(0, "CaptainSMC_Bg", OBJPROP_BGCOLOR, C'10,15,25');
   ObjectSetInteger(0, "CaptainSMC_Bg", OBJPROP_BORDER_COLOR, C'40,70,120');

   UpdateDashboard("INITIALIZED", "Ready");
}

void UpdateDashboard(string status, string detail)
{
   string text = "\n" +
      "  ⭐ Captain SMC Signal V1.2\n" +
      "  ────────────────────────\n" +
      "  • Preset: " + (InpPresetMode == PRESET_SCALPER ? "Scalper (M5)" : "Balanced") + "\n" +
      "  • Model:  Dual Auto (Fast+Conf)\n" +
      "  • Status: " + status + "\n" +
      "  • Active: " + IntegerToString(CountOpenPositions()) + " orders\n" +
      "  • RRR:    1:1 / 1:2 / 1:3\n" +
      "  • Detail: " + detail + "\n" +
      "  ────────────────────────\n" +
      "  Captain Trading LAB";

   Comment(text);
}
