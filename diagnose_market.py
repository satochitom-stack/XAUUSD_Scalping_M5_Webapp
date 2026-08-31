import MetaTrader5 as mt5
import pandas as pd
from bot_engine import GoldScalpingBot
from mt5_connector import MT5Connector

connector = MT5Connector()
if not connector.initialize():
    print('Failed to initialize MT5')
    exit(1)

df = connector.get_candles('XAUUSDc', 'M5', 100)
print('Total M5 Candles fetched:', len(df))

bot = GoldScalpingBot(connector, {'strategy': {'strategy_mode': 'ALL', 'fast_ema': 50, 'slow_ema': 150}})

print('
=== LAST 15 M5 CANDLE STRATEGY EVALUATIONS ===')
for i in range(15, 0, -1):
    sub_df = df.iloc[:-i] if i > 1 else df
    b1 = sub_df.iloc[-2]
    b2 = sub_df.iloc[-3]
    b3 = sub_df.iloc[-4]
    t = b1['time']
    c = b1['close']
    e50 = b1.get('ema50', 0)
    e150 = b1.get('ema150', 0)
    rsi = b1.get('rsi', 0)

    smc_buy, smc_sell, smc_rs = bot.check_smc_liquidity_sweep(sub_df, b1, b2)
    rib_buy, rib_sell, rib_rs = bot.check_ema_ribbon_momentum(sub_df, b1, b2)
    bb_buy, bb_sell, bb_rs = bot.check_bb_squeeze_breakout(sub_df, b1, b2, b3)
    sec_buy, sec_sell, sec_rs = bot.check_secret_ema_pullback(sub_df, b1, b2)

    signals = []
    if smc_buy: signals.append(f'SMC_BUY ({smc_rs})')
    if smc_sell: signals.append(f'SMC_SELL ({smc_rs})')
    if rib_buy: signals.append(f'RIBBON_BUY ({rib_rs})')
    if rib_sell: signals.append(f'RIBBON_SELL ({rib_rs})')
    if bb_buy: signals.append(f'BB_BUY ({bb_rs})')
    if bb_sell: signals.append(f'BB_SELL ({bb_rs})')
    if sec_buy: signals.append(f'SECRET_BUY ({sec_rs})')
    if sec_sell: signals.append(f'SECRET_SELL ({sec_rs})')

    sig_str = ' | '.join(signals) if signals else 'No Signal (Condition Not Met)'
    print(f'[{t}] Close: {c:.2f} | EMA50: {e50:.2f} | EMA150: {e150:.2f} | RSI: {rsi:.1f} -> {sig_str}')

print('
=== SUMMARY OF CONDITIONS ===')
latest = df.iloc[-2]
print('Latest Closed M5 Candle:', latest['time'])
print('Close:', round(latest['close'], 2))
print('EMA20:', round(latest.get('ema20', 0), 2), '| EMA50:', round(latest.get('ema50', 0), 2), '| EMA100:', round(latest.get('ema100', 0), 2), '| EMA200:', round(latest.get('ema200', 0), 2))
print('RSI:', round(latest.get('rsi', 0), 1))
print('ATR:', round(latest.get('atr', 0), 2))