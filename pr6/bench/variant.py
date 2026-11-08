"""Версія за варіантом 2: мінімальні типи даних.

Відрізняється від optimized.py лише типами під час читання CSV:
  city_id — category (замість int32): 1 байт коду на рядок,
            бо в даних лише два міста;
  pm25    — float32 (замість float64): 4 байти замість 8.
Решта розрахунку не змінюється. Через category групування
виконується з observed=True: групи лише для міст, які
є в даних, а не для всіх можливих категорій.

Порівняння пам'яті таблиці (з папки pr6):
  python -m bench.variant
"""
import pandas as pd

from bench.common import (CITY_IDS, COLUMNS, EU_DAILY_2030,
                          MIN_HOURS, WHO_DAILY, YEARS,
                          raw_file, who_level)
from bench import optimized

# ВАРІАНТ 2: мінімальні типи для двох числових стовпців.
# Категорії задано явно: з рядком "category" pandas 2.x
# зчитав би коди міст як текст ("2", "219"), і фільтр за
# числовими id відкинув би всі рядки. Значення поза списком
# категорій стають NaN і відкидаються фільтром isin.
DTYPES = {"city_id": pd.CategoricalDtype(sorted(CITY_IDS)),
          "pm25": "float32"}


def load() -> pd.DataFrame:
    # Як у optimized: кожен файл — один раз, лише 3 стовпці,
    # але з мінімальними типами
    frames = [pd.read_csv(raw_file(y),
                          usecols=["city_id", "pm25",
                                   "logged_at"],
                          dtype=DTYPES)
              for y in YEARS]
    # однакові категорії в усіх файлах → concat зберігає category
    df = pd.concat(frames, ignore_index=True)
    df = df[df["city_id"].isin(list(CITY_IDS))]
    df["logged_at"] = pd.to_datetime(
        df["logged_at"], format="%Y-%m-%d %H:%M:%S")
    df = df.drop_duplicates(subset=["city_id", "logged_at"])
    return df[df["pm25"].between(0, 1000)]


def compute_indicators() -> pd.DataFrame:
    df = load()
    day = df["logged_at"].dt.floor("D")
    # observed=True: лише наявні комбінації категорій
    daily = (df.groupby(["city_id", day], observed=True)["pm25"]
               .agg(["mean", "count"]))
    valid = daily.loc[daily["count"] >= MIN_HOURS, "mean"]
    city = valid.index.get_level_values("city_id")
    year = valid.index.get_level_values("logged_at").year

    ind = valid.groupby([city, year], observed=True).agg(
        annual_mean="mean",
        valid_days="size",
        days_over_15=lambda s: int((s > WHO_DAILY).sum()),
        days_over_25=lambda s: int((s > EU_DAILY_2030).sum()),
    )
    ind.index.names = ["city_id", "year"]
    years = ind.index.get_level_values("year")
    ind["days_in_year"] = [366 if y % 4 == 0 else 365
                           for y in years]
    ind["completeness_pct"] = (ind["valid_days"]
                               / ind["days_in_year"] * 100)
    ind["who_level"] = ind["annual_mean"].map(who_level)
    return ind[COLUMNS]


def memory_report() -> None:
    """Пам'ять таблиці вимірів: optimized проти variant."""
    v_opt = optimized.load().memory_usage(deep=True)
    v_var = load().memory_usage(deep=True)
    t = pd.DataFrame({"optimized, байт": v_opt,
                      "variant, байт": v_var})
    t.loc["разом"] = t.sum()
    t["Δmem, %"] = ((1 - t["variant, байт"]
                     / t["optimized, байт"]) * 100).round(1)
    print("Пам'ять таблиці після load() — "
          "df.memory_usage(deep=True):")
    print(t.to_string())
    print("\nТипи стовпців:")
    print(pd.DataFrame({"optimized": optimized.load().dtypes,
                        "variant": load().dtypes}).to_string())


if __name__ == "__main__":
    memory_report()
