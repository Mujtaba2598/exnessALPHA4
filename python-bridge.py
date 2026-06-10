#!/usr/bin/env python3
import asyncio
import json
import websockets
import MetaTrader5 as mt5
import numpy as np
from datetime import datetime

# Halal trading pairs (no interest-bearing instruments)
HALAL_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD', 'ETHUSD']

class HalalExnessBridge:
    def __init__(self):
        self.connected = False
        self.login = None
        self.server = None
        
    def calculate_rsi(self, prices, period=14):
        if len(prices) < period + 1:
            return 50
        deltas = np.diff(prices)
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        if down == 0:
            return 100
        rs = up / down
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, prices):
        if len(prices) < 26:
            return 0
        ema12 = np.mean(prices[-12:])
        ema26 = np.mean(prices[-26:])
        macd = ema12 - ema26
        return macd
    
    def get_ai_signal(self, symbol):
        """Halal AI decision based on technical analysis"""
        try:
            # Get rates
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)
            if rates is None or len(rates) < 50:
                return {"action": "HOLD", "confidence": 0, "reasons": ["Insufficient data"]}
            
            closes = [r.close for r in rates]
            current_price = closes[-1]
            
            # Calculate indicators
            rsi = self.calculate_rsi(closes)
            macd = self.calculate_macd(closes)
            
            # Simple moving averages
            ma20 = np.mean(closes[-20:])
            ma50 = np.mean(closes[-50:])
            
            # Calculate recent momentum
            momentum = ((closes[-1] - closes[-5]) / closes[-5]) * 100 if len(closes) >= 5 else 0
            
            # Halal AI Decision Matrix
            action = "HOLD"
            confidence = 0
            reasons = []
            
            # BUY signals
            if rsi < 30 and momentum > -0.5:
                action = "BUY"
                confidence = 0.85
                reasons.append(f"RSI oversold ({rsi:.1f})")
                reasons.append("Stabilizing momentum")
            elif rsi < 45 and ma20 > ma50 and momentum > 0:
                action = "BUY"
                confidence = 0.75
                reasons.append(f"RSI {rsi:.1f} in buy zone")
                reasons.append("Uptrend confirmed")
            elif momentum > 0.3 and ma20 > ma50:
                action = "BUY"
                confidence = 0.70
                reasons.append(f"Positive momentum {momentum:.2f}%")
                reasons.append("Uptrend continuing")
            
            # SELL signals
            if rsi > 75 and momentum < 0.5:
                action = "SELL"
                confidence = 0.85
                reasons.append(f"RSI overbought ({rsi:.1f})")
                reasons.append("Momentum weakening")
            elif rsi > 60 and ma20 < ma50 and momentum < 0:
                action = "SELL"
                confidence = 0.75
                reasons.append(f"RSI {rsi:.1f} in sell zone")
                reasons.append("Downtrend confirmed")
            elif momentum < -0.3 and ma20 < ma50:
                action = "SELL"
                confidence = 0.70
                reasons.append(f"Negative momentum {momentum:.2f}%")
                reasons.append("Downtrend accelerating")
            
            print(f"🤖 AI Signal [{symbol}]: {action} ({confidence*100:.0f}%) - RSI:{rsi:.1f} | {', '.join(reasons)}")
            
            return {
                "action": action,
                "confidence": confidence,
                "reasons": reasons,
                "currentPrice": current_price,
                "rsi": rsi,
                "momentum": momentum
            }
        except Exception as e:
            print(f"AI error: {e}")
            return {"action": "HOLD", "confidence": 0, "reasons": [str(e)]}
    
    async def handle_connection(self, websocket):
        print("✅ Client connected to bridge")
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_id = data.get('id')
                    action = data.get('action')
                    params = data.get('params', {})
                    
                    result = None
                    
                    if action == 'connect':
                        login = params.get('login')
                        password = params.get('password')
                        server = params.get('server')
                        
                        if not mt5.initialize():
                            result = {"success": False, "error": "MT5 initialization failed"}
                        else:
                            authenticated = mt5.login(login, password=password, server=server)
                            if authenticated:
                                account_info = mt5.account_info()
                                balance = account_info.balance if account_info else 0
                                self.connected = True
                                self.login = login
                                self.server = server
                                result = {"success": True, "data": {"balance": balance}}
                            else:
                                result = {"success": False, "error": "Login failed"}
                    
                    elif action == 'getBalance':
                        account_info = mt5.account_info()
                        if account_info:
                            result = {"success": True, "data": account_info.balance}
                        else:
                            result = {"success": False, "error": "Not connected"}
                    
                    elif action == 'getSignal':
                        symbol = params.get('symbol')
                        signal = self.get_ai_signal(symbol)
                        result = {"success": True, "data": signal}
                    
                    elif action == 'getPrice':
                        symbol = params.get('symbol')
                        tick = mt5.symbol_info_tick(symbol)
                        if tick:
                            result = {"success": True, "data": {"bid": tick.bid, "ask": tick.ask}}
                        else:
                            result = {"success": False, "error": f"Cannot get price for {symbol}"}
                    
                    elif action == 'placeOrder':
                        symbol = params.get('symbol')
                        volume = params.get('volume')
                        side = params.get('side')
                        sl = params.get('sl')
                        tp = params.get('tp')
                        
                        order_type = mt5.ORDER_TYPE_BUY if side == 'buy' else mt5.ORDER_TYPE_SELL
                        price = mt5.symbol_info_tick(symbol).ask if side == 'buy' else mt5.symbol_info_tick(symbol).bid
                        
                        request = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": symbol,
                            "volume": volume,
                            "type": order_type,
                            "price": price,
                            "sl": sl,
                            "tp": tp,
                            "deviation": 10,
                            "magic": 234000,
                            "comment": "Halal Bot",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        
                        order_result = mt5.order_send(request)
                        if order_result.retcode == mt5.TRADE_RETCODE_DONE:
                            result = {"success": True, "data": {"orderId": order_result.order, "price": price}}
                        else:
                            result = {"success": False, "error": f"Order failed: {order_result.comment}"}
                    
                    elif action == 'closeOrder':
                        order_id = params.get('orderId')
                        position = mt5.positions_get(ticket=order_id)
                        if position:
                            close_request = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": position[0].symbol,
                                "volume": position[0].volume,
                                "type": mt5.ORDER_TYPE_SELL if position[0].type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                                "position": order_id,
                                "price": mt5.symbol_info_tick(position[0].symbol).bid if position[0].type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position[0].symbol).ask,
                                "deviation": 10,
                                "magic": 234000,
                                "comment": "Close by Halal Bot",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            close_result = mt5.order_send(close_request)
                            if close_result.retcode == mt5.TRADE_RETCODE_DONE:
                                result = {"success": True, "data": {"orderId": close_result.order}}
                            else:
                                result = {"success": False, "error": f"Close failed: {close_result.comment}"}
                        else:
                            result = {"success": False, "error": "Position not found"}
                    
                    if result:
                        response = {"id": msg_id, "success": result["success"], "data": result.get("data"), "error": result.get("error")}
                        await websocket.send(json.dumps(response))
                
                except Exception as e:
                    print(f"Error processing message: {e}")
                    error_response = {"id": msg_id, "success": False, "error": str(e)}
                    await websocket.send(json.dumps(error_response))
        
        except websockets.exceptions.ConnectionClosed:
            print("Client disconnected")
        finally:
            if self.connected:
                mt5.shutdown()
                self.connected = False

async def main():
    print("\n🕋 HALAL EXNESS BRIDGE - Python MT5 Bridge")
    print("✅ Waiting for Node.js bot to connect...")
    print("✅ WebSocket server running on ws://localhost:5001\n")
    
    bridge = HalalExnessBridge()
    async with websockets.serve(bridge.handle_connection, "localhost", 5001):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
