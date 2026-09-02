//+------------------------------------------------------------------+
//|                                     XAUUSD_Scalping_M5.mq5        |
//|                       Scalping M5 (Secret System) Expert Advisor  |
//|                                Copyright 2026, Antigravity AI    |
//|                                             https://google.com   |
//+------------------------------------------------------------------+
#property copyright   "Copyright 2026, Antigravity AI"
#property link        "https://google.com"
#property version     "1.00"
#property description "XAUUSD Scalping M5 (Secret System) Automated Trading Bot"
#property description "Features: EMA 50/150 Trend & Slope Filter, Pullback & Breakout Setups,"
#property description "Dynamic Risk Management, Multi-Order (TP 1:1 + Trailing Runner),"
#property description "Consecutive Loss Pause, Dynamic Lot Reduction, Daily Target Stop & Live HUD."

//--- Include Trade Library
#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>
#include <Trade\OrderInfo.mqh>

//--- Enums
enum ENUM_ENTRY_TYPE
  {
   ENTRY_ALL = 0,          // Both Pullback & Breakout
   ENTRY_PULLBACK_ONLY = 1,// Pullback / Retest Only
   ENTRY_BREAKOUT_ONLY = 2 // Breakout Only
  };

enum ENUM_SL_TYPE
  {
   SL_SWING_HIGH_LOW = 0, // Recent Swing High / Low
   SL_CANDLE_HIGH_LOW = 1,// Signal Candle High / Low
   SL_EMA_LINE = 2        // EMA 50 / 150 Line + Buffer
  };

enum ENUM_LOT_MODE
  {
   LOT_RISK_PERCENT = 0,  // Risk Percentage of Balance (1%-2%)
   LOT_FIXED = 1          // Fixed Lot Size
  };

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                 |
//+------------------------------------------------------------------+
input group "=== 1. General & Magic Settings ==="
input ulong             InpMagicNumber          = 555888;         // EA Magic Number
input string            InpTradeComment         = "GoldM5_Secret"; // Order Comment
input ENUM_ENTRY_TYPE   InpEntryType            = ENTRY_ALL;      // Entry Setup Selection

input group "=== 2. Indicator & Trend Settings ==="
input int               InpFastEMAPeriod        = 50;             // Fast EMA Period (Default: 50)
input int               InpSlowEMAPeriod        = 150;            // Slow EMA Period (Default: 150)
input ENUM_MA_METHOD    InpMAMethod             = MODE_EMA;       // MA Method
input ENUM_APPLIED_PRICE InpAppliedPrice        = PRICE_CLOSE;    // Applied Price
input double            InpMinSlopePoints       = 30.0;           // Min EMA Slope in Points (Slope Filter)
input int               InpSlopeBarsLookback    = 3;              // Bars to Calculate Slope
input double            InpMaxExhaustionDist    = 4000.0;         // Max Distance from Slow EMA (Exhaustion Filter in Points)
input int               InpTangleLookbackBars   = 10;             // Bars to check EMA cross tangle (Sideway Filter)

input group "=== 3. Higher Timeframe (HTF) Filter ==="
input bool              InpUseHTFFilter         = true;           // Enable HTF Macro Trend Filter
input ENUM_TIMEFRAMES   InpHTFTimeframe         = PERIOD_H1;      // HTF Timeframe (e.g. H1)
input int               InpHTF_EMAPeriod        = 200;            // HTF EMA Period (Default: 200)

input group "=== 4. Price Action & Entry Quality ==="
input double            InpMaxUpperWickBuy      = 0.40;           // Max Upper Wick Ratio for Buy Reversal (0.0-1.0)
input double            InpMaxLowerWickSell     = 0.40;           // Max Lower Wick Ratio for Sell Reversal (0.0-1.0)
input double            InpMinBodyPoints        = 50.0;           // Min Candle Body Size in Points
input double            InpMaxEntryDistFromEMA  = 600.0;          // Max Entry Distance from EMA (Points)
input int               InpSwingBars            = 12;             // Swing High/Low Lookback for Breakout
input double            InpPullbackEMABuffer    = 100.0;          // Pullback Proximity Buffer to EMA (Points)

input group "=== 5. Risk & Money Management ==="
input ENUM_LOT_MODE     InpLotMode              = LOT_RISK_PERCENT;// Lot Calculation Mode
input double            InpRiskPercent          = 1.0;            // Risk Per Trade (% of Balance)
input double            InpFixedLotSize         = 0.05;           // Fixed Lot Size (if Fixed Mode)
input ENUM_SL_TYPE      InpSLType               = SL_SWING_HIGH_LOW;// Stop Loss Calculation Method
input int               InpSLSwingBars          = 7;              // Swing Bars for SL Calculation
input double            InpSLBufferPoints       = 50.0;           // Additional SL Buffer (Points)
input double            InpMinSLPoints          = 150.0;          // Minimum Stop Loss (Points)
input double            InpMaxSLPoints          = 1200.0;         // Maximum Stop Loss (Points)
input double            InpRiskRewardRatio      = 1.0;            // Take Profit 1 Risk:Reward (Default: 1.0)

input group "=== 6. Multi-Order & Run Trend Settings ==="
input bool              InpEnableMultiOrder     = true;           // Enable 2nd Runner Position
input double            InpPos1_LotRatio        = 0.50;           // Position 1 Volume Ratio (Scalp TP 1:1)
input double            InpPos2_LotRatio        = 0.50;           // Position 2 Volume Ratio (Runner)
input bool              InpMoveBE_OnTP1         = true;           // Move Pos2 SL to Break-Even when Pos1 Hits TP
input double            InpBE_BufferPoints      = 30.0;           // Break-Even Lock-in Profit (Points)
input bool              InpUseTrailingOnRunner  = true;           // Use Trailing Stop on Runner Position
input bool              InpTrailByEMA           = true;           // Trail SL behind Fast EMA 50 (if false, by Points)
input double            InpTrailPoints          = 300.0;          // Fixed Trailing Points (if not by EMA)
input double            InpTrailStepPoints      = 50.0;           // Trailing Step in Points

input group "=== 7. Safety & Drawdown Controls ==="
input int               InpConsecutiveLossLimit = 2;              // Max Consecutive Losses before Pause
input int               InpPauseHoursOnLoss     = 4;              // Hours to Pause Trading after Loss Limit
input bool              InpDynamicLotReduction  = true;           // Enable Dynamic Lot Reduction after Loss
input double            InpDailyTargetPercent   = 5.0;            // Daily Profit Target Stop (%)
input double            InpDailyMaxLossPercent  = 3.0;            // Daily Max Loss Limit (%)
input double            InpMaxSpreadPoints      = 35.0;           // Maximum Allowed Spread (Points / Pipette)
input int               InpCooldownBars         = 2;              // Cooldown Bars after Position Close

input group "=== 8. Trading Session / Time Filter ==="
input bool              InpUseTimeFilter        = true;           // Enable Session Time Filter
input string            InpSessionStart         = "07:00";        // Trading Session Start (HH:MM Server Time)
input string            InpSessionEnd           = "21:00";        // Trading Session End (HH:MM Server Time)

input group "=== 9. Visual HUD Dashboard ==="
input bool              InpShowHUD              = true;           // Display On-Chart Live Dashboard
input color             InpHUD_BgColor          = C'15,20,30';    // HUD Background Color
input color             InpHUD_TextColor        = clrWhite;       // HUD Text Color

//+------------------------------------------------------------------+
//| GLOBAL VARIABLES & OBJECTS                                       |
//+------------------------------------------------------------------+
CTrade            trade;
CPositionInfo     posInfo;
CAccountInfo      accInfo;
COrderInfo        ordInfo;

//--- Indicator Handles
int               hFastEMA = INVALID_HANDLE;
int               hSlowEMA = INVALID_HANDLE;
int               hHTF_EMA = INVALID_HANDLE;

//--- State Tracking
datetime          lastBarTime = 0;
datetime          pauseUntilTime = 0;
int               consecutiveLosses = 0;
int               consecutiveWins = 0;
datetime          lastTradeClosedTime = 0;
int               lastClosedBarIndex = -1;
double            dayStartingEquity = 0.0;
datetime          currentDayTime = 0;
bool              dailyTargetReached = false;
bool              dailyMaxLossReached = false;

//--- Sub Magic Numbers for Multi-Order separation
ulong             magicPos1 = 0;
ulong             magicPos2 = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   // Set magic numbers
   magicPos1 = InpMagicNumber + 1;
   magicPos2 = InpMagicNumber + 2;
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);

   // Initialize Indicator Handles
   hFastEMA = iMA(_Symbol, _Period, InpFastEMAPeriod, 0, InpMAMethod, InpAppliedPrice);
   if(hFastEMA == INVALID_HANDLE)
     {
      Print("Error creating Fast EMA handle: ", GetLastError());
      return INIT_FAILED;
     }

   hSlowEMA = iMA(_Symbol, _Period, InpSlowEMAPeriod, 0, InpMAMethod, InpAppliedPrice);
   if(hSlowEMA == INVALID_HANDLE)
     {
      Print("Error creating Slow EMA handle: ", GetLastError());
      return INIT_FAILED;
     }

   if(InpUseHTFFilter)
     {
      hHTF_EMA = iMA(_Symbol, InpHTFTimeframe, InpHTF_EMAPeriod, 0, InpMAMethod, InpAppliedPrice);
      if(hHTF_EMA == INVALID_HANDLE)
        {
         Print("Error creating HTF EMA handle: ", GetLastError());
         return INIT_FAILED;
        }
     }

   // Initialize daily balance
   InitDailyTracking();

   // Recalculate historical consecutive losses for safety persistence
   CheckHistoricalConsecutiveStats();

   Print("XAUUSD Scalping M5 (Secret System) EA Initialized Successfully.");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   // Release handles
   if(hFastEMA != INVALID_HANDLE) IndicatorRelease(hFastEMA);
   if(hSlowEMA != INVALID_HANDLE) IndicatorRelease(hSlowEMA);
   if(hHTF_EMA != INVALID_HANDLE) IndicatorRelease(hHTF_EMA);

   // Clean up Chart Objects
   ObjectsDeleteAll(0, "HUD_");
   Comment("");
  }

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   // Check new day reset
   CheckNewDay();

   // Manage Active Positions (Break-Even, Trailing Stop, Exit rules)
   ManageOpenPositions();

   // Update HUD Dashboard
   if(InpShowHUD)
      DrawHUD();

   // Check if a new M5 Bar has opened (Execute Strategy at Bar Close)
   datetime currentBarTime = iTime(_Symbol, _Period, 0);
   if(currentBarTime == lastBarTime)
      return; // Wait for bar completion

   // --- STRATEGY EXECUTION ON NEW BAR (Bar 1 is newly closed) ---
   ProcessStrategy();

   // Update bar time tracker
   lastBarTime = currentBarTime;
  }

//+------------------------------------------------------------------+
//| Core Strategy Logic on Bar Close                                 |
//+------------------------------------------------------------------+
void ProcessStrategy()
  {
   // 1. Safety Filters Checks
   if(!IsTradingAllowedSafety())
      return;

   // 2. Check Spread (Auto-scale for 2-digit vs 3-digit Gold)
   double spread = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   double maxSpread = InpMaxSpreadPoints;
   if(_Digits == 3 && maxSpread < 150.0) maxSpread *= 10.0;
   if(spread > maxSpread)
     {
      PrintFormat("Trade Skipped: Spread (%.1f) exceeds maximum allowed (%.1f)", spread, maxSpread);
      return;
     }

   // 3. Check Session Time Filter
   if(InpUseTimeFilter && !IsInsideTradingSession())
     {
      return;
     }

   // 4. Check Maximum Positions Allowed (1 active set at a time)
   if(HasOpenEAOrders())
      return;

   // 5. Fetch Indicator Data
   double fastEMA[], slowEMA[];
   ArraySetAsSeries(fastEMA, true);
   ArraySetAsSeries(slowEMA, true);

   if(CopyBuffer(hFastEMA, 0, 0, InpSlopeBarsLookback + 5, fastEMA) <= 0 ||
      CopyBuffer(hSlowEMA, 0, 0, InpSlopeBarsLookback + 5, slowEMA) <= 0)
     {
      Print("Failed to copy EMA buffers.");
      return;
     }

   // Fetch Price Bars
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, InpSwingBars + 5, rates) <= 0)
     {
      Print("Failed to copy price rates.");
      return;
     }

   // 6. Trend Identification & Slope Logic
   bool isBullishTrend = false;
   bool isBearishTrend = false;
   bool isSidewayOrExhausted = false;

   CheckTrendConditions(fastEMA, slowEMA, rates, isBullishTrend, isBearishTrend, isSidewayOrExhausted);

   if(isSidewayOrExhausted)
      return; // No trade during Sideway or Exhaustion

   // 7. Higher Timeframe Filter (HTF Trend)
   if(InpUseHTFFilter)
     {
      double htfEMA[];
      ArraySetAsSeries(htfEMA, true);
      if(CopyBuffer(hHTF_EMA, 0, 0, 2, htfEMA) > 0)
        {
         MqlRates htfRates[];
         ArraySetAsSeries(htfRates, true);
         if(CopyRates(_Symbol, InpHTFTimeframe, 0, 2, htfRates) > 0)
           {
            if(isBullishTrend && htfRates[1].close < htfEMA[1])
               return; // HTF is below EMA 200, skip Buy
            if(isBearishTrend && htfRates[1].close > htfEMA[1])
               return; // HTF is above EMA 200, skip Sell
           }
        }
     }

   // 8. Evaluate Entry Setups
   bool buySignal = false;
   bool sellSignal = false;
   string signalReason = "";

   // --- BUY SIGNAL EVALUATION ---
   if(isBullishTrend)
     {
      // Setup A: Pullback / Retest
      if(InpEntryType == ENTRY_ALL || InpEntryType == ENTRY_PULLBACK_ONLY)
        {
         if(CheckBuyPullbackSetup(rates, fastEMA, slowEMA))
           {
            buySignal = true;
            signalReason = "Buy Pullback / Retest at EMA";
           }
        }

      // Setup B: Breakout
      if(!buySignal && (InpEntryType == ENTRY_ALL || InpEntryType == ENTRY_BREAKOUT_ONLY))
        {
         if(CheckBuyBreakoutSetup(rates))
           {
            buySignal = true;
            signalReason = "Buy Breakout above Swing High";
           }
        }
     }

   // --- SELL SIGNAL EVALUATION ---
   if(isBearishTrend)
     {
      // Setup A: Pullback / Retest
      if(InpEntryType == ENTRY_ALL || InpEntryType == ENTRY_PULLBACK_ONLY)
        {
         if(CheckSellPullbackSetup(rates, fastEMA, slowEMA))
           {
            sellSignal = true;
            signalReason = "Sell Pullback / Retest at EMA";
           }
        }

      // Setup B: Breakout
      if(!sellSignal && (InpEntryType == ENTRY_ALL || InpEntryType == ENTRY_BREAKOUT_ONLY))
        {
         if(CheckSellBreakoutSetup(rates))
           {
            sellSignal = true;
            signalReason = "Sell Breakout below Swing Low";
           }
        }
     }

   // 9. Execute Trades
   if(buySignal)
     {
      ExecuteBuyOrder(rates, fastEMA, slowEMA, signalReason);
     }
   else if(sellSignal)
     {
      ExecuteSellOrder(rates, fastEMA, slowEMA, signalReason);
     }
  }

//+------------------------------------------------------------------+
//| Trend & Slope Identification                                     |
//+------------------------------------------------------------------+
void CheckTrendConditions(const double &fastEMA[], const double &slowEMA[], const MqlRates &rates[],
                          bool &isBullish, bool &isBearish, bool &isSideway)
  {
   isBullish = false;
   isBearish = false;
   isSideway = false;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int lookback = InpSlopeBarsLookback;

   // 1. Calculate Slopes in Points
   double fastSlope = (fastEMA[1] - fastEMA[1 + lookback]) / point;
   double slowSlope = (slowEMA[1] - slowEMA[1 + lookback]) / point;

   // 2. Trend Direction
   bool fastAboveSlow = (fastEMA[1] > slowEMA[1]);
   bool fastBelowSlow = (fastEMA[1] < slowEMA[1]);

   // 3. Slope Threshold Check
   bool fastSlopingUp   = (fastSlope >= InpMinSlopePoints);
   bool slowSlopingUp   = (slowSlope >= (InpMinSlopePoints * 0.4)); // Slow EMA slope threshold is lower
   bool fastSlopingDown = (fastSlope <= -InpMinSlopePoints);
   bool slowSlopingDown = (slowSlope <= -(InpMinSlopePoints * 0.4));

   // 4. Sideway & Tangle Check: Count EMA Crosses in recent bars
   int crossCount = 0;
   for(int i = 1; i <= InpTangleLookbackBars; i++)
     {
      if((fastEMA[i] > slowEMA[i] && fastEMA[i+1] <= slowEMA[i+1]) ||
         (fastEMA[i] < slowEMA[i] && fastEMA[i+1] >= slowEMA[i+1]))
        {
         crossCount++;
        }
     }

   if(crossCount >= 2)
     {
      isSideway = true; // EMAs are tangled / crossing back and forth
      return;
     }

   // 5. Exhaustion Filter: Price is overextended from Slow EMA
   double distFromSlowEMA = MathAbs(rates[1].close - slowEMA[1]) / point;
   if(distFromSlowEMA > InpMaxExhaustionDist)
     {
      isSideway = true; // Exhaustion mode: Market has traveled too far, wait for consolidation
      return;
     }

   // 6. Final Trend Classification
   if(fastAboveSlow && fastSlopingUp && slowSlopingUp)
     {
      isBullish = true;
     }
   else if(fastBelowSlow && fastSlopingDown && slowSlopingDown)
     {
      isBearish = true;
     }
   else
     {
      isSideway = true; // Flat or conflicting slopes
     }
  }

//+------------------------------------------------------------------+
//| Buy Setup: Pullback / Retest at EMA                              |
//+------------------------------------------------------------------+
bool CheckBuyPullbackSetup(const MqlRates &rates[], const double &fastEMA[], const double &slowEMA[])
  {
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double buffer = InpPullbackEMABuffer * point;

   // 1. Bar 1 must be Bullish
   if(rates[1].close <= rates[1].open)
      return false;

   // 2. Bar 1 touched or came within buffer of EMA 50 or EMA 150
   bool touchedFastEMA = (rates[1].low <= (fastEMA[1] + buffer) && rates[1].close > fastEMA[1]);
   bool touchedSlowEMA = (rates[1].low <= (slowEMA[1] + buffer) && rates[1].close > slowEMA[1]);

   if(!touchedFastEMA && !touchedSlowEMA)
      return false;

   // 3. Reversal Price Action Quality
   double candleRange = rates[1].high - rates[1].low;
   double bodySize = rates[1].close - rates[1].open;
   double upperWick = rates[1].high - rates[1].close;

   if(candleRange <= 0 || (bodySize / point) < InpMinBodyPoints)
      return false;

   // Upper wick must not be excessively long (rejecting top)
   if((upperWick / candleRange) > InpMaxUpperWickBuy)
      return false;

   // 4. Close not too far from EMA
   double refEMA = touchedFastEMA ? fastEMA[1] : slowEMA[1];
   if(((rates[1].close - refEMA) / point) > InpMaxEntryDistFromEMA)
      return false;

   return true;
  }

//+------------------------------------------------------------------+
//| Buy Setup: Breakout above Swing High                             |
//+------------------------------------------------------------------+
bool CheckBuyBreakoutSetup(const MqlRates &rates[])
  {
   double swingHigh = -1.0;
   // Find Swing High in the prior N bars (excluding bar 1)
   for(int i = 2; i <= InpSwingBars; i++)
     {
      if(rates[i].high > swingHigh)
         swingHigh = rates[i].high;
     }

   if(swingHigh <= 0)
      return false;

   // Breakout condition: Bar 1 closed above Swing High, but Bar 2 was below/equal
   if(rates[1].close > swingHigh && rates[2].close <= swingHigh)
     {
      // Bullish bar confirmation
      if(rates[1].close > rates[1].open)
         return true;
     }

   return false;
  }

//+------------------------------------------------------------------+
//| Sell Setup: Pullback / Retest at EMA                             |
//+------------------------------------------------------------------+
bool CheckSellPullbackSetup(const MqlRates &rates[], const double &fastEMA[], const double &slowEMA[])
  {
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double buffer = InpPullbackEMABuffer * point;

   // 1. Bar 1 must be Bearish
   if(rates[1].close >= rates[1].open)
      return false;

   // 2. Bar 1 touched or came within buffer of EMA 50 or EMA 150
   bool touchedFastEMA = (rates[1].high >= (fastEMA[1] - buffer) && rates[1].close < fastEMA[1]);
   bool touchedSlowEMA = (rates[1].high >= (slowEMA[1] - buffer) && rates[1].close < slowEMA[1]);

   if(!touchedFastEMA && !touchedSlowEMA)
      return false;

   // 3. Reversal Price Action Quality
   double candleRange = rates[1].high - rates[1].low;
   double bodySize = rates[1].open - rates[1].close;
   double lowerWick = rates[1].close - rates[1].low;

   if(candleRange <= 0 || (bodySize / point) < InpMinBodyPoints)
      return false;

   // Lower wick must not be excessively long (rejecting bottom)
   if((lowerWick / candleRange) > InpMaxLowerWickSell)
      return false;

   // 4. Close not too far from EMA
   double refEMA = touchedFastEMA ? fastEMA[1] : slowEMA[1];
   if(((refEMA - rates[1].close) / point) > InpMaxEntryDistFromEMA)
      return false;

   return true;
  }

//+------------------------------------------------------------------+
//| Sell Setup: Breakout below Swing Low                             |
//+------------------------------------------------------------------+
bool CheckSellBreakoutSetup(const MqlRates &rates[])
  {
   double swingLow = DBL_MAX;
   // Find Swing Low in the prior N bars (excluding bar 1)
   for(int i = 2; i <= InpSwingBars; i++)
     {
      if(rates[i].low < swingLow)
         swingLow = rates[i].low;
     }

   if(swingLow >= DBL_MAX)
      return false;

   // Breakout condition: Bar 1 closed below Swing Low, but Bar 2 was above/equal
   if(rates[1].close < swingLow && rates[2].close >= swingLow)
     {
      // Bearish bar confirmation
      if(rates[1].close < rates[1].open)
         return true;
     }

   return false;
  }

//+------------------------------------------------------------------+
//| Execute Buy Orders (Multi-Order Supported)                       |
//+------------------------------------------------------------------+
void ExecuteBuyOrder(const MqlRates &rates[], const double &fastEMA[], const double &slowEMA[], string reason)
  {
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   // Calculate Stop Loss
   double slPrice = 0.0;
   if(InpSLType == SL_SWING_HIGH_LOW)
     {
      double lowestLow = rates[1].low;
      for(int i = 1; i <= InpSLSwingBars; i++)
        {
         if(rates[i].low < lowestLow) lowestLow = rates[i].low;
        }
      slPrice = lowestLow - (InpSLBufferPoints * point);
     }
   else if(InpSLType == SL_CANDLE_HIGH_LOW)
     {
      slPrice = rates[1].low - (InpSLBufferPoints * point);
     }
   else if(InpSLType == SL_EMA_LINE)
     {
      double baseEMA = MathMin(fastEMA[1], slowEMA[1]);
      slPrice = baseEMA - (InpSLBufferPoints * point);
     }

   // Validate SL distance
   double slDistPoints = (ask - slPrice) / point;
   if(slDistPoints < InpMinSLPoints)
     {
      slPrice = ask - (InpMinSLPoints * point);
      slDistPoints = InpMinSLPoints;
     }
   if(slDistPoints > InpMaxSLPoints)
     {
      slPrice = ask - (InpMaxSLPoints * point);
      slDistPoints = InpMaxSLPoints;
     }

   slPrice = NormalizeDouble(slPrice, digits);

   // Take Profit 1: 1:1 RR
   double tp1Price = NormalizeDouble(ask + (slDistPoints * InpRiskRewardRatio * point), digits);

   // Calculate Lot Sizes
   double totalLot = CalculateLotSize(slDistPoints);
   if(totalLot <= 0) return;

   if(InpEnableMultiOrder)
     {
      double lot1 = NormalizeLot(totalLot * InpPos1_LotRatio);
      double lot2 = NormalizeLot(totalLot * InpPos2_LotRatio);

      // Order 1 (Scalp TP 1:1)
      trade.SetExpertMagicNumber(magicPos1);
      string comment1 = InpTradeComment + "_P1";
      trade.Buy(lot1, _Symbol, ask, slPrice, tp1Price, comment1);

      // Order 2 (Runner - Run Trend with Trailing)
      trade.SetExpertMagicNumber(magicPos2);
      string comment2 = InpTradeComment + "_P2";
      // Runner has no fixed TP (or huge TP) so it trails
      trade.Buy(lot2, _Symbol, ask, slPrice, 0.0, comment2);

      PrintFormat("BUY Multi-Order Opened [%s]: Lot1=%.2f (TP=%.2f), Lot2=%.2f (Runner), SL=%.2f", 
                  reason, lot1, tp1Price, lot2, slPrice);
     }
   else
     {
      trade.SetExpertMagicNumber(InpMagicNumber);
      trade.Buy(totalLot, _Symbol, ask, slPrice, tp1Price, InpTradeComment);
      PrintFormat("BUY Single Order Opened [%s]: Lot=%.2f, SL=%.2f, TP=%.2f", reason, totalLot, slPrice, tp1Price);
     }
  }

//+------------------------------------------------------------------+
//| Execute Sell Orders (Multi-Order Supported)                      |
//+------------------------------------------------------------------+
void ExecuteSellOrder(const MqlRates &rates[], const double &fastEMA[], const double &slowEMA[], string reason)
  {
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   // Calculate Stop Loss
   double slPrice = 0.0;
   if(InpSLType == SL_SWING_HIGH_LOW)
     {
      double highestHigh = rates[1].high;
      for(int i = 1; i <= InpSLSwingBars; i++)
        {
         if(rates[i].high > highestHigh) highestHigh = rates[i].high;
        }
      slPrice = highestHigh + (InpSLBufferPoints * point);
     }
   else if(InpSLType == SL_CANDLE_HIGH_LOW)
     {
      slPrice = rates[1].high + (InpSLBufferPoints * point);
     }
   else if(InpSLType == SL_EMA_LINE)
     {
      double baseEMA = MathMax(fastEMA[1], slowEMA[1]);
      slPrice = baseEMA + (InpSLBufferPoints * point);
     }

   // Validate SL distance
   double slDistPoints = (slPrice - bid) / point;
   if(slDistPoints < InpMinSLPoints)
     {
      slPrice = bid + (InpMinSLPoints * point);
      slDistPoints = InpMinSLPoints;
     }
   if(slDistPoints > InpMaxSLPoints)
     {
      slPrice = bid + (InpMaxSLPoints * point);
      slDistPoints = InpMaxSLPoints;
     }

   slPrice = NormalizeDouble(slPrice, digits);

   // Take Profit 1: 1:1 RR
   double tp1Price = NormalizeDouble(bid - (slDistPoints * InpRiskRewardRatio * point), digits);

   // Calculate Lot Sizes
   double totalLot = CalculateLotSize(slDistPoints);
   if(totalLot <= 0) return;

   if(InpEnableMultiOrder)
     {
      double lot1 = NormalizeLot(totalLot * InpPos1_LotRatio);
      double lot2 = NormalizeLot(totalLot * InpPos2_LotRatio);

      // Order 1 (Scalp TP 1:1)
      trade.SetExpertMagicNumber(magicPos1);
      string comment1 = InpTradeComment + "_P1";
      trade.Sell(lot1, _Symbol, bid, slPrice, tp1Price, comment1);

      // Order 2 (Runner - Run Trend with Trailing)
      trade.SetExpertMagicNumber(magicPos2);
      string comment2 = InpTradeComment + "_P2";
      trade.Sell(lot2, _Symbol, bid, slPrice, 0.0, comment2);

      PrintFormat("SELL Multi-Order Opened [%s]: Lot1=%.2f (TP=%.2f), Lot2=%.2f (Runner), SL=%.2f", 
                  reason, lot1, tp1Price, lot2, slPrice);
     }
   else
     {
      trade.SetExpertMagicNumber(InpMagicNumber);
      trade.Sell(totalLot, _Symbol, bid, slPrice, tp1Price, InpTradeComment);
      PrintFormat("SELL Single Order Opened [%s]: Lot=%.2f, SL=%.2f, TP=%.2f", reason, totalLot, slPrice, tp1Price);
     }
  }

//+------------------------------------------------------------------+
//| Manage Open Positions (Break-Even, Trailing Stop, Opposite Exit) |
//+------------------------------------------------------------------+
void ManageOpenPositions()
  {
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   // Get Fast EMA for Trailing
   double fastEMA[];
   ArraySetAsSeries(fastEMA, true);
   bool haveFastEMA = (CopyBuffer(hFastEMA, 0, 0, 3, fastEMA) > 0);

   // Check if Position 1 is closed to trigger BE on Position 2
   bool pos1Exists = false;
   bool pos2Exists = false;
   ulong pos2Ticket = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!posInfo.SelectByIndex(i)) continue;
      if(posInfo.Symbol() != _Symbol) continue;

      ulong mag = posInfo.Magic();
      if(mag == magicPos1) pos1Exists = true;
      if(mag == magicPos2)
        {
         pos2Exists = true;
         pos2Ticket = posInfo.Ticket();
        }
     }

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!posInfo.SelectByIndex(i)) continue;
      if(posInfo.Symbol() != _Symbol) continue;

      ulong mag = posInfo.Magic();
      if(mag != InpMagicNumber && mag != magicPos1 && mag != magicPos2) continue;

      ENUM_POSITION_TYPE posType = posInfo.PositionType();
      double openPrice = posInfo.PriceOpen();
      double currentSL = posInfo.StopLoss();
      double currentPrice = (posType == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      // --- Runner Position Management (magicPos2) ---
      if(mag == magicPos2)
        {
         // 1. Move to Break-Even if Position 1 is already closed (hit TP1)
         if(!pos1Exists && InpMoveBE_OnTP1)
           {
            if(posType == POSITION_TYPE_BUY)
              {
               double bePrice = NormalizeDouble(openPrice + (InpBE_BufferPoints * point), digits);
               if(currentSL < openPrice && currentPrice > bePrice)
                 {
                  trade.SetExpertMagicNumber(magicPos2);
                  trade.PositionModify(posInfo.Ticket(), bePrice, posInfo.TakeProfit());
                  PrintFormat("Runner Pos2 SL moved to Break-Even: %.2f", bePrice);
                 }
              }
            else if(posType == POSITION_TYPE_SELL)
              {
               double bePrice = NormalizeDouble(openPrice - (InpBE_BufferPoints * point), digits);
               if((currentSL > openPrice || currentSL == 0) && currentPrice < bePrice)
                 {
                  trade.SetExpertMagicNumber(magicPos2);
                  trade.PositionModify(posInfo.Ticket(), bePrice, posInfo.TakeProfit());
                  PrintFormat("Runner Pos2 SL moved to Break-Even: %.2f", bePrice);
                 }
              }
           }

         // 2. Trailing Stop on Runner
         if(InpUseTrailingOnRunner && haveFastEMA)
           {
            if(posType == POSITION_TYPE_BUY)
              {
               double newSL = 0.0;
               if(InpTrailByEMA)
                 {
                  newSL = NormalizeDouble(fastEMA[1] - (InpSLBufferPoints * point), digits);
                 }
               else
                 {
                  if(currentPrice - openPrice > InpTrailPoints * point)
                     newSL = NormalizeDouble(currentPrice - (InpTrailPoints * point), digits);
                 }

               // Only trail upward
               if(newSL > currentSL + (InpTrailStepPoints * point) && newSL < currentPrice)
                 {
                  trade.SetExpertMagicNumber(magicPos2);
                  trade.PositionModify(posInfo.Ticket(), newSL, posInfo.TakeProfit());
                 }
              }
            else if(posType == POSITION_TYPE_SELL)
              {
               double newSL = 0.0;
               if(InpTrailByEMA)
                 {
                  newSL = NormalizeDouble(fastEMA[1] + (InpSLBufferPoints * point), digits);
                 }
               else
                 {
                  if(openPrice - currentPrice > InpTrailPoints * point)
                     newSL = NormalizeDouble(currentPrice + (InpTrailPoints * point), digits);
                 }

               // Only trail downward
               if((currentSL == 0 || newSL < currentSL - (InpTrailStepPoints * point)) && newSL > currentPrice)
                 {
                  trade.SetExpertMagicNumber(magicPos2);
                  trade.PositionModify(posInfo.Ticket(), newSL, posInfo.TakeProfit());
                 }
              }
           }

         // 3. Exit Runner when Price Closes across Opposite EMA (Bar close check)
         if(haveFastEMA)
           {
            MqlRates r[];
            ArraySetAsSeries(r, true);
            if(CopyRates(_Symbol, _Period, 0, 2, r) > 0)
              {
               if(posType == POSITION_TYPE_BUY && r[1].close < fastEMA[1])
                 {
                  trade.SetExpertMagicNumber(magicPos2);
                  trade.PositionClose(posInfo.Ticket());
                  Print("Runner Pos2 closed due to opposite close below Fast EMA.");
                 }
               else if(posType == POSITION_TYPE_SELL && r[1].close > fastEMA[1])
                 {
                  trade.SetExpertMagicNumber(magicPos2);
                  trade.PositionClose(posInfo.Ticket());
                  Print("Runner Pos2 closed due to opposite close above Fast EMA.");
                 }
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Calculate Lot Size with Risk Management & Dynamic Reduction      |
//+------------------------------------------------------------------+
double CalculateLotSize(double slDistPoints)
  {
   double lot = InpFixedLotSize;

   if(InpLotMode == LOT_RISK_PERCENT)
     {
      double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      double riskMoney = balance * (InpRiskPercent / 100.0);
      double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      double point     = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

      if(tickSize > 0 && tickValue > 0 && slDistPoints > 0)
        {
         double pointsPerTick = tickSize / point;
         double moneyPerLotForSL = (slDistPoints / pointsPerTick) * tickValue;
         if(moneyPerLotForSL > 0)
            lot = riskMoney / moneyPerLotForSL;
        }
     }

   // Dynamic Lot Reduction Logic after Loss
   if(InpDynamicLotReduction)
     {
      if(consecutiveLosses == 1)
        {
         lot *= 0.50; // Cut lot by half after 1 loss
        }
      else if(consecutiveLosses >= 2)
        {
         lot *= 0.25; // Cut lot further after consecutive losses
        }
     }

   return NormalizeLot(lot);
  }

//+------------------------------------------------------------------+
//| Normalize Lot Size within Symbol Limits                          |
//+------------------------------------------------------------------+
double NormalizeLot(double lot)
  {
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(lotStep <= 0) lotStep = 0.01;

   lot = MathFloor(lot / lotStep) * lotStep;

   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;

   return NormalizeDouble(lot, 2);
  }

//+------------------------------------------------------------------+
//| Safety & Protection Checks                                       |
//+------------------------------------------------------------------+
bool IsTradingAllowedSafety()
  {
   // Check Pause Time from Consecutive Losses
   if(pauseUntilTime > 0 && TimeCurrent() < pauseUntilTime)
     {
      return false;
     }

   // Check Daily Target
   if(dailyTargetReached || dailyMaxLossReached)
     {
      return false;
     }

   // Check Account Trade Allowed
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
     {
      return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| Check Historical Consecutive Stats & Trade Results               |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   // Monitor closed deals to update win/loss counters
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
     {
      ulong dealTicket = trans.deal;
      if(HistoryDealSelect(dealTicket))
        {
         long dealEntry = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
         if(dealEntry == DEAL_ENTRY_OUT)
           {
            ulong dealMagic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);
            if(dealMagic == InpMagicNumber || dealMagic == magicPos1 || dealMagic == magicPos2)
              {
               double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
               profit += HistoryDealGetDouble(dealTicket, DEAL_SWAP) + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);

               if(profit < 0)
                 {
                  consecutiveLosses++;
                  consecutiveWins = 0;
                  PrintFormat("Trade Closed with LOSS ($%.2f). Consecutive Losses = %d", profit, consecutiveLosses);

                  // Consecutive Loss Pause Check
                  if(consecutiveLosses >= InpConsecutiveLossLimit)
                    {
                     pauseUntilTime = TimeCurrent() + (InpPauseHoursOnLoss * 3600);
                     PrintFormat("Consecutive Loss Limit reached (%d). Trading paused until %s", 
                                 consecutiveLosses, TimeToString(pauseUntilTime, TIME_DATE|TIME_MINUTES));
                    }
                 }
               else if(profit > 0)
                 {
                  consecutiveWins++;
                  if(consecutiveWins >= 2)
                    {
                     consecutiveLosses = 0; // Reset consecutive losses after 2 wins
                    }
                  PrintFormat("Trade Closed with PROFIT ($%.2f). Consecutive Wins = %d", profit, consecutiveWins);
                 }

               lastTradeClosedTime = TimeCurrent();
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Initialize / Check Daily Stats and Targets                       |
//+------------------------------------------------------------------+
void InitDailyTracking()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   currentDayTime = StructToTime(dt);
   dayStartingEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   dailyTargetReached = false;
   dailyMaxLossReached = false;
  }

void CheckNewDay()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   datetime todayStart = StructToTime(dt);

   if(todayStart != currentDayTime)
     {
      currentDayTime = todayStart;
      dayStartingEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      dailyTargetReached = false;
      dailyMaxLossReached = false;
      pauseUntilTime = 0;
      Print("New Day Detected. Daily PnL trackers and Pause timers reset.");
     }

   // Calculate Today's Realized Profit
   double todayProfit = GetTodayClosedProfit();
   if(dayStartingEquity > 0)
     {
      double profitPercent = (todayProfit / dayStartingEquity) * 100.0;

      if(profitPercent >= InpDailyTargetPercent && !dailyTargetReached)
        {
         dailyTargetReached = true;
         PrintFormat("Daily Target Hit (+%.2f%% / $%.2f). Bot stopped for today.", profitPercent, todayProfit);
        }
      else if(profitPercent <= -InpDailyMaxLossPercent && !dailyMaxLossReached)
        {
         dailyMaxLossReached = true;
         PrintFormat("Daily Max Loss Hit (%.2f%% / $%.2f). Bot stopped for today.", profitPercent, todayProfit);
        }
     }
  }

//+------------------------------------------------------------------+
//| Get Total Closed Profit for Today                                |
//+------------------------------------------------------------------+
double GetTodayClosedProfit()
  {
   double total = 0.0;
   if(HistorySelect(currentDayTime, TimeCurrent()))
     {
      int deals = HistoryDealsTotal();
      for(int i = 0; i < deals; i++)
        {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket > 0)
           {
            ulong dealMagic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
            if(dealMagic == InpMagicNumber || dealMagic == magicPos1 || dealMagic == magicPos2)
              {
               total += HistoryDealGetDouble(ticket, DEAL_PROFIT);
               total += HistoryDealGetDouble(ticket, DEAL_SWAP) + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
              }
           }
        }
     }
   return total;
  }

//+------------------------------------------------------------------+
//| Check Historical Consecutive Stats on startup                    |
//+------------------------------------------------------------------+
void CheckHistoricalConsecutiveStats()
  {
   consecutiveLosses = 0;
   consecutiveWins = 0;

   datetime fromDate = TimeCurrent() - (7 * 86400); // Last 7 days
   if(HistorySelect(fromDate, TimeCurrent()))
     {
      int deals = HistoryDealsTotal();
      for(int i = deals - 1; i >= 0; i--)
        {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket > 0 && HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_OUT)
           {
            ulong dealMagic = HistoryDealGetInteger(ticket, DEAL_MAGIC);
            if(dealMagic == InpMagicNumber || dealMagic == magicPos1 || dealMagic == magicPos2)
              {
               double pnl = HistoryDealGetDouble(ticket, DEAL_PROFIT);
               if(pnl < 0)
                 {
                  if(consecutiveWins == 0) consecutiveLosses++;
                  else break;
                 }
               else if(pnl > 0)
                 {
                  if(consecutiveLosses == 0) consecutiveWins++;
                  else break;
                 }
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Check if Inside Allowed Trading Session                          |
//+------------------------------------------------------------------+
bool IsInsideTradingSession()
  {
   string currTime = TimeToString(TimeCurrent(), TIME_MINUTES);
   if(StringCompare(InpSessionStart, InpSessionEnd) <= 0)
     {
      return (StringCompare(currTime, InpSessionStart) >= 0 && StringCompare(currTime, InpSessionEnd) <= 0);
     }
   else // Over midnight session
     {
      return (StringCompare(currTime, InpSessionStart) >= 0 || StringCompare(currTime, InpSessionEnd) <= 0);
     }
  }

//+------------------------------------------------------------------+
//| Check if Bot already has Open Orders                             |
//+------------------------------------------------------------------+
bool HasOpenEAOrders()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!posInfo.SelectByIndex(i)) continue;
      if(posInfo.Symbol() != _Symbol) continue;
      ulong mag = posInfo.Magic();
      if(mag == InpMagicNumber || mag == magicPos1 || mag == magicPos2)
         return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| On-Chart Visual Live HUD Dashboard                               |
//+------------------------------------------------------------------+
void DrawHUD()
  {
   double spread = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   double todayPnL = GetTodayClosedProfit();
   double pnlPercent = (dayStartingEquity > 0) ? (todayPnL / dayStartingEquity) * 100.0 : 0.0;

   // Get Trend Status
   double fastEMA[], slowEMA[];
   ArraySetAsSeries(fastEMA, true);
   ArraySetAsSeries(slowEMA, true);
   string trendStr = "ANALYZING...";
   color trendColor = clrGray;

   if(CopyBuffer(hFastEMA, 0, 0, 5, fastEMA) > 0 && CopyBuffer(hSlowEMA, 0, 0, 5, slowEMA) > 0)
     {
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      if(CopyRates(_Symbol, _Period, 0, 5, rates) > 0)
        {
         bool isBull = false, isBear = false, isSide = false;
         CheckTrendConditions(fastEMA, slowEMA, rates, isBull, isBear, isSide);
         if(isBull) { trendStr = "BULLISH (UP)"; trendColor = clrLime; }
         else if(isBear) { trendStr = "BEARISH (DOWN)"; trendColor = clrRed; }
         else { trendStr = "SIDEWAY / EXHAUSTED"; trendColor = clrOrange; }
        }
     }

   string botStatus = "ACTIVE (SEARCHING)";
   color statusColor = clrLime;

   if(pauseUntilTime > 0 && TimeCurrent() < pauseUntilTime)
     {
      botStatus = "PAUSED (CONSECUTIVE LOSS)";
      statusColor = clrOrange;
     }
   else if(dailyTargetReached)
     {
      botStatus = "STOPPED (DAILY TARGET HIT)";
      statusColor = clrGold;
     }
   else if(dailyMaxLossReached)
     {
      botStatus = "STOPPED (DAILY MAX LOSS)";
      statusColor = clrCrimson;
     }
   else if(spread > InpMaxSpreadPoints)
     {
      botStatus = "WAITING (SPREAD TOO HIGH)";
      statusColor = clrDarkOrange;
     }
   else if(InpUseTimeFilter && !IsInsideTradingSession())
     {
      botStatus = "SLEEP (OUT OF SESSION)";
      statusColor = clrGray;
     }

   // Build text panel string for clean Comment display
   string info = "";
   info += "===============================================\n";
   info += "   XAUUSD Scalping M5 - Secret System (EA)     \n";
   info += "===============================================\n";
   info += StringFormat(" > Status:        %s\n", botStatus);
   info += StringFormat(" > Market Trend:  %s\n", trendStr);
   info += StringFormat(" > Spread:        %.1f pts (Max: %.1f)\n", spread, InpMaxSpreadPoints);
   info += "-----------------------------------------------\n";
   info += StringFormat(" > Today Profit:  $%.2f (%.2f%%)\n", todayPnL, pnlPercent);
   info += StringFormat(" > Daily Targets: +%.1f%% / -%.1f%%\n", InpDailyTargetPercent, InpDailyMaxLossPercent);
   info += StringFormat(" > Consec. Loss:  %d (Limit: %d)\n", consecutiveLosses, InpConsecutiveLossLimit);
   info += StringFormat(" > Multi-Order:   %s\n", InpEnableMultiOrder ? "ENABLED (1:1 + Trailing)" : "SINGLE (1:1)");
   info += StringFormat(" > Risk Mode:     %s (%.1f%%)\n", (InpLotMode == LOT_RISK_PERCENT ? "Dynamic %" : "Fixed"), InpRiskPercent);
   info += "===============================================\n";

   Comment(info);
  }
//+------------------------------------------------------------------+
