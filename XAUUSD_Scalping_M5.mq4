//+------------------------------------------------------------------+
//|                                     XAUUSD_Scalping_M5.mq4        |
//|                       Scalping M5 (Secret System) Expert Advisor  |
//|                                Copyright 2026, Antigravity AI    |
//|                                             https://google.com   |
//+------------------------------------------------------------------+
#property copyright   "Copyright 2026, Antigravity AI"
#property link        "https://google.com"
#property version     "1.00"
#property description "XAUUSD Scalping M5 (Secret System) Automated Trading Bot for MT4"
#property strict

//--- Enums
enum ENUM_ENTRY_TYPE_4
  {
   ENTRY_ALL_4 = 0,         // Both Pullback & Breakout
   ENTRY_PULLBACK_ONLY_4 = 1,// Pullback / Retest Only
   ENTRY_BREAKOUT_ONLY_4 = 2 // Breakout Only
  };

enum ENUM_SL_TYPE_4
  {
   SL_SWING_HIGH_LOW_4 = 0, // Recent Swing High / Low
   SL_CANDLE_HIGH_LOW_4 = 1,// Signal Candle High / Low
   SL_EMA_LINE_4 = 2        // EMA 50 / 150 Line + Buffer
  };

enum ENUM_LOT_MODE_4
  {
   LOT_RISK_PERCENT_4 = 0,  // Risk Percentage of Balance (1%-2%)
   LOT_FIXED_4 = 1          // Fixed Lot Size
  };

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                 |
//+------------------------------------------------------------------+
extern string               S1 = "=== 1. General & Magic Settings ===";
extern int                  InpMagicNumber          = 555888;         // EA Magic Number
extern string               InpTradeComment         = "GoldM5_Secret"; // Order Comment
extern ENUM_ENTRY_TYPE_4    InpEntryType            = ENTRY_ALL_4;    // Entry Setup Selection

extern string               S2 = "=== 2. Indicator & Trend Settings ===";
extern int                  InpFastEMAPeriod        = 50;             // Fast EMA Period (Default: 50)
extern int                  InpSlowEMAPeriod        = 150;            // Slow EMA Period (Default: 150)
extern int                  InpMAMethod             = 1;              // MA Method (1 = EMA)
extern int                  InpAppliedPrice         = 0;              // Applied Price (0 = Close)
extern double               InpMinSlopePoints       = 30.0;           // Min EMA Slope in Points (Slope Filter)
extern int                  InpSlopeBarsLookback    = 3;              // Bars to Calculate Slope
extern double               InpMaxExhaustionDist    = 4000.0;         // Max Distance from Slow EMA (Exhaustion Filter in Points)
extern int                  InpTangleLookbackBars   = 10;             // Bars to check EMA cross tangle (Sideway Filter)

extern string               S3 = "=== 3. Higher Timeframe (HTF) Filter ===";
extern bool                 InpUseHTFFilter         = true;           // Enable HTF Macro Trend Filter
extern int                  InpHTFTimeframe         = 60;             // HTF Timeframe (60 = H1)
extern int                  InpHTF_EMAPeriod        = 200;            // HTF EMA Period (Default: 200)

extern string               S4 = "=== 4. Price Action & Entry Quality ===";
extern double               InpMaxUpperWickBuy      = 0.40;           // Max Upper Wick Ratio for Buy Reversal (0.0-1.0)
extern double               InpMaxLowerWickSell     = 0.40;           // Max Lower Wick Ratio for Sell Reversal (0.0-1.0)
extern double               InpMinBodyPoints        = 50.0;           // Min Candle Body Size in Points
extern double               InpMaxEntryDistFromEMA  = 600.0;          // Max Entry Distance from EMA (Points)
extern int                  InpSwingBars            = 12;             // Swing High/Low Lookback for Breakout
extern double               InpPullbackEMABuffer    = 100.0;          // Pullback Proximity Buffer to EMA (Points)

extern string               S5 = "=== 5. Risk & Money Management ===";
extern ENUM_LOT_MODE_4      InpLotMode              = LOT_RISK_PERCENT_4;// Lot Calculation Mode
extern double               InpRiskPercent          = 1.0;            // Risk Per Trade (% of Balance)
extern double               InpFixedLotSize         = 0.05;           // Fixed Lot Size (if Fixed Mode)
extern ENUM_SL_TYPE_4       InpSLType               = SL_SWING_HIGH_LOW_4;// Stop Loss Calculation Method
extern int                  InpSLSwingBars          = 7;              // Swing Bars for SL Calculation
extern double               InpSLBufferPoints       = 50.0;           // Additional SL Buffer (Points)
extern double               InpMinSLPoints          = 150.0;          // Minimum Stop Loss (Points)
extern double               InpMaxSLPoints          = 1200.0;         // Maximum Stop Loss (Points)
extern double               InpRiskRewardRatio      = 1.0;            // Take Profit 1 Risk:Reward (Default: 1.0)

extern string               S6 = "=== 6. Multi-Order & Run Trend Settings ===";
extern bool                 InpEnableMultiOrder     = true;           // Enable 2nd Runner Position
extern double               InpPos1_LotRatio        = 0.50;           // Position 1 Volume Ratio (Scalp TP 1:1)
extern double               InpPos2_LotRatio        = 0.50;           // Position 2 Volume Ratio (Runner)
extern bool                 InpMoveBE_OnTP1         = true;           // Move Pos2 SL to Break-Even when Pos1 Hits TP
extern double               InpBE_BufferPoints      = 30.0;           // Break-Even Lock-in Profit (Points)
extern bool                 InpUseTrailingOnRunner  = true;           // Use Trailing Stop on Runner Position
extern bool                 InpTrailByEMA           = true;           // Trail SL behind Fast EMA 50 (if false, by Points)
extern double               InpTrailPoints          = 300.0;          // Fixed Trailing Points (if not by EMA)
extern double               InpTrailStepPoints      = 50.0;           // Trailing Step in Points

extern string               S7 = "=== 7. Safety & Drawdown Controls ===";
extern int                  InpConsecutiveLossLimit = 2;              // Max Consecutive Losses before Pause
extern int                  InpPauseHoursOnLoss     = 4;              // Hours to Pause Trading after Loss Limit
extern bool                 InpDynamicLotReduction  = true;           // Enable Dynamic Lot Reduction after Loss
extern double               InpDailyTargetPercent   = 5.0;            // Daily Profit Target Stop (%)
extern double               InpDailyMaxLossPercent  = 3.0;            // Daily Max Loss Limit (%)
extern double               InpMaxSpreadPoints      = 35.0;           // Maximum Allowed Spread (Points / Pipette)

extern string               S8 = "=== 8. Trading Session / Time Filter ===";
extern bool                 InpUseTimeFilter        = true;           // Enable Session Time Filter
extern string               InpSessionStart         = "07:00";        // Trading Session Start (HH:MM Server Time)
extern string               InpSessionEnd           = "21:00";        // Trading Session End (HH:MM Server Time)

extern string               S9 = "=== 9. Visual HUD Dashboard ===";
extern bool                 InpShowHUD              = true;           // Display On-Chart Live Dashboard

//+------------------------------------------------------------------+
//| GLOBAL VARIABLES                                                 |
//+------------------------------------------------------------------+
datetime          lastBarTime = 0;
datetime          pauseUntilTime = 0;
int               consecutiveLosses = 0;
int               consecutiveWins = 0;
double            dayStartingEquity = 0.0;
datetime          currentDayTime = 0;
bool              dailyTargetReached = false;
bool              dailyMaxLossReached = false;

int               magicPos1 = 0;
int               magicPos2 = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   magicPos1 = InpMagicNumber + 1;
   magicPos2 = InpMagicNumber + 2;

   InitDailyTracking();
   CheckHistoricalConsecutiveStats();

   Print("XAUUSD Scalping M5 MT4 EA Initialized Successfully.");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Comment("");
  }

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   CheckNewDay();
   ManageOpenPositions();

   if(InpShowHUD)
      DrawHUD();

   // Bar Close detection
   if(Time[0] == lastBarTime)
      return;

   ProcessStrategy();
   lastBarTime = Time[0];
  }

//+------------------------------------------------------------------+
//| Core Strategy Logic on Bar Close                                 |
//+------------------------------------------------------------------+
void ProcessStrategy()
  {
   if(!IsTradingAllowedSafety())
      return;

   double spread = (Ask - Bid) / Point;
   if(spread > InpMaxSpreadPoints)
     {
      PrintFormat("Trade Skipped: Spread (%.1f) exceeds maximum allowed (%.1f)", spread, InpMaxSpreadPoints);
      return;
     }

   if(InpUseTimeFilter && !IsInsideTradingSession())
      return;

   if(HasOpenEAOrders())
      return;

   // Calculate EMAs
   double fastEMA1 = iMA(Symbol(), 0, InpFastEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1);
   double slowEMA1 = iMA(Symbol(), 0, InpSlowEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1);

   bool isBullish = false;
   bool isBearish = false;
   bool isSideway = false;

   CheckTrendConditions(isBullish, isBearish, isSideway);
   if(isSideway) return;

   // Higher Timeframe Filter
   if(InpUseHTFFilter)
     {
      double htfEMA = iMA(Symbol(), InpHTFTimeframe, InpHTF_EMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1);
      double htfClose = iClose(Symbol(), InpHTFTimeframe, 1);
      if(isBullish && htfClose < htfEMA) return;
      if(isBearish && htfClose > htfEMA) return;
     }

   bool buySignal = false;
   bool sellSignal = false;
   string reason = "";

   if(isBullish)
     {
      if(InpEntryType == ENTRY_ALL_4 || InpEntryType == ENTRY_PULLBACK_ONLY_4)
        {
         if(CheckBuyPullbackSetup(fastEMA1, slowEMA1))
           {
            buySignal = true;
            reason = "Buy Pullback at EMA";
           }
        }
      if(!buySignal && (InpEntryType == ENTRY_ALL_4 || InpEntryType == ENTRY_BREAKOUT_ONLY_4))
        {
         if(CheckBuyBreakoutSetup())
           {
            buySignal = true;
            reason = "Buy Breakout";
           }
        }
     }

   if(isBearish)
     {
      if(InpEntryType == ENTRY_ALL_4 || InpEntryType == ENTRY_PULLBACK_ONLY_4)
        {
         if(CheckSellPullbackSetup(fastEMA1, slowEMA1))
           {
            sellSignal = true;
            reason = "Sell Pullback at EMA";
           }
        }
      if(!sellSignal && (InpEntryType == ENTRY_ALL_4 || InpEntryType == ENTRY_BREAKOUT_ONLY_4))
        {
         if(CheckSellBreakoutSetup())
           {
            sellSignal = true;
            reason = "Sell Breakout";
           }
        }
     }

   if(buySignal)
      ExecuteBuyOrder(fastEMA1, slowEMA1, reason);
   else if(sellSignal)
      ExecuteSellOrder(fastEMA1, slowEMA1, reason);
  }

//+------------------------------------------------------------------+
//| Trend & Slope Identification                                     |
//+------------------------------------------------------------------+
void CheckTrendConditions(bool &isBullish, bool &isBearish, bool &isSideway)
  {
   isBullish = false; isBearish = false; isSideway = false;
   int lb = InpSlopeBarsLookback;

   double fastEMA1 = iMA(Symbol(), 0, InpFastEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1);
   double fastEMALookback = iMA(Symbol(), 0, InpFastEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1 + lb);

   double slowEMA1 = iMA(Symbol(), 0, InpSlowEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1);
   double slowEMALookback = iMA(Symbol(), 0, InpSlowEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1 + lb);

   double fastSlope = (fastEMA1 - fastEMALookback) / Point;
   double slowSlope = (slowEMA1 - slowEMALookback) / Point;

   bool fastAboveSlow = (fastEMA1 > slowEMA1);
   bool fastBelowSlow = (fastEMA1 < slowEMA1);

   bool fastSlopingUp   = (fastSlope >= InpMinSlopePoints);
   bool slowSlopingUp   = (slowSlope >= (InpMinSlopePoints * 0.4));
   bool fastSlopingDown = (fastSlope <= -InpMinSlopePoints);
   bool slowSlopingDown = (slowSlope <= -(InpMinSlopePoints * 0.4));

   // Cross tangle check
   int crosses = 0;
   for(int i = 1; i <= InpTangleLookbackBars; i++)
     {
      double fCurr = iMA(Symbol(), 0, InpFastEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, i);
      double sCurr = iMA(Symbol(), 0, InpSlowEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, i);
      double fPrev = iMA(Symbol(), 0, InpFastEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, i+1);
      double sPrev = iMA(Symbol(), 0, InpSlowEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, i+1);

      if((fCurr > sCurr && fPrev <= sPrev) || (fCurr < sCurr && fPrev >= sPrev))
         crosses++;
     }

   if(crosses >= 2)
     {
      isSideway = true;
      return;
     }

   // Exhaustion check
   double distSlow = MathAbs(Close[1] - slowEMA1) / Point;
   if(distSlow > InpMaxExhaustionDist)
     {
      isSideway = true;
      return;
     }

   if(fastAboveSlow && fastSlopingUp && slowSlopingUp)
      isBullish = true;
   else if(fastBelowSlow && fastSlopingDown && slowSlopingDown)
      isBearish = true;
   else
      isSideway = true;
  }

//+------------------------------------------------------------------+
//| Buy Setups                                                       |
//+------------------------------------------------------------------+
bool CheckBuyPullbackSetup(double fastEMA, double slowEMA)
  {
   double buffer = InpPullbackEMABuffer * Point;
   if(Close[1] <= Open[1]) return false;

   bool touchedFast = (Low[1] <= (fastEMA + buffer) && Close[1] > fastEMA);
   bool touchedSlow = (Low[1] <= (slowEMA + buffer) && Close[1] > slowEMA);
   if(!touchedFast && !touchedSlow) return false;

   double range = High[1] - Low[1];
   double body = Close[1] - Open[1];
   double upperWick = High[1] - Close[1];

   if(range <= 0 || (body / Point) < InpMinBodyPoints) return false;
   if((upperWick / range) > InpMaxUpperWickBuy) return false;

   double refEMA = touchedFast ? fastEMA : slowEMA;
   if(((Close[1] - refEMA) / Point) > InpMaxEntryDistFromEMA) return false;

   return true;
  }

bool CheckBuyBreakoutSetup()
  {
   double swingHigh = -1.0;
   for(int i = 2; i <= InpSwingBars; i++)
     {
      if(High[i] > swingHigh) swingHigh = High[i];
     }
   if(swingHigh <= 0) return false;

   if(Close[1] > swingHigh && Close[2] <= swingHigh && Close[1] > Open[1])
      return true;

   return false;
  }

//+------------------------------------------------------------------+
//| Sell Setups                                                      |
//+------------------------------------------------------------------+
bool CheckSellPullbackSetup(double fastEMA, double slowEMA)
  {
   double buffer = InpPullbackEMABuffer * Point;
   if(Close[1] >= Open[1]) return false;

   bool touchedFast = (High[1] >= (fastEMA - buffer) && Close[1] < fastEMA);
   bool touchedSlow = (High[1] >= (slowEMA - buffer) && Close[1] < slowEMA);
   if(!touchedFast && !touchedSlow) return false;

   double range = High[1] - Low[1];
   double body = Open[1] - Close[1];
   double lowerWick = Close[1] - Low[1];

   if(range <= 0 || (body / Point) < InpMinBodyPoints) return false;
   if((lowerWick / range) > InpMaxLowerWickSell) return false;

   double refEMA = touchedFast ? fastEMA : slowEMA;
   if(((refEMA - Close[1]) / Point) > InpMaxEntryDistFromEMA) return false;

   return true;
  }

bool CheckSellBreakoutSetup()
  {
   double swingLow = 999999.0;
   for(int i = 2; i <= InpSwingBars; i++)
     {
      if(Low[i] < swingLow) swingLow = Low[i];
     }
   if(swingLow >= 999999.0) return false;

   if(Close[1] < swingLow && Close[2] >= swingLow && Close[1] < Open[1])
      return true;

   return false;
  }

//+------------------------------------------------------------------+
//| Order Execution                                                  |
//+------------------------------------------------------------------+
void ExecuteBuyOrder(double fastEMA, double slowEMA, string reason)
  {
   double slPrice = 0.0;
   if(InpSLType == SL_SWING_HIGH_LOW_4)
     {
      double lowestLow = Low[1];
      for(int i = 1; i <= InpSLSwingBars; i++)
        {
         if(Low[i] < lowestLow) lowestLow = Low[i];
        }
      slPrice = lowestLow - (InpSLBufferPoints * Point);
     }
   else if(InpSLType == SL_CANDLE_HIGH_LOW_4)
     {
      slPrice = Low[1] - (InpSLBufferPoints * Point);
     }
   else if(InpSLType == SL_EMA_LINE_4)
     {
      slPrice = MathMin(fastEMA, slowEMA) - (InpSLBufferPoints * Point);
     }

   double slDist = (Ask - slPrice) / Point;
   if(slDist < InpMinSLPoints) { slPrice = Ask - (InpMinSLPoints * Point); slDist = InpMinSLPoints; }
   if(slDist > InpMaxSLPoints) { slPrice = Ask - (InpMaxSLPoints * Point); slDist = InpMaxSLPoints; }
   slPrice = NormalizeDouble(slPrice, Digits);

   double tp1 = NormalizeDouble(Ask + (slDist * InpRiskRewardRatio * Point), Digits);
   double totalLot = CalculateLotSize(slDist);
   if(totalLot <= 0) return;

   if(InpEnableMultiOrder)
     {
      double lot1 = NormalizeLot(totalLot * InpPos1_LotRatio);
      double lot2 = NormalizeLot(totalLot * InpPos2_LotRatio);

      OrderSend(Symbol(), OP_BUY, lot1, Ask, 3, slPrice, tp1, InpTradeComment + "_P1", magicPos1, 0, clrBlue);
      OrderSend(Symbol(), OP_BUY, lot2, Ask, 3, slPrice, 0.0, InpTradeComment + "_P2", magicPos2, 0, clrBlue);
     }
   else
     {
      OrderSend(Symbol(), OP_BUY, totalLot, Ask, 3, slPrice, tp1, InpTradeComment, InpMagicNumber, 0, clrBlue);
     }
  }

void ExecuteSellOrder(double fastEMA, double slowEMA, string reason)
  {
   double slPrice = 0.0;
   if(InpSLType == SL_SWING_HIGH_LOW_4)
     {
      double highestHigh = High[1];
      for(int i = 1; i <= InpSLSwingBars; i++)
        {
         if(High[i] > highestHigh) highestHigh = High[i];
        }
      slPrice = highestHigh + (InpSLBufferPoints * Point);
     }
   else if(InpSLType == SL_CANDLE_HIGH_LOW_4)
     {
      slPrice = High[1] + (InpSLBufferPoints * Point);
     }
   else if(InpSLType == SL_EMA_LINE_4)
     {
      slPrice = MathMax(fastEMA, slowEMA) + (InpSLBufferPoints * Point);
     }

   double slDist = (slPrice - Bid) / Point;
   if(slDist < InpMinSLPoints) { slPrice = Bid + (InpMinSLPoints * Point); slDist = InpMinSLPoints; }
   if(slDist > InpMaxSLPoints) { slPrice = Bid + (InpMaxSLPoints * Point); slDist = InpMaxSLPoints; }
   slPrice = NormalizeDouble(slPrice, Digits);

   double tp1 = NormalizeDouble(Bid - (slDist * InpRiskRewardRatio * Point), Digits);
   double totalLot = CalculateLotSize(slDist);
   if(totalLot <= 0) return;

   if(InpEnableMultiOrder)
     {
      double lot1 = NormalizeLot(totalLot * InpPos1_LotRatio);
      double lot2 = NormalizeLot(totalLot * InpPos2_LotRatio);

      OrderSend(Symbol(), OP_SELL, lot2, Bid, 3, slPrice, tp1, InpTradeComment + "_P1", magicPos1, 0, clrRed);
      OrderSend(Symbol(), OP_SELL, lot1, Bid, 3, slPrice, 0.0, InpTradeComment + "_P2", magicPos2, 0, clrRed);
     }
   else
     {
      OrderSend(Symbol(), OP_SELL, totalLot, Bid, 3, slPrice, tp1, InpTradeComment, InpMagicNumber, 0, clrRed);
     }
  }

//+------------------------------------------------------------------+
//| Manage Open Positions                                            |
//+------------------------------------------------------------------+
void ManageOpenPositions()
  {
   double fastEMA1 = iMA(Symbol(), 0, InpFastEMAPeriod, 0, (ENUM_MA_METHOD)InpMAMethod, (ENUM_APPLIED_PRICE)InpAppliedPrice, 1);
   bool pos1Exists = false;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
        {
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == magicPos1)
            pos1Exists = true;
        }
     }

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol()) continue;

      int mag = OrderMagicNumber();
      if(mag != InpMagicNumber && mag != magicPos1 && mag != magicPos2) continue;

      int type = OrderType();
      double openPrice = OrderOpenPrice();
      double currentSL = OrderStopLoss();

      if(mag == magicPos2)
        {
         // 1. Break-Even on Runner
         if(!pos1Exists && InpMoveBE_OnTP1)
           {
            if(type == OP_BUY)
              {
               double bePrice = NormalizeDouble(openPrice + (InpBE_BufferPoints * Point), Digits);
               if(currentSL < openPrice && Bid > bePrice)
                  OrderModify(OrderTicket(), openPrice, bePrice, OrderTakeProfit(), 0, clrGreen);
              }
            else if(type == OP_SELL)
              {
               double bePrice = NormalizeDouble(openPrice - (InpBE_BufferPoints * Point), Digits);
               if((currentSL > openPrice || currentSL == 0) && Ask < bePrice)
                  OrderModify(OrderTicket(), openPrice, bePrice, OrderTakeProfit(), 0, clrGreen);
              }
           }

         // 2. Trailing on Runner
         if(InpUseTrailingOnRunner)
           {
            if(type == OP_BUY)
              {
               double newSL = InpTrailByEMA ? NormalizeDouble(fastEMA1 - (InpSLBufferPoints * Point), Digits) :
                              NormalizeDouble(Bid - (InpTrailPoints * Point), Digits);

               if(newSL > currentSL + (InpTrailStepPoints * Point) && newSL < Bid)
                  OrderModify(OrderTicket(), openPrice, newSL, OrderTakeProfit(), 0, clrGreen);
              }
            else if(type == OP_SELL)
              {
               double newSL = InpTrailByEMA ? NormalizeDouble(fastEMA1 + (InpSLBufferPoints * Point), Digits) :
                              NormalizeDouble(Ask + (InpTrailPoints * Point), Digits);

               if((currentSL == 0 || newSL < currentSL - (InpTrailStepPoints * Point)) && newSL > Ask)
                  OrderModify(OrderTicket(), openPrice, newSL, OrderTakeProfit(), 0, clrGreen);
              }
           }

         // 3. Close on Opposite EMA Close
         if(type == OP_BUY && Close[1] < fastEMA1)
            OrderClose(OrderTicket(), OrderLots(), Bid, 3, clrWhite);
         else if(type == OP_SELL && Close[1] > fastEMA1)
            OrderClose(OrderTicket(), OrderLots(), Ask, 3, clrWhite);
        }
     }
  }

//+------------------------------------------------------------------+
//| Lot Size & Money Management                                      |
//+------------------------------------------------------------------+
double CalculateLotSize(double slDistPoints)
  {
   double lot = InpFixedLotSize;

   if(InpLotMode == LOT_RISK_PERCENT_4)
     {
      double riskMoney = AccountBalance() * (InpRiskPercent / 100.0);
      double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
      double tickSize  = MarketInfo(Symbol(), MODE_TICKSIZE);

      if(tickSize > 0 && tickValue > 0 && slDistPoints > 0)
        {
         double pointsPerTick = tickSize / Point;
         double moneyPerLot = (slDistPoints / pointsPerTick) * tickValue;
         if(moneyPerLot > 0)
            lot = riskMoney / moneyPerLot;
        }
     }

   if(InpDynamicLotReduction)
     {
      if(consecutiveLosses == 1) lot *= 0.50;
      else if(consecutiveLosses >= 2) lot *= 0.25;
     }

   return NormalizeLot(lot);
  }

double NormalizeLot(double lot)
  {
   double minLot  = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot  = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);
   if(lotStep <= 0) lotStep = 0.01;

   lot = MathFloor(lot / lotStep) * lotStep;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;

   return NormalizeDouble(lot, 2);
  }

//+------------------------------------------------------------------+
//| Safety & Tracking                                                |
//+------------------------------------------------------------------+
bool IsTradingAllowedSafety()
  {
   if(pauseUntilTime > 0 && TimeCurrent() < pauseUntilTime) return false;
   if(dailyTargetReached || dailyMaxLossReached) return false;
   if(!IsTradeAllowed()) return false;
   return true;
  }

void InitDailyTracking()
  {
   currentDayTime = iTime(Symbol(), PERIOD_D1, 0);
   dayStartingEquity = AccountEquity();
   dailyTargetReached = false;
   dailyMaxLossReached = false;
  }

void CheckNewDay()
  {
   datetime todayStart = iTime(Symbol(), PERIOD_D1, 0);
   if(todayStart != currentDayTime)
     {
      currentDayTime = todayStart;
      dayStartingEquity = AccountEquity();
      dailyTargetReached = false;
      dailyMaxLossReached = false;
      pauseUntilTime = 0;
     }

   double todayProfit = GetTodayClosedProfit();
   if(dayStartingEquity > 0)
     {
      double pPercent = (todayProfit / dayStartingEquity) * 100.0;
      if(pPercent >= InpDailyTargetPercent) dailyTargetReached = true;
      if(pPercent <= -InpDailyMaxLossPercent) dailyMaxLossReached = true;
     }

   CheckHistoricalConsecutiveStats();
  }

double GetTodayClosedProfit()
  {
   double total = 0.0;
   int histTotal = OrdersHistoryTotal();
   for(int i = 0; i < histTotal; i++)
     {
      if(OrderSelect(i, SELECT_BY_POS, MODE_HISTORY))
        {
         if(OrderSymbol() == Symbol() && OrderCloseTime() >= currentDayTime)
           {
            int mag = OrderMagicNumber();
            if(mag == InpMagicNumber || mag == magicPos1 || mag == magicPos2)
               total += OrderProfit() + OrderSwap() + OrderCommission();
           }
        }
     }
   return total;
  }

void CheckHistoricalConsecutiveStats()
  {
   consecutiveLosses = 0;
   consecutiveWins = 0;
   int histTotal = OrdersHistoryTotal();

   for(int i = histTotal - 1; i >= 0; i--)
     {
      if(OrderSelect(i, SELECT_BY_POS, MODE_HISTORY))
        {
         if(OrderSymbol() == Symbol())
           {
            int mag = OrderMagicNumber();
            if(mag == InpMagicNumber || mag == magicPos1 || mag == magicPos2)
              {
               double pnl = OrderProfit() + OrderSwap() + OrderCommission();
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

   if(consecutiveLosses >= InpConsecutiveLossLimit && pauseUntilTime == 0)
     {
      pauseUntilTime = TimeCurrent() + (InpPauseHoursOnLoss * 3600);
     }
  }

bool IsInsideTradingSession()
  {
   string currTime = TimeToStr(TimeCurrent(), TIME_MINUTES);
   if(StringCompare(InpSessionStart, InpSessionEnd) <= 0)
      return (StringCompare(currTime, InpSessionStart) >= 0 && StringCompare(currTime, InpSessionEnd) <= 0);
   else
      return (StringCompare(currTime, InpSessionStart) >= 0 || StringCompare(currTime, InpSessionEnd) <= 0);
  }

bool HasOpenEAOrders()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
        {
         if(OrderSymbol() == Symbol())
           {
            int mag = OrderMagicNumber();
            if(mag == InpMagicNumber || mag == magicPos1 || mag == magicPos2)
               return true;
           }
        }
     }
   return false;
  }

void DrawHUD()
  {
   double spread = (Ask - Bid) / Point;
   double todayPnL = GetTodayClosedProfit();
   double pnlPercent = (dayStartingEquity > 0) ? (todayPnL / dayStartingEquity) * 100.0 : 0.0;

   bool isBull = false, isBear = false, isSide = false;
   CheckTrendConditions(isBull, isBear, isSide);
   string trendStr = isBull ? "BULLISH (UP)" : (isBear ? "BEARISH (DOWN)" : "SIDEWAY / EXHAUSTED");

   string botStatus = "ACTIVE (SEARCHING)";
   if(pauseUntilTime > 0 && TimeCurrent() < pauseUntilTime) botStatus = "PAUSED (CONSECUTIVE LOSS)";
   else if(dailyTargetReached) botStatus = "STOPPED (DAILY TARGET HIT)";
   else if(dailyMaxLossReached) botStatus = "STOPPED (DAILY MAX LOSS)";
   else if(spread > InpMaxSpreadPoints) botStatus = "WAITING (SPREAD TOO HIGH)";
   else if(InpUseTimeFilter && !IsInsideTradingSession()) botStatus = "SLEEP (OUT OF SESSION)";

   string info = "";
   info = info + "===============================================\n";
   info = info + "   XAUUSD Scalping M5 - Secret System (MT4 EA) \n";
   info = info + "===============================================\n";
   info = info + StringFormat(" > Status:        %s\n", botStatus);
   info = info + StringFormat(" > Market Trend:  %s\n", trendStr);
   info = info + StringFormat(" > Spread:        %.1f pts (Max: %.1f)\n", spread, InpMaxSpreadPoints);
   info = info + "-----------------------------------------------\n";
   info = info + StringFormat(" > Today Profit:  $%.2f (%.2f%%)\n", todayPnL, pnlPercent);
   info = info + StringFormat(" > Daily Targets: +%.1f%% / -%.1f%%\n", InpDailyTargetPercent, InpDailyMaxLossPercent);
   info = info + StringFormat(" > Consec. Loss:  %d (Limit: %d)\n", consecutiveLosses, InpConsecutiveLossLimit);
   info = info + StringFormat(" > Multi-Order:   %s\n", InpEnableMultiOrder ? "ENABLED (1:1 + Trailing)" : "SINGLE (1:1)");
   info = info + StringFormat(" > Risk Mode:     %s (%.1f%%)\n", (InpLotMode == LOT_RISK_PERCENT_4 ? "Dynamic %" : "Fixed"), InpRiskPercent);
   info = info + "===============================================\n";

   Comment(info);
  }
//+------------------------------------------------------------------+
