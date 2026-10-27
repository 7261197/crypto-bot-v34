import ccxt
import telebot
import json
import os

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
BOT_TOKEN = '9202486628:AAHVyl1xmgCraqQLDISpruwNcXhHTGi7wug'
CHAT_ID = 534358423

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'DOT/USDT', 'LINK/USDT', 'XRP/USDT', 'LTC/USDT']
TIMEFRAME = '1d'

INITIAL_BALANCE = 1000.0
BASE_ORDER_SIZE = 100.0
SO_MULTIPLIER = 1.5
SO_STEP_PERCENT = 0.05
MAX_SAFETY_ORDERS = 5
TAKE_PROFIT_PERCENT = 0.05
RSI_PERIOD = 14
RSI_ENTRY_THRESHOLD = 35

STATE_FILE = 'bot_state_v34.json'

# ==========================================
# 2. ФУНКЦИИ
# ==========================================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'balance': INITIAL_BALANCE, 'active_deals': [], 'total_trades': 0, 'total_profit': 0.0}

def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=4)

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        ch = prices[i] - prices[i-1]
        gains.append(max(0.0, ch))
        losses.append(max(0.0, -ch))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    rs = ag / al if al != 0 else 100.0
    rsi = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period, len(prices) - 1):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
        rs = ag / al if al != 0 else 100.0
        rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def send_msg(text):
    try:
        bot = telebot.TeleBot(BOT_TOKEN)
        bot.send_message(CHAT_ID, text, parse_mode='Markdown')
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

# ==========================================
# 3. ОСНОВНАЯ ЛОГИКА (как в бэктесте v34)
# ==========================================
def main():
    print("🔄 Проверка рынка по закрытым дневным свечам...")
    state = load_state()
    exchange = ccxt.binance({'enableRateLimit': True, 'timeout': 10000})
    
    for symbol in SYMBOLS:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=40)
            if len(ohlcv) < RSI_PERIOD + 2:
                continue
            
            prev = ohlcv[-2]  # последняя ЗАКРЫТАЯ дневная свеча
            ts, o, h, l, c, v = prev
            confirmed_closes = [x[4] for x in ohlcv[:-1]]
            rsi = calculate_rsi(confirmed_closes, RSI_PERIOD)
            if rsi is None:
                continue
            
            # --- Управление открытой сделкой ---
            for idx, d in enumerate(state['active_deals']):
                if d['symbol'] != symbol:
                    continue
                # Тейк-профит (свеча достала до тейка)
                if h >= d['tp']:
                    revenue = d['coins'] * d['tp']
                    profit = revenue - d['invested']
                    state['balance'] += revenue
                    state['total_trades'] += 1
                    state['total_profit'] += profit
                    state['active_deals'].pop(idx)
                    send_msg(f"✅ *ЗАКРЫТА СДЕЛКА*\n\nМонета: `{symbol}`\nПрибыль: `${profit:.2f}`\nУсреднений было: {d['level']}")
                    continue
                # Усреднение
                if d['level'] < MAX_SAFETY_ORDERS:
                    next_so = d['base_price'] * (1 - (d['level'] + 1) * SO_STEP_PERCENT)
                    if l <= next_so:
                        so_size = BASE_ORDER_SIZE * (SO_MULTIPLIER ** (d['level'] + 1))
                        if state['balance'] >= so_size:
                            state['balance'] -= so_size
                            d['invested'] += so_size
                            d['coins'] += so_size / next_so
                            d['avg_price'] = d['invested'] / d['coins']
                            d['tp'] = d['avg_price'] * (1 + TAKE_PROFIT_PERCENT)
                            d['level'] += 1
                            send_msg(f"📉 *УСРЕДНЕНИЕ*\n\nМонета: `{symbol}`\nНовая средняя: `${d['avg_price']:.2f}`\nУровень: {d['level']}/{MAX_SAFETY_ORDERS}")
            
            # --- Новый вход ---
            active_symbols = [d['symbol'] for d in state['active_deals']]
            if rsi < RSI_ENTRY_THRESHOLD and symbol not in active_symbols and state['balance'] >= BASE_ORDER_SIZE:
                state['balance'] -= BASE_ORDER_SIZE
                state['active_deals'].append({
                    'symbol': symbol,
                    'base_price': c,
                    'avg_price': c,
                    'tp': c * (1 + TAKE_PROFIT_PERCENT),
                    'invested': BASE_ORDER_SIZE,
                    'coins': BASE_ORDER_SIZE / c,
                    'level': 0
                })
                send_msg(f"🟢 *НОВАЯ СДЕЛКА*\n\nМонета: `{symbol}`\nЦена входа: `${c:.2f}`\nRSI: `{rsi:.1f}`\nТейк: `${c * (1 + TAKE_PROFIT_PERCENT):.2f}`")
                
        except Exception as e:
            print(f"Ошибка с {symbol}: {e}")
    
    save_state(state)
    print(f"💰 Баланс: ${state['balance']:.2f} | Активных сделок: {len(state['active_deals'])}")
    print("✅ Проверка завершена.")

if __name__ == '__main__':
    main()
