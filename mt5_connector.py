"""
MT5 Connector Module for Python WebApp
Provides automated live connection to active MetaTrader 5 terminals on Windows.
Auto-detects running MT5 instances and seamlessly syncs real balances, equity, and positions.
"""

import time
import logging
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger("MT5Connector")

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 python package not found. Running in Paper Simulation mode.")


class MT5Connector:
    def __init__(self, config: dict):
        self.config = config.get("mt5", {})
        self.account = self.config.get("account", 0)
        self.password = self.config.get("password", "")
        self.server = self.config.get("server", "")
        self.path = self.config.get("path", "")
        self.symbol = self.config.get("symbol", "XAUUSD")
        self.magic_number = self.config.get("magic_number", 555888)
        self.is_connected = False
        self.simulation_mode = self.config.get("simulation_mode", False)
        
        # Real-time state cache
        self.live_currency = "USD"
        self.connect()

    def connect(self) -> bool:
        """Connect to MT5 terminal (Auto-detect running MT5 or connect via credentials)."""
        if not MT5_AVAILABLE or self.simulation_mode:
            logger.info("Operating in Simulation / Paper Trading mode.")
            self.is_connected = False
            return False

        try:
            # 1. First, attempt to attach to already running visible MT5 GUI terminal
            init_ok = mt5.initialize()
            if init_ok and mt5.account_info() is not None:
                acc_info = mt5.account_info()
                self.is_connected = True
                self.account = acc_info.login
                self.server = acc_info.server
                self.live_currency = acc_info.currency
                logger.info(f"✅ Successfully attached to active MT5 GUI Window #{acc_info.login} ({acc_info.server}) | Balance: {acc_info.balance:,.2f} {acc_info.currency}")
                return True

            # 2. If not open, launch MT5 GUI process directly so the window is visible to the user
            if self.path and os.path.exists(self.path):
                import subprocess
                subprocess.Popen([self.path])
                time.sleep(2.0)
                init_ok = mt5.initialize()

            # 3. Fallback explicit login
            if not init_ok and self.account > 0 and self.password and self.server:
                if self.path:
                    init_ok = mt5.initialize(
                        path=self.path,
                        login=int(self.account),
                        password=self.password,
                        server=self.server
                    )
                else:
                    init_ok = mt5.initialize(
                        login=int(self.account),
                        password=self.password,
                        server=self.server
                    )

            if init_ok:
                acc_info = mt5.account_info()
                if acc_info is not None:
                    self.is_connected = True
                    self.account = acc_info.login
                    self.server = acc_info.server
                    self.live_currency = acc_info.currency
                    logger.info(f"✅ Successfully attached to live MT5 Account #{acc_info.login} ({acc_info.server}) | Balance: {acc_info.balance:,.2f} {acc_info.currency}")
                    return True
                else:
                    logger.warning(f"Attached to MT5, but account_info() is None: {mt5.last_error()}")
            else:
                logger.warning(f"Could not initialize MT5: {mt5.last_error()}")

        except Exception as e:
            logger.error(f"Error connecting to MT5: {e}")

        self.is_connected = False
        return False

    def ensure_connected(self):
        """Ensure connection is active, auto-reconnecting if MT5 was restarted."""
        if not MT5_AVAILABLE:
            return False
        try:
            acc = mt5.account_info()
            if acc is not None:
                self.is_connected = True
                return True
        except Exception:
            pass
        return self.connect()

    def get_account_info(self) -> dict:
        """Fetch live account balance, equity, free margin, currency from MT5."""
        if self.ensure_connected() and MT5_AVAILABLE:
            try:
                acc = mt5.account_info()
                if acc is not None:
                    self.live_currency = acc.currency
                    return {
                        "login": acc.login,
                        "server": acc.server,
                        "currency": acc.currency,
                        "balance": round(float(acc.balance), 2),
                        "equity": round(float(acc.equity), 2),
                        "margin": round(float(acc.margin), 2),
                        "free_margin": round(float(acc.margin_free), 2),
                        "profit": round(float(acc.profit), 2),
                        "mode": "Live MT5 Terminal",
                        "connected": True
                    }
            except Exception as e:
                logger.error(f"Error fetching live account_info: {e}")

        # Fallback if MT5 is closed
        return {
            "login": self.account if self.account else 0,
            "server": self.server if self.server else "MT5 Disconnected",
            "currency": self.live_currency,
            "balance": 0.0,
            "equity": 0.0,
            "margin": 0.0,
            "free_margin": 0.0,
            "profit": 0.0,
            "mode": "Disconnected (Please open MT5)",
            "connected": False
        }

    def get_symbol_info(self, symbol: str) -> dict:
        """Get live bid/ask/spread."""
        if self.ensure_connected() and MT5_AVAILABLE:
            try:
                # Try requested symbol or auto-detect matching symbol (e.g. XAUUSDc vs XAUUSD)
                info = mt5.symbol_info(symbol)
                if info is None:
                    for alt in [symbol + "c", symbol + "m", "XAUUSDc", "XAUUSDm", "GOLD", "XAUUSD"]:
                        info = mt5.symbol_info(alt)
                        if info is not None:
                            symbol = alt
                            break

                if info is not None:
                    if not info.visible:
                        mt5.symbol_select(symbol, True)
                    tick = mt5.symbol_info_tick(symbol)
                    if tick is not None:
                        if "XAU" in symbol or "GOLD" in symbol:
                            spread_pts = (tick.ask - tick.bid) / 0.01
                        else:
                            spread_pts = (tick.ask - tick.bid) / (info.point if info.point > 0 else 0.0001)
                        return {
                            "symbol": symbol,
                            "bid": round(tick.bid, 3),
                            "ask": round(tick.ask, 3),
                            "spread": round(spread_pts, 1),
                            "point": info.point,
                            "digits": info.digits,
                            "trade_allowed": (info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL)
                        }
            except Exception as e:
                logger.error(f"Error fetching symbol info: {e}")

        return {
            "symbol": symbol,
            "bid": 2650.00,
            "ask": 2650.25,
            "spread": 25.0,
            "point": 0.01,
            "digits": 2
        }

    def get_market_info(self, symbol: str) -> dict:
        return self.get_symbol_info(symbol)

    def get_open_positions(self, symbol: Optional[str] = None) -> List[dict]:
        """Fetch real open positions from live MT5 terminal."""
        positions_list = []
        if self.ensure_connected() and MT5_AVAILABLE:
            try:
                positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
                if positions is not None:
                    for p in positions:
                        positions_list.append({
                            "ticket": p.ticket,
                            "symbol": p.symbol,
                            "type": "BUY" if p.type == 0 else "SELL",
                            "volume": p.volume,
                            "price_open": round(p.price_open, 3),
                            "sl": round(p.sl, 3),
                            "tp": round(p.tp, 3),
                            "price_current": round(p.price_current, 3),
                            "profit": round(p.profit, 2),
                            "swap": round(p.swap, 2),
                            "comment": p.comment,
                            "magic": p.magic
                        })
            except Exception as e:
                logger.error(f"Error fetching positions: {e}")
        return positions_list

    def get_rates(self, symbol: str, timeframe: str = "M5", count: int = 100) -> pd.DataFrame:
        """Fetch real candlestick rates from MT5."""
        if self.ensure_connected() and MT5_AVAILABLE:
            try:
                tf_map = {
                    "M1": mt5.TIMEFRAME_M1,
                    "M5": mt5.TIMEFRAME_M5,
                    "M15": mt5.TIMEFRAME_M15,
                    "M30": mt5.TIMEFRAME_M30,
                    "H1": mt5.TIMEFRAME_H1,
                    "H4": mt5.TIMEFRAME_H4,
                    "D1": mt5.TIMEFRAME_D1,
                }
                tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M5)
                
                sym_info = self.get_symbol_info(symbol)
                target_symbol = sym_info.get("symbol", symbol)

                rates = mt5.copy_rates_from_pos(target_symbol, tf, 0, count)
                if rates is not None and len(rates) > 0:
                    df = pd.DataFrame(rates)
                    df['time'] = pd.to_datetime(df['time'], unit='s')
                    return df
            except Exception as e:
                logger.error(f"Error copying rates from MT5: {e}")

        return pd.DataFrame()

    def open_order(self, symbol: str, order_type: str, volume: float, sl: float, tp: float, magic: int, comment: str = "") -> dict:
        """Execute real market order on MT5."""
        if self.ensure_connected() and MT5_AVAILABLE:
            try:
                sym_info = self.get_symbol_info(symbol)
                target_symbol = sym_info.get("symbol", symbol)
                tick = mt5.symbol_info_tick(target_symbol)
                if not tick:
                    return {"status": False, "message": "Failed to get live tick"}

                price = tick.ask if order_type.upper() == "BUY" else tick.bid
                action_type = mt5.ORDER_TYPE_BUY if order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL

                filling_type = mt5.ORDER_FILLING_IOC
                s_info = mt5.symbol_info(target_symbol)
                if s_info:
                    filling_mode = s_info.filling_mode
                    if filling_mode & 1: filling_type = mt5.ORDER_FILLING_FOK
                    elif filling_mode & 2: filling_type = mt5.ORDER_FILLING_IOC
                    else: filling_type = mt5.ORDER_FILLING_RETURN

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": target_symbol,
                    "volume": float(volume),
                    "type": action_type,
                    "price": float(price),
                    "sl": float(sl),
                    "tp": float(tp),
                    "deviation": 20,
                    "magic": int(magic),
                    "comment": str(comment),
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": filling_type,
                }

                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return {"status": True, "ticket": result.order, "price": result.price}
                else:
                    err_code = result.retcode if result else mt5.last_error()
                    logger.error(f"MT5 Order Send Failed: {err_code} ({result.comment if result else ''})")
                    return {"status": False, "error": str(err_code)}

            except Exception as e:
                logger.error(f"Exception sending MT5 order: {e}")
                return {"status": False, "error": str(e)}

        return {"status": False, "error": "MT5 Not Connected"}

    def close_position(self, ticket: int) -> bool:
        """Close open position by ticket."""
        if self.ensure_connected() and MT5_AVAILABLE:
            try:
                positions = mt5.positions_get(ticket=ticket)
                if positions and len(positions) > 0:
                    pos = positions[0]
                    tick = mt5.symbol_info_tick(pos.symbol)
                    if not tick: return False

                    close_price = tick.bid if pos.type == 0 else tick.ask
                    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY

                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": pos.symbol,
                        "volume": pos.volume,
                        "type": close_type,
                        "position": pos.ticket,
                        "price": close_price,
                        "deviation": 20,
                        "magic": pos.magic,
                        "comment": "Close by WebApp",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    return (result and result.retcode == mt5.TRADE_RETCODE_DONE)
            except Exception as e:
                logger.error(f"Error closing position #{ticket}: {e}")
        return False

    def close_all_positions(self, magic: Optional[int] = None) -> int:
        """Close all positions."""
        closed_count = 0
        positions = self.get_open_positions()
        for p in positions:
            if magic is None or p.get("magic") == magic:
                if self.close_position(p["ticket"]):
                    closed_count += 1
        return closed_count

    def modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        """Modify SL/TP of an open position."""
        if self.ensure_connected() and MT5_AVAILABLE:
            try:
                positions = mt5.positions_get(ticket=ticket)
                if positions and len(positions) > 0:
                    pos = positions[0]
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": pos.symbol,
                        "position": pos.ticket,
                        "sl": float(sl),
                        "tp": float(tp if tp else 0.0),
                    }
                    result = mt5.order_send(request)
                    return (result and result.retcode == mt5.TRADE_RETCODE_DONE)
            except Exception as e:
                logger.error(f"Error modifying position #{ticket}: {e}")
        return False
