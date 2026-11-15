"""Dwie pułapki targetu kolejki i zestawienie wersji (docs/kolejka_bias.md, tabele B10–B12).

Uruchomienie (po `pypyr baza`; czyta leady_cel i metryki.json wersji, nie uczy modeli):
    cd api && poetry run python -m api.ai.lead_model.evals.analiza_cenzura_kontakt

- B10 cenzurowanie: zapytania utworzone 2026-08-16 – 2026-09-30 (czas warszawski). Porównujemy konwersję liczoną
  naiwnie (zapytanie bez umowy do dnia eksportu = 0, także gdy minęło mniej niż 45 dni) z wynikiem przy poprawnym
  cenzurowaniu: (a) definicja `leady_cel` (wynik tylko dla zapytań, które miały pełne 45 dni), (b) estymator
  Kaplana–Meiera P(umowa w 45 dni), który bierze każde zapytanie na tyle dni, ile było obserwowane do eksportu.
  Sprawdzian KM: ten sam rachunek przy udawanym eksporcie 2026-05-31 23:59 dla zapytań 2026-04-16 – 2026-05-31,
  dla których prawdziwe `umowa_45d` jest znane.
- B11 czas do pierwszego kontaktu (`leady_cel.godz_do_pierwszego_kontaktu`): konwersja przy kontakcie ≤ 1 dnia
  (≤ 24 h), 1–7 dni, > 7 dni (> 168 h) i bez kontaktu w 45 dni, osobno poza oknem migracji i w oknie; niecenzurowane.
- B12 zestawienie v0, v1, v2, v2b: AUC i lift@10% w oknie migracji z metryki.json, tokeny / 1 000 zapytań z v1.
Wynik: tabele na standardowym wyjściu i evals/wyniki/cenzura_kontakt.json.
"""

import json

import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.ai.lead_model.evals.ewaluacja import KATALOG_MODELU, KATALOG_WYNIKOW

HORYZONT_DNI = 45

# Zapytania z okresu [od, do) z czasem obserwacji do „eksportu” i czasem do umowy (o ile umowa była przed eksportem).
SQL_OKRES = """
SELECT
    id_leada,
    utworzono,
    umowa_45d,
    cenzurowany,
    zamkniety,
    epoch(?::TIMESTAMPTZ - utworzono) / 86400.0 AS dni_obserwacji,
    CASE WHEN data_umowy < ?::TIMESTAMPTZ THEN dni_do_umowy END AS dni_do_umowy_przed_eksportem
FROM leady_cel
WHERE utworzono >= ?::TIMESTAMPTZ AND utworzono < ?::TIMESTAMPTZ
"""

SQL_KONTAKT = """
SELECT
    CASE WHEN okno_migracji THEN 'w oknie migracji' ELSE 'poza oknem migracji' END AS okres,
    CASE
        WHEN NOT obsluzony THEN '4 brak kontaktu w 45 dni'
        WHEN godz_do_pierwszego_kontaktu <= 24 THEN '1 ≤ 1 dzień'
        WHEN godz_do_pierwszego_kontaktu <= 168 THEN '2 1–7 dni'
        ELSE '3 > 7 dni'
    END AS pierwszy_kontakt,
    count(*) AS zapytania,
    sum(umowa_45d) AS umowy,
    avg(umowa_45d) AS konwersja
FROM leady_cel
WHERE NOT cenzurowany
GROUP BY ALL
ORDER BY okres DESC, pierwszy_kontakt
"""

# Ten sam podział poza oknem według źródła (czy efekt nie wynika tylko z tego, że `domteraz` czeka dłużej).
SQL_KONTAKT_ZRODLO = """
SELECT
    zrodlo,
    count(*) FILTER (WHERE godz_do_pierwszego_kontaktu <= 24) AS zapytania_le_1d,
    avg(umowa_45d) FILTER (WHERE godz_do_pierwszego_kontaktu <= 24) AS konwersja_le_1d,
    count(*) FILTER (WHERE godz_do_pierwszego_kontaktu > 168) AS zapytania_gt_7d,
    avg(umowa_45d) FILTER (WHERE godz_do_pierwszego_kontaktu > 168) AS konwersja_gt_7d
FROM leady_cel
WHERE NOT cenzurowany AND NOT okno_migracji AND obsluzony
GROUP BY zrodlo
ORDER BY zrodlo
"""


def kaplan_meier(czas: np.ndarray, zdarzenie: np.ndarray, horyzont: float = HORYZONT_DNI) -> dict:
    """1 − S(horyzont) i 95% CI (Greenwood, na skali S). `czas`: dni do umowy albo do końca obserwacji."""
    czas, zdarzenie = np.asarray(czas, dtype=float), np.asarray(zdarzenie, dtype=bool)
    s, suma_greenwood = 1.0, 0.0
    for t in np.unique(czas[zdarzenie & (czas <= horyzont)]):
        n = int((czas >= t).sum())
        d = int(((czas == t) & zdarzenie).sum())
        s *= 1 - d / n
        if n > d:
            suma_greenwood += d / (n * (n - d))
    se = s * np.sqrt(suma_greenwood)
    return {
        "p_umowa_45d": float(1 - s),
        "ci95": [float(max(0.0, 1 - s - 1.96 * se)), float(min(1.0, 1 - s + 1.96 * se))],
        "w_ryzyku_na_koncu": int((czas >= horyzont).sum()),
    }


def _tydzien(utworzono: pd.Series) -> pd.Series:
    dzien = pd.to_datetime(utworzono, utc=True).dt.tz_convert("Europe/Warsaw").dt.normalize().dt.tz_localize(None)
    return dzien.dt.to_period("W-SAT").dt.start_time.dt.date.astype(str)


def analiza_okresu(con, od: str, do: str, eksport: str, prawda_znana: bool) -> dict:
    df = con.execute(SQL_OKRES, [eksport, eksport, od, do]).df()
    obserwacja = df["dni_obserwacji"].clip(upper=HORYZONT_DNI)
    umowa = df["dni_do_umowy_przed_eksportem"]
    zdarzenie = umowa.notna() & (umowa <= HORYZONT_DNI)
    czas = np.where(zdarzenie, umowa, obserwacja)
    pelne = df["dni_obserwacji"] >= HORYZONT_DNI
    df = df.assign(umowa_do_eksportu=zdarzenie.astype(int), pelne_45d=pelne, tydzien=_tydzien(df["utworzono"]))
    tygodnie = (
        df.groupby("tydzien")
        .agg(
            zapytania=("id_leada", "size"),
            umowy_do_eksportu=("umowa_do_eksportu", "sum"),
            naiwna_otwarte_0=("umowa_do_eksportu", "mean"),
            mediana_dni_obserwacji=("dni_obserwacji", "median"),
            z_pelnymi_45d=("pelne_45d", "sum"),
        )
        .reset_index()
    )
    if prawda_znana:
        tygodnie = tygodnie.merge(df.groupby("tydzien")["umowa_45d"].mean().rename("prawdziwa_umowa_45d"), on="tydzien")
    wynik = {
        "okres": f"{od} – {do} (bez prawej granicy), eksport {eksport}",
        "zapytania": len(df),
        "umowy_do_eksportu": int(zdarzenie.sum()),
        "naiwna_otwarte_0": float(zdarzenie.mean()),
        "z_pelnymi_45d": int(pelne.sum()),
        "konwersja_tylko_pelne_45d": float(zdarzenie[pelne].mean()) if pelne.any() else None,
        "kaplan_meier": kaplan_meier(czas, zdarzenie),
        "tygodnie": tygodnie.to_dict("records"),
    }
    if prawda_znana:
        wynik["prawdziwa_umowa_45d"] = float(df["umowa_45d"].mean())
    return wynik


def zestawienie_wersji() -> list[dict]:
    wersje = KATALOG_MODELU / "versions"
    v1 = json.loads((wersje / "v1_llm_zero_shot" / "metryki.json").read_text(encoding="utf-8"))
    v2b = json.loads((wersje / "v2b_lgbm_ipw" / "metryki.json").read_text(encoding="utf-8"))
    okno = v2b["okno_migracji"]  # wszystkie wersje na tych samych 5 320 zapytaniach, v0 uczona na treningu v2
    tokeny = {k: v1["koszt_na_1000"][k] for k in ("tokeny_wejscia", "tokeny_wejscia_z_cache", "tokeny_wyjscia")}
    return [
        {"wersja": w, "auc": okno[w]["auc"], "lift_10": okno[w]["lift_10"], "tokeny_na_1000": t}
        for w, t in (
            ("v0_regula_zrodla", None),
            ("v1_llm_zero_shot", tokeny),
            ("v2_lgbm_naiwny", tokeny),
            ("v2b_lgbm_ipw", tokeny),
        )
    ]


def main() -> dict:
    con = polacz()
    wynik = {
        "B10_cenzurowanie": analiza_okresu(
            con, "2026-08-16", "2026-10-01", "2026-10-01 00:00:00+02", prawda_znana=False
        ),
        "B10_sprawdzian_km": analiza_okresu(
            con, "2026-04-16", "2026-06-01", "2026-06-01 00:00:00+02", prawda_znana=True
        ),
        "B11_kontakt": con.execute(SQL_KONTAKT).df().to_dict("records"),
        "B11_kontakt_zrodlo": con.execute(SQL_KONTAKT_ZRODLO).df().to_dict("records"),
        # punkt odniesienia: konwersja 45 dni w ostatnich pełnych miesiącach (niecenzurowane)
        "B10_miesiace_odniesienia": con.execute(
            """SELECT strftime(utworzono, '%Y-%m') AS miesiac, count(*) AS zapytania, avg(umowa_45d) AS konwersja
               FROM leady_cel WHERE NOT cenzurowany AND utworzono >= TIMESTAMPTZ '2026-04-01'
               GROUP BY 1 ORDER BY 1"""
        )
        .df()
        .to_dict("records"),
        "B12_wersje": zestawienie_wersji(),
    }
    con.close()
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    (KATALOG_WYNIKOW / "cenzura_kontakt.json").write_text(
        json.dumps(wynik, ensure_ascii=False, indent=2, default=_json), encoding="utf-8"
    )
    print(json.dumps(wynik, ensure_ascii=False, indent=1, default=_json))
    return wynik


def _json(o):
    if isinstance(o, np.generic):
        return o.item()
    if o is pd.NA or (isinstance(o, float) and np.isnan(o)):
        return None
    return str(o)


if __name__ == "__main__":
    main()
