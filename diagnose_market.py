import MetaTrader5 as mt5
import pandas as pd
from bot_engine import GoldScalpingBot
from mt5_connector import MT5Connector

import json

with open('config.json', 'r', encoding='utf-8') as f:
    cfg = json.load(f)

connector = MT5Connector(cfg.get("accounts", [{}])[1] if len(cfg.get("accounts", [])) > 1 else {})
if not connector.is_connected:
    print('Failed to connect to live MT5 instance (is MT5 running?)')

rates = connector.get_rates('XAUUSDc', 'M5', 100)
df = rates
print('Total M5 Candles fetched:', len(df))

bot = GoldScalpingBot(connector, cfg.get("accounts", [{}])[1] if len(cfg.get("accounts", [])) > 1 else {})

print('\n=== LAST 15 M5 CANDLE STRATEGY EVALUATIONS ===')
for i in range(15, 0, -1):
    sub_df = df.iloc[:-i] if i > 1 else df
    b1 = sub_df.iloc[-2]
    b2 = sub_df.iloc[-3]
    b3 = sub_df.iloc[-4]
    t = b1['time']
    c = b1['close']
    e50 = b1.get('ema50', 0)
    e150 = b1.get('ema150', 0)
    sub_df = sub_df.copy()
    sub_df['ema20'] = sub_df['close'].ewm(span=20, adjust=False).mean()
    sub_df['ema50'] = sub_df['close'].ewm(span=50, adjust=False).mean()
    sub_df['ema100'] = sub_df['close'].ewm(span=100, adjust=False).mean()
    sub_df['ema150'] = sub_df['close'].ewm(span=150, adjust=False).mean()
    sub_df['ema200'] = sub_df['close'].ewm(span=200, adjust=False).mean()
    sub_df['sma20'] = sub_df['close'].rolling(window=20).mean()
    sub_df['std20'] = sub_df['close'].rolling(window=20).std()
    sub_df['bb_upper'] = sub_df['sma20'] + (2.0 * sub_df['std20'])
    sub_df['bb_lower'] = sub_df['sma20'] - (2.0 * sub_df['std20'])
    sub_df['ema9'] = sub_df['close'].ewm(span=9, adjust=False).mean()
    sub_df['ema21'] = sub_df['close'].ewm(span=21, adjust=False).mean()

    delta = sub_df['close'].diff()
    gain7 = (delta.where(delta > 0, 0)).rolling(window=7).mean()
    loss7 = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
    sub_df['rsi7'] = 100 - (100 / (1 + (gain7 / (loss7 + 1e-9))))

    gain14 = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss14 = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    sub_df['rsi14'] = 100 - (100 / (1 + (gain14 / (loss14 + 1e-9))))

    b1 = sub_df.iloc[-2]
    t = b1['time']
    c = b1['close']
    e50 = b1.get('ema50', 0)
    e150 = b1.get('ema150', 0)
    rsi = b1.get('rsi14', 0)

    smc_buy, smc_sell, smc_rs = bot._check_captain_smc(sub_df)
    flash_buy, flash_sell, flash_rs = bot._check_flash_micro_scalper(sub_df)
    asian_buy, asian_sell, asian_rs = bot._check_asian_range_sniper(sub_df)
    ema3_buy, ema3_sell, ema3_rs = bot._check_ema50_3candles_h1(sub_df)
    sec_buy, sec_sell, sec_rs = bot._check_secret_ema_pullback(sub_df, {})

    signals = []
    if smc_buy: signals.append(f'CAPTAIN_SMC_BUY ({smc_rs})')
    if smc_sell: signals.append(f'CAPTAIN_SMC_SELL ({smc_rs})')
    if flash_buy: signals.append(f'FLASH_BUY ({flash_rs})')
    if flash_sell: signals.append(f'FLASH_SELL ({flash_rs})')
    if asian_buy: signals.append(f'ASIAN_BUY ({asian_rs})')
    if asian_sell: signals.append(f'ASIAN_SELL ({asian_rs})')
    if ema3_buy: signals.append(f'EMA3_BUY ({ema3_rs})')
    if ema3_sell: signals.append(f'EMA3_SELL ({ema3_rs})')
    if sec_buy: signals.append(f'SECRET_BUY ({sec_rs})')
    if sec_sell: signals.append(f'SECRET_SELL ({sec_rs})')

    # Also evaluate scorer
    score_res = bot.scorer.evaluate_market_confluence(sub_df, 20.0, "FLASH_MICRO_SCALPER")

    sig_str = ' | '.join(signals) if signals else 'No Signal (Condition Not Met)'
    print(f'[{t}] Close: {c:.2f} | EMA50: {e50:.2f} | EMA150: {e150:.2f} | RSI: {rsi:.1f} -> {sig_str}')

print('\n=== SUMMARY OF CONDITIONS ===')
latest = df.iloc[-2]
print('Latest Closed M5 Candle:', latest['time'])
print('Close:', round(latest['close'], 2))
print('EMA20:', round(latest.get('ema20', 0), 2), '| EMA50:', round(latest.get('ema50', 0), 2), '| EMA100:', round(latest.get('ema100', 0), 2), '| EMA200:', round(latest.get('ema200', 0), 2))
print('RSI:', round(latest.get('rsi', 0), 1))
print('ATR:', round(latest.get('atr', 0), 2))