"""Симулятор мережі станцій моніторингу повітря (ПР5).

Кожна станція — окремий MQTT-клієнт. Кожні INTERVAL секунд
вона публікує вимір у тему kharkiv/air/<id>/telemetry, а свій
стан (online/offline) — у тему kharkiv/air/<id>/status.
Сценарій подій повторюється кожні CYCLE секунд.
"""
import argparse
import json
import math
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

# ---------- Параметри мережі станцій ----------
STATIONS = [
    {"id": "kh-01", "name": "Центр", "base": 9.0},
    {"id": "kh-02", "name": "Салтівка", "base": 11.0},
    {"id": "kh-03", "name": "ХТЗ", "base": 14.0},
]
PREFIX = "kharkiv/air"
INTERVAL = 5      # період вимірювання, с
PHI = 0.8         # інерційність ряду AR(1), 0 ≤ φ < 1
SIGMA = 1.5       # стандартне відхилення шуму, мкг/м³
GLITCH_P = 0.02   # імовірність збою сенсора

# ---------- Сценарій подій (секунди від початку циклу) ----
CYCLE = 600                            # 10 хв
SMOKE = ("kh-02", 120, 240, 4.0)       # задимлення: ×4
OUTAGE = ("kh-03", 360, 480)           # знеструмлення


def daily_factor(hour: float) -> float:
    """Формула (3): добовий профіль, максимум о 21:00."""
    return 1 + 0.35 * math.cos(2 * math.pi * (hour - 21) / 24)


class Station:
    """Одна станція: власне MQTT-з'єднання і власний ряд."""

    def __init__(self, cfg, host, port):
        self.id = cfg["id"]
        self.base = cfg["base"]
        self.x = None            # попереднє значення ряду
        self.mu = None           # попереднє середнє μ
        self.online = False
        self.host, self.port = host, port
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=f"sim-{self.id}")
        # «Заповіт» (Last Will): брокер сам опублікує offline,
        # якщо станція зникне без коректного від'єднання
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
        """Знеструмлення: станція просто замовкає —
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

    def measure(self, hour, smoke):
        # Формула (4): AR(1) навколо добового профілю
        mu = self.base * daily_factor(hour)
        if self.x is None:
            self.x, self.mu = mu, mu
        eps = random.gauss(0, 1)
        x = mu + PHI * (self.x - self.mu) + SIGMA * eps
        self.x, self.mu = max(x, 0.5), mu
        pm25 = self.x * smoke
        if random.random() < GLITCH_P:   # збій сенсора
            pm25 = random.choice([-1.0, 9999.0])
        return {
            "ts": int(time.time() * 1000),  # мс від 1970 р.
            "pm25": round(pm25, 1),
            "t": round(8 + 4 * math.sin(
                2 * math.pi * (hour - 9) / 24)
                + random.gauss(0, 0.3), 1),
            "rh": round(min(100, max(20, 75
                        + random.gauss(0, 3))), 1),
        }


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
            for s in stations:
                cut = (s.id == OUTAGE[0]
                       and OUTAGE[1] <= phase < OUTAGE[2])
                if cut and s.online:
                    s.power_cut()
                    print(f"{now:%H:%M:%S} {s.id} "
                          "ЗНЕСТРУМЛЕНО")
                elif not cut and not s.online:
                    s.power_on()
                    print(f"{now:%H:%M:%S} {s.id} "
                          "живлення відновлено")
                if not s.online:
                    continue
                smoke = (SMOKE[3] if s.id == SMOKE[0]
                         and SMOKE[1] <= phase < SMOKE[2]
                         else 1.0)
                m = s.measure(hour, smoke)
                s.c.publish(s.topic("telemetry"),
                            json.dumps(m), qos=1)
                print(f"{now:%H:%M:%S} {s.id} "
                      f"pm25={m['pm25']:>7} t={m['t']:>5} "
                      f"rh={m['rh']:>5}")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("Зупинка…")
    finally:
        for s in stations:
            if s.online:
                s.stop()


if __name__ == "__main__":
    main()
