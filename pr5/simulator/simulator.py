"""Симулятор мережі індивідуальних теплових пунктів (ПР5, варіант 2).

Кожен ІТП — окремий MQTT-клієнт. Кожні INTERVAL секунд він публікує
вимір у тему kharkiv/heat/<id>/telemetry, а свій стан (online/offline)
— у тему kharkiv/heat/<id>/status.
Поля виміру: t_sup — температура подавального трубопроводу T_под, °C;
t_ret — зворотного T_зв, °C; g — витрата теплоносія G, м³/год;
t_out — температура зовнішнього повітря (датчик погодного регулятора), °C.
Сценарій подій повторюється кожні CYCLE секунд.
"""
import argparse
import json
import math
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

# ---------- Параметри мережі ІТП ----------
# g_nom — номінальна витрата контуру опалення будинку, м³/год
STATIONS = [
    {"id": "itp-01", "name": "5-поверховий будинок", "g_nom": 2.2},
    {"id": "itp-02", "name": "9-поверховий будинок", "g_nom": 3.2},
    {"id": "itp-03", "name": "16-поверховий будинок", "g_nom": 4.0},
]
PREFIX = "kharkiv/heat"
INTERVAL = 5      # період вимірювання, с
PHI = 0.8         # інерційність ряду AR(1), 0 ≤ φ < 1
SIGMA_T = 0.4     # шум температури подачі, °C
SIGMA_G = 0.02    # шум витрати, частка від g_nom
GLITCH_P = 0.02   # імовірність збою сенсора

# ---------- Погода і температурний графік ----------
T_OUT_MEAN = -3.0   # середня температура повітря, °C
T_OUT_AMP = 3.0     # амплітуда добового ходу, °C (максимум о 15:00)
T_IN = 20.0         # розрахункова температура в квартирах, °C
T_OUT_CALC = -3.0   # температура, для якої задано номінальний режим
T_SUP_NOM = 72.0    # T_под при T_OUT_CALC, °C
DT_NOM = 22.0       # T_под − T_зв при T_OUT_CALC, °C

# ---------- Сценарій подій (секунди від початку циклу) ----
CYCLE = 600                          # 10 хв
WARM = (30, 270, 13.0)               # відлига: t_out → +13 °C (уся мережа)
PUMP = ("itp-02", 300, 420)          # зупинка циркуляційного насоса: G → 0
OUTAGE = ("itp-03", 450, 570)        # знеструмлення контролера


def outdoor_temp(hour: float) -> float:
    """Формула (3'): добовий хід температури повітря, максимум о 15:00."""
    return T_OUT_MEAN + T_OUT_AMP * math.cos(2 * math.pi * (hour - 15) / 24)


def warm_weight(phase: float) -> float:
    """Частка відлиги 0…1: плавний перехід за 60 с на початку й у кінці."""
    start, end, _ = WARM
    if not start <= phase < end:
        return 0.0
    return min(1.0, (phase - start) / 60, (end - phase) / 60)


def load_fraction(t_out: float) -> float:
    """Відносне теплове навантаження: 1 при T_OUT_CALC, 0 при T_IN."""
    return max(0.0, (T_IN - t_out) / (T_IN - T_OUT_CALC))


class Station:
    """Один ІТП: власне MQTT-з'єднання і власні ряди."""

    def __init__(self, cfg, host, port):
        self.id = cfg["id"]
        self.g_nom = cfg["g_nom"]
        self.dev_t = 0.0         # відхилення T_под від графіка (AR(1))
        self.dev_g = 0.0         # відхилення G від номіналу (AR(1))
        self.f = None            # навантаження з інерцією будинку
        self.g = self.g_nom      # поточна витрата
        self.t_ret = None        # поточна T_зв
        self.online = False
        self.host, self.port = host, port
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"sim-{self.id}")
        # «Заповіт» (Last Will): брокер сам опублікує offline,
        # якщо ІТП зникне без коректного від'єднання
        self.c.will_set(self.topic("status"), "offline",
                        qos=1, retain=True)
        self.c.on_connect = self.on_connect

    def topic(self, kind):
        return f"{PREFIX}/{self.id}/{kind}"

    def on_connect(self, client, userdata, flags, rc, props):
        client.publish(self.topic("status"), "online",
                       qos=1, retain=True)

    def start(self):
        self.c.connect(self.host, self.port, keepalive=10)
        self.c.loop_start()       # окремий потік обміну
        self.online = True

    def power_cut(self):
        """Знеструмлення: ІТП просто замовкає —
        без DISCONNECT і без сигналів keep-alive."""
        self.c.loop_stop()
        self.online = False

    def power_on(self):
        self.c.reconnect()    # нове з'єднання з брокером
        self.c.loop_start()
        self.online = True

    def stop(self):
        """Коректне вимкнення: offline публікуємо самі."""
        self.c.publish(self.topic("status"), "offline",
                       qos=1, retain=True).wait_for_publish(2)
        self.c.disconnect()
        self.c.loop_stop()

    def measure(self, t_out, pump_stopped):
        # Температурний графік: T_под і ΔT пропорційні навантаженню f;
        # будинок реагує на погоду з інерцією τ = 30 с (прискорено)
        f = load_fraction(t_out)
        self.f = f if self.f is None else f + (self.f - f) * math.exp(-INTERVAL / 30)
        # Формула (4): AR(1) для відхилень T_под і G від графіка
        self.dev_t = PHI * self.dev_t + SIGMA_T * random.gauss(0, 1)
        self.dev_g = PHI * self.dev_g + SIGMA_G * random.gauss(0, 1)
        t_sup = T_IN + (T_SUP_NOM - T_IN) * self.f + self.dev_t
        t_ret_graph = t_sup - DT_NOM * self.f
        if pump_stopped:
            # Насос вибігає за ~10 с, G → 0,05 м³/год;
            # вода в будинку остигає до 25 °C з τ = 120 с
            self.g = 0.05 + (self.g - 0.05) * math.exp(-INTERVAL / 10)
            self.t_ret = 25 + (self.t_ret - 25) * math.exp(-INTERVAL / 120)
        else:
            g_target = self.g_nom * (1 + self.dev_g)
            # після пуску насоса витрата відновлюється за ~10 с
            self.g = g_target + (self.g - g_target) * math.exp(-INTERVAL / 10)
            if self.t_ret is None or self.t_ret >= t_ret_graph - 0.5:
                self.t_ret = t_ret_graph
            else:   # після простою холодна вода прогрівається з τ = 15 с
                self.t_ret = t_ret_graph + (self.t_ret - t_ret_graph) * math.exp(-INTERVAL / 15)
        m = {
            "ts": int(time.time() * 1000),  # мс від 1970 р.
            "t_sup": round(t_sup, 1),
            "t_ret": round(min(self.t_ret, t_sup), 1),
            "g": round(max(self.g, 0.0), 2),
            "t_out": round(t_out, 1),
        }
        if random.random() < GLITCH_P:   # збій сенсора
            field, code = random.choice([("t_sup", -127.0),  # обрив термодатчика
                                         ("t_ret", -127.0),
                                         ("g", -1.0)])        # помилка витратоміра
            m[field] = code
        return m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    random.seed(args.seed)

    stations = [Station(s, args.host, args.port)
                for s in STATIONS]
    for s in stations:
        s.start()
    print(f"Підключено до {args.host}:{args.port}. "
          "Ctrl+C — зупинити.")
    t0 = time.monotonic()
    try:
        while True:
            phase = (time.monotonic() - t0) % CYCLE
            now = datetime.now()
            hour = now.hour + now.minute / 60
            w = warm_weight(phase)
            t_out = (1 - w) * outdoor_temp(hour) + w * WARM[2]
            for s in stations:
                cut = (s.id == OUTAGE[0]
                       and OUTAGE[1] <= phase < OUTAGE[2])
                if cut and s.online:
                    s.power_cut()
                    print(f"{now:%H:%M:%S} {s.id} ЗНЕСТРУМЛЕНО")
                elif not cut and not s.online:
                    s.power_on()
                    print(f"{now:%H:%M:%S} {s.id} живлення відновлено")
                if not s.online:
                    continue
                pump = (s.id == PUMP[0] and PUMP[1] <= phase < PUMP[2])
                m = s.measure(t_out, pump)
                s.c.publish(s.topic("telemetry"), json.dumps(m), qos=1)
                note = " НАСОС ЗУПИНЕНО" if pump else ""
                print(f"{now:%H:%M:%S} {s.id} t_sup={m['t_sup']:>6} "
                      f"t_ret={m['t_ret']:>6} g={m['g']:>5} "
                      f"t_out={m['t_out']:>5}{note}")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("Зупинка…")
    finally:
        for s in stations:
            if s.online:
                s.stop()


if __name__ == "__main__":
    main()
