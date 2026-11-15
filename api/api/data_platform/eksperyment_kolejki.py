"""Moc i analiza eksperymentu switchback kolejki (docs/kolejka_eksperyment.md). Dane: modele dbt w schemacie metryki.

Uruchomienie: `cd api && poetry run python -m api.data_platform.eksperyment_kolejki`
Wynik: api/api/data_platform/wyniki/eksperyment_moc.json (wszystkie liczby raportu).

Założenia testu (ustalone przed eksperymentem): dwa warianty, po n/2 tygodni; test t dwustronny, alfa 5%, moc 80%;
efekt i MDE względem średniej metryki. Korekta (ANCOVA, CUPED dla tygodni) = regresja metryki tygodnia na wariant
i zmienne znane bez względu na wariant: godziny doradców w tygodniu i nowe zapytania w tym i poprzednim tygodniu
(k = 2 zmienne, df = n − 2 − k). Zmienność po korekcie liczymy z reszt leave-one-out na historii (bez dopasowania do
tych samych tygodni), więc nie jest zaniżona.
Tłumienie: metryka według tygodnia podpisania zbiera w tygodniu t wartość z kontaktów z tygodni t, t−1, … (wagi
z danych). Przy zmianie wariantu co tydzień różnica wariantów to tylko część prawdziwego efektu; liczymy ją symulacją
tego samego losowania planu (pary tygodni), a tygodnie przed startem mają wariant `model` (domyślny w zadaniu).
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

KATALOG_WYNIKOW = Path(__file__).resolve().with_name("wyniki")
ALFA = 0.05
MOC = 0.80
EFEKT_DOCELOWY = 0.15
TYGODNIE = (12, 16)
SIATKA_TYGODNI = (12, 16, 20, 24, 30, 44)
OKRES = ("2025-07-07", "2026-06-22")  # pierwszy i ostatni tydzień (poniedziałki) jak w docs/kolejka_metryki.md, T3
KWARTAL_WYJSCIOWY = "2026-04-01"
ZIARNO = 20261115
POWTORZEN_TLUMIENIA = 20_000

# --- statystyka (czyste funkcje, testowane w api/tests/test_eksperyment_kolejki.py) ----------------------------------


def moc_testu(efekt_w_sd: float, n: int, k: int = 0, alfa: float = ALFA) -> float:
    """Moc dwustronnego testu t dla różnicy dwóch wariantów po n/2 tygodni (efekt w odchyleniach standardowych)."""
    df = n - 2 - k
    if df < 1:
        return float("nan")
    ncp = efekt_w_sd / math.sqrt(4 / n)
    t_kr = stats.t.ppf(1 - alfa / 2, df)
    moc = stats.nct.sf(t_kr, df, ncp) + stats.nct.cdf(-t_kr, df, ncp)
    return 1.0 if math.isnan(moc) and ncp > t_kr else float(moc)  # nct daje NaN dla bardzo dużych ncp


def mde(cv: float, n: int, k: int = 0, moc: float = MOC, alfa: float = ALFA) -> float:
    """Najmniejszy efekt (ułamek średniej) wykrywalny z mocą `moc`; cv = odchylenie / średnia (ułamek)."""
    efekt = optimize.brentq(lambda d: moc_testu(d, n, k, alfa) - moc, 1e-9, 12.0)
    return float(efekt * cv)


def mde_normalne(cv: float, n: int, moc: float = MOC, alfa: float = ALFA) -> float:
    """Przybliżenie normalne (z zamiast t): (z_{1−α/2} + z_moc) × cv × √(4/n)."""
    return float((stats.norm.ppf(1 - alfa / 2) + stats.norm.ppf(moc)) * cv * math.sqrt(4 / n))


def tygodnie_dla(efekt: float, cv: float, k: int = 0, tlumienie=lambda n: 1.0, maks: int = 400) -> int | None:
    """Najmniejsza parzysta liczba tygodni, przy której prawdziwy efekt `efekt` (ułamek średniej) ma moc >= MOC.

    `tlumienie(n)`: jaka część prawdziwego efektu trafia do metryki przy n tygodniach (1 = cała)."""
    for n in range(max(4, k + 4), maks + 1, 2):
        if moc_testu(efekt * tlumienie(n) / cv, n, k) >= MOC:
            return n
    return None


def cv_loo(y: np.ndarray, zmienne: list[np.ndarray]) -> float:
    """Odchylenie reszt leave-one-out z regresji y na zmienne (z wyrazem wolnym), jako ułamek średniej y."""
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(len(y))] + [np.asarray(z, dtype=float) for z in zmienne])
    reszty = []
    for i in range(len(y)):
        m = np.ones(len(y), dtype=bool)
        m[i] = False
        b = np.linalg.lstsq(X[m], y[m], rcond=None)[0]
        reszty.append(y[i] - X[i] @ b)
    return float(np.std(reszty, ddof=1) / y.mean())


def cv_surowe(y: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    return float(y.std(ddof=1) / y.mean())


def plan_par(n: int, rng: np.random.Generator) -> np.ndarray:
    """1 = tydzień modelu, 0 = kontrolny; pary z losową kolejnością (jak eksperyment.wylosuj_plan)."""
    return np.concatenate([rng.permutation([1, 0]) for _ in range(n // 2)])


def tlumienie_podpisan(wagi: np.ndarray, n: int, powtorzen: int = POWTORZEN_TLUMIENIA, ziarno: int = ZIARNO) -> float:
    """Oczekiwana różnica wariantów metryki według tygodnia podpisania na jednostkę prawdziwego efektu.

    `wagi[j]`: udział wartości podpisanej w tygodniu t, która pochodzi z kontaktów z tygodnia t − j (suma 1).
    Tygodnie przed startem mają wariant model (1)."""
    rng = np.random.default_rng(ziarno)
    wagi = np.asarray(wagi, dtype=float) / np.sum(wagi)
    L = len(wagi)
    wyniki = []
    for _ in range(powtorzen):
        a = np.concatenate([np.ones(L - 1), plan_par(n, rng)])
        y = np.array([wagi @ a[t - np.arange(L)] for t in range(L - 1, L - 1 + n)])
        w = a[L - 1 :]
        wyniki.append(y[w == 1].mean() - y[w == 0].mean())
    return float(np.mean(wyniki))


def analiza(tygodnie: pd.DataFrame, metryka: str, zmienne=("godziny_doradcow", "nowe_zapytania_2tyg")) -> dict:
    """Wynik eksperymentu: regresja metryki tygodnia na wariant (model = 1) i zmienne korekty.

    `tygodnie`: kolumny wariant ('model' / 'od_najnowszego'), metryka i zmienne. Zwraca efekt (zł/h i % średniej
    w tygodniach kontrolnych), przedział 95%, p i liczbę tygodni."""
    df = tygodnie.dropna(subset=[metryka, *zmienne])
    y = df[metryka].to_numpy(dtype=float)
    a = (df["wariant"] == "model").to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(y)), a] + [df[z].to_numpy(dtype=float) for z in zmienne])
    st = len(y) - X.shape[1]
    if st < 1 or a.sum() == 0 or a.sum() == len(a):
        return {"tygodnie": len(y), "efekt": None, "uwaga": "za mało tygodni albo jeden wariant"}
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    reszty = y - X @ b
    s2 = reszty @ reszty / st
    se = math.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    t = b[1] / se
    kr = stats.t.ppf(1 - ALFA / 2, st)
    srednia_kontroli = y[a == 0].mean()
    return {
        "tygodnie": len(y),
        "tygodnie_model": int(a.sum()),
        "efekt": float(b[1]),
        "efekt_proc_kontroli": float(b[1] / srednia_kontroli),
        "przedzial_95": [float(b[1] - kr * se), float(b[1] + kr * se)],
        "p": float(2 * stats.t.sf(abs(t), st)),
        "stopnie_swobody": int(st),
    }


# --- dane z modeli dbt --------------------------------------------------------------------------------------------

SQL_TYGODNIE = """
SELECT p.poczatek_okresu AS tydzien, p.godziny_doradcow, p.podpisania_z_zapytan, p.wartosc_umow_z_zapytan,
       p.przychod_na_godzine_doradcy,
       k.nowe_zapytania + k.nowe_zapytania_poprzedni_tydzien AS nowe_zapytania_2tyg,
       k.przychod_z_kontaktow_na_godzine, k.przychod_z_kontaktow_bez_limitu_na_godzine,
       k.umowy_z_kontaktow_na_godzine, k.kompletny
FROM metryki.przychod_na_godzine_doradcy AS p
JOIN metryki.przychod_z_kontaktow AS k ON k.tydzien = p.poczatek_okresu
WHERE p.okres = 'tydzien' AND p.pelny_okres AND p.poczatek_okresu BETWEEN DATE '{od}' AND DATE '{do}'
ORDER BY tydzien
"""
# Q2: skąd przychodzi wartość podpisana w tygodniu: tydzień pierwszego kontaktu (opóźnienie w tygodniach).
SQL_OPOZNIENIE = """
SELECT date_diff('week', cast(date_trunc('week', k.data_kolejki_kontaktu) AS date),
                 cast(date_trunc('week', w.data_podpisania) AS date)) AS opoznienie_tyg,
       count(*) AS umowy, sum(w.wartosc_umowy) AS wartosc
FROM metryki.wartosc_umowy AS w
JOIN metryki.pierwszy_kontakt AS k USING (id_leada)
WHERE w.z_zapytania AND NOT k.kontakt_cc AND w.data_podpisania BETWEEN DATE '{od}' AND DATE '{do}' + INTERVAL 6 DAY
GROUP BY 1 ORDER BY 1
"""
SQL_WYJSCIOWA = """
SELECT przychod_na_godzine_doradcy, godziny_doradcow FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'kwartal' AND poczatek_okresu = DATE '{kwartal}'
"""
# Koszt części losowej: EV kolejek dnia z 5% pozycji losowych wobec EV pierwszych k × 40 zapytań rankingu miasta.
SQL_KOSZT_LOSOWYCH = """
WITH r AS (SELECT * FROM kolejka_ranking WHERE data_kolejki = (SELECT max(data_kolejki) FROM kolejka_historia)),
d AS (SELECT miasto, count(DISTINCT id_doradcy) AS doradcy, count(id_doradcy) AS pozycje FROM r GROUP BY miasto)
SELECT (SELECT max(data_kolejki) FROM r) AS data_kolejki,
       (SELECT sum(ev_pln) FROM r WHERE id_doradcy IS NOT NULL) AS ev_kolejek,
       (SELECT sum(r.ev_pln) FROM r JOIN d USING (miasto) WHERE r.ranga <= d.pozycje) AS ev_bez_losowych,
       (SELECT sum(ev_pln) FROM r WHERE id_doradcy IS NOT NULL AND id_leada IN
           (SELECT id_leada FROM kolejka_historia WHERE losowa AND data_kolejki = (SELECT max(data_kolejki) FROM r)))
           AS ev_losowych,
       (SELECT count(*) FROM kolejka_historia WHERE losowa AND data_kolejki = (SELECT max(data_kolejki) FROM r))
           AS pozycje_losowe
"""
# Metryka pomocnicza: konwersja górnego decyla w pełnych tygodniach symulacji wstecz (docs/kolejka_panel.md, T2).
SQL_DECYL = """
SELECT tydzien, zapytania_decyl, konwersja_decyl, adopcja, adopcja_losowa
FROM metryki.panel_tydzien
WHERE zrodlo_kolejki = 'symulacja_wstecz' AND dni_kolejki = 7 AND konwersja_decyl IS NOT NULL
ORDER BY tydzien
"""

ZMIENNE_KOREKTY = ["godziny_doradcow", "nowe_zapytania_2tyg"]


def kandydaci(df: pd.DataFrame, tlumienie_n: dict[int, float]) -> list[dict]:
    """Metryki główne do porównania: zmienność, tłumienie i MDE dla 12 i 16 tygodni oraz tygodnie dla +15%."""
    zmienne = [df[z].to_numpy(dtype=float) for z in ZMIENNE_KOREKTY]
    tl_podp = lambda n: tlumienie_n.get(n) or tlumienie_n[max(tlumienie_n)]  # noqa: E731
    opisy = [
        ("przychod_na_godzine_doradcy", "przychód na godzinę, tydzień podpisania (z polecenia)", False, True, True),
        ("przychod_na_godzine_doradcy", "jw. z korektą (godziny, nowe zapytania)", True, True, True),
        ("przychod_z_kontaktow_bez_limitu_na_godzine", "przychód z kontaktów tygodnia na godzinę", False, False, True),
        ("przychod_z_kontaktow_na_godzine", "jw., wartość umowy do 95. percentyla", False, False, True),
        ("przychod_z_kontaktow_na_godzine", "jw. z korektą (proponowana metryka główna)", True, False, True),
        (
            "umowy_z_kontaktow_na_godzine",
            "umowy z kontaktów tygodnia na godzinę z korektą (bez zł)",
            True,
            False,
            False,
        ),
    ]
    wyniki = []
    for kolumna, opis, korekta, podpisania, zl in opisy:
        y = df[kolumna].to_numpy(dtype=float)
        cv = cv_loo(y, zmienne) if korekta else cv_surowe(y)
        k = len(zmienne) if korekta else 0
        tl = tl_podp if podpisania else (lambda n: 1.0)
        w = {
            "metryka": kolumna,
            "opis": opis,
            "korekta": korekta,
            "w_zlotowkach": zl,
            "srednia": float(y.mean()),
            "cv": cv,
            "zmiennych_korekty": k,
            "tlumienie": {str(n): tl(n) for n in TYGODNIE},
            "tygodnie_dla_15_proc": tygodnie_dla(EFEKT_DOCELOWY, cv, k, tl),
            # gdyby cały efekt trafiał do metryki (bez przenoszenia między tygodniami)
            "tygodnie_dla_15_proc_bez_tlumienia": tygodnie_dla(EFEKT_DOCELOWY, cv, k),
        }
        w["mde_siatka"] = {str(n): mde(cv, n, k) / tl(n) for n in SIATKA_TYGODNI}
        for n in TYGODNIE:
            w[f"mde_{n}"] = mde(cv, n, k)
            w[f"mde_{n}_normalne"] = mde_normalne(cv, n)
            w[f"mde_{n}_prawdziwego_efektu"] = mde(cv, n, k) / tl(n)
        wyniki.append(w)
    return wyniki


def policz(con) -> dict:
    od, do = OKRES
    df = con.execute(SQL_TYGODNIE.format(od=od, do=do)).df()
    if not df["kompletny"].all():
        raise RuntimeError("Tygodnie bez pełnych 45 dni na umowy w okresie zmienności")
    opoz = con.execute(SQL_OPOZNIENIE.format(od=od, do=do)).df()
    wagi = (opoz["wartosc"] / opoz["wartosc"].sum()).to_numpy()
    tlumienie_n = {n: tlumienie_podpisan(wagi, n) for n in sorted({*TYGODNIE, 20, 24, 30, 40, 50})}
    wyjsciowa, godziny_q2 = con.execute(SQL_WYJSCIOWA.format(kwartal=KWARTAL_WYJSCIOWY)).fetchone()
    godziny_tyg = float(df["godziny_doradcow"].mean())
    decyl = con.execute(SQL_DECYL).df()
    m1 = df["przychod_na_godzine_doradcy"].to_numpy(dtype=float)
    lista = kandydaci(df, tlumienie_n)

    def zl_tydz(proc: float) -> float:  # % przychodu na godzinę -> zł wartości umów tygodniowo (średnie godziny)
        return proc * wyjsciowa * godziny_tyg

    pieniadze = {
        "wartosc_wyjsciowa_zl_h": float(wyjsciowa),
        "srednie_godziny_tygodniowo": godziny_tyg,
        "efekt_15_proc_zl_h": EFEKT_DOCELOWY * wyjsciowa,
        "efekt_15_proc_zl_tydzien": zl_tydz(EFEKT_DOCELOWY),
    }
    for w in lista:
        for n in TYGODNIE:
            w[f"mde_{n}_prawdziwego_efektu_zl_h"] = w[f"mde_{n}_prawdziwego_efektu"] * wyjsciowa
            w[f"mde_{n}_prawdziwego_efektu_zl_tydzien"] = zl_tydz(w[f"mde_{n}_prawdziwego_efektu"])
        if w["tygodnie_dla_15_proc"]:
            # tygodnie kontrolne = połowa; koszt, jeśli model naprawdę daje +15%: tyle wartości umów nie powstanie
            w["koszt_tygodni_kontrolnych_przy_15_proc_zl"] = w["tygodnie_dla_15_proc"] / 2 * zl_tydz(EFEKT_DOCELOWY)
    koszt_n = {str(n): n / 2 * zl_tydz(EFEKT_DOCELOWY) for n in TYGODNIE}
    koszt_losowych = con.execute(SQL_KOSZT_LOSOWYCH).df().to_dict("records")[0]
    if koszt_losowych["data_kolejki"] is not None:
        koszt_losowych["data_kolejki"] = str(pd.Timestamp(koszt_losowych["data_kolejki"]).date())
    cv_decyl = cv_surowe(decyl["konwersja_decyl"].to_numpy(dtype=float)) if len(decyl) > 2 else None
    wynik = {
        "okres": {"od": od, "do": do, "tygodnie": len(df)},
        "zalozenia": {"alfa": ALFA, "moc": MOC, "efekt_docelowy": EFEKT_DOCELOWY, "zmienne_korekty": ZMIENNE_KOREKTY},
        "metryka_z_polecenia": {
            "srednia": float(m1.mean()),
            "odchylenie": float(m1.std(ddof=1)),
            "cv": cv_surowe(m1),
            "autokorelacja_lag1": float(np.corrcoef(m1[:-1], m1[1:])[0, 1]),
        },
        "opoznienie_kontakt_podpisanie": [
            {
                "opoznienie_tyg": int(r.opoznienie_tyg),
                "umowy": int(r.umowy),
                "udzial_wartosci": float(r.wartosc / opoz["wartosc"].sum()),
            }
            for r in opoz.itertuples()
        ],
        "tlumienie_metryki_podpisan": {str(n): t for n, t in tlumienie_n.items()},
        "kandydaci": lista,
        "pieniadze": pieniadze,
        "koszt_tygodni_kontrolnych_przy_15_proc_zl": koszt_n,
        "koszt_czesci_losowej": {
            k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in koszt_losowych.items()
        },
        "pomocnicze": {
            "konwersja_decyla": {
                "tygodnie": len(decyl),
                "srednia": float(decyl["konwersja_decyl"].mean()) if len(decyl) else None,
                "cv": cv_decyl,
                "zapytan_decyla_tygodniowo": float(decyl["zapytania_decyl"].mean()) if len(decyl) else None,
                **({f"mde_{n}": mde(cv_decyl, n) for n in TYGODNIE} if cv_decyl else {}),
            },
            "adopcja_przed_wdrozeniem": {
                "srednia": float(decyl["adopcja"].mean()) if len(decyl) else None,
                "losowo": float(decyl["adopcja_losowa"].mean()) if len(decyl) else None,
            },
        },
    }
    KATALOG_WYNIKOW.mkdir(exist_ok=True)
    (KATALOG_WYNIKOW / "eksperyment_moc.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=2), "utf-8")
    return wynik


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie() as polaczenie_bazy:
        w = policz(polaczenie_bazy)
    print(json.dumps({k: v for k, v in w.items() if k != "kandydaci"}, ensure_ascii=False, indent=1))
    for k in w["kandydaci"]:
        print(
            f"{k['opis'][:60]:60} cv {100 * k['cv']:5.2f}% tł12 {k['tlumienie']['12']:.3f} "
            f"MDE12 {100 * k['mde_12']:5.1f}% MDE16 {100 * k['mde_16']:5.1f}% "
            f"prawdz12 {100 * k['mde_12_prawdziwego_efektu']:6.1f}% "
            f"prawdz16 {100 * k['mde_16_prawdziwego_efektu']:6.1f}% "
            f"tyg15 {k['tygodnie_dla_15_proc']} (bez tłumienia {k['tygodnie_dla_15_proc_bez_tlumienia']})"
        )
