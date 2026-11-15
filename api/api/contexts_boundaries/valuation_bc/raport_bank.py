"""Raport kwartalny dla banku (docs/bank/raport_RRRRQn.md): operaty kontrolne, pokrycie, odmowy, portfel, LTV.

Źródła: najnowsze wyceny lokali z `wyceny_historia` (zadanie nocne), `operaty` (typ 'kontrolny' z kwartału raportu
i ostatni 'roczny' każdego lokalu), `pms_lokale` + `pms_budynki`. Warunki banku: valuation_bc/zalozenia.yaml.
LTV wymaga kwoty zadłużenia, której nie ma w data/: raport pisze „brak w danych”.
Układ jak każdy raport w docs/ (CLAUDE.md): wnioski, tabele, SQL i kod.
"""

from datetime import date, datetime

import duckdb
import numpy as np
import pandas as pd
from api.adapters import wyceny_historia
from api.contexts_boundaries.valuation_bc.zalozenia import wczytaj_zalozenia

SQL_OPERATY_KONTROLNE = """
SELECT o.id_operatu, o.id_lokalu, o.data_wyceny, o.wartosc_pln AS wartosc_operatu, b.miasto, b.nazwa AS budynek
FROM operaty o JOIN pms_lokale l USING (id_lokalu) JOIN pms_budynki b USING (id_budynku)
WHERE o.typ = 'kontrolny' AND o.data_wyceny >= $od AND o.data_wyceny < $do_wylacznie
ORDER BY o.id_lokalu
"""
SQL_PORTFEL = """
SELECT l.id_lokalu, b.nazwa AS budynek, b.miasto, b.dzielnica, l.metraz, r.wartosc_pln AS operat_roczny,
       r.data_wyceny AS data_operatu_rocznego
FROM pms_lokale l
JOIN pms_budynki b USING (id_budynku)
LEFT JOIN (
    SELECT id_lokalu, wartosc_pln, data_wyceny FROM operaty WHERE typ = 'roczny'
    QUALIFY row_number() OVER (PARTITION BY id_lokalu ORDER BY data_wyceny DESC) = 1
) r USING (id_lokalu)
ORDER BY l.id_lokalu
"""
RODZAJE_POWODOW = (
    ("Miasto ", "miasto spoza treningu albo z małą liczbą transakcji"),
    ("Dzielnica ", "dzielnica z małą liczbą transakcji"),
    ("Metraż ", "metraż poza zakresem treningu"),
    ("Brak roku budowy", "brak roku budowy"),
    ("Rok budowy ", "rok budowy poza zakresem treningu"),
    ("Nietypowy typ lokalu", "nietypowy typ lokalu (pokoje × metraż)"),
    ("Lokal daleko", "lokal daleko od transakcji treningowych (kNN)"),
)


def _f(x: float, miejsca: int = 1) -> str:
    return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def _warszawa(czas) -> str:
    return f"{pd.Timestamp(czas).tz_convert('Europe/Warsaw'):%Y-%m-%d %H:%M} (czas warszawski)"


def _mln(x: float) -> str:
    return _f(x / 1e6, 1) + " mln zł"


def ostatni_kwartal(dzien: date) -> tuple[int, int, date, date]:
    """(rok, numer, pierwszy dzień, ostatni dzień) ostatniego pełnego kwartału przed `dzien`."""
    q_teraz = (dzien.month - 1) // 3 + 1
    rok, q = (dzien.year, q_teraz - 1) if q_teraz > 1 else (dzien.year - 1, 4)
    od = date(rok, 3 * (q - 1) + 1, 1)
    do = (date(rok + 1, 1, 1) if q == 4 else date(rok, 3 * q + 1, 1)) - pd.Timedelta(days=1)
    return rok, q, od, do


def _wyceny_lokali(hcon: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    w = wyceny_historia.ostatnie(hcon, "lokal")
    kolumny = ["id_obiektu", "p10", "p50", "p90", "odmowa", "powod", "czas_przebiegu", "wersja_modelu"]
    return pd.DataFrame(columns=kolumny) if w.empty else w[kolumny]


def dane_operatow(con: duckdb.DuckDBPyConnection, hcon: duckdb.DuckDBPyConnection, kwartal) -> pd.DataFrame:
    """Operaty kontrolne z kwartału + najnowsza wycena lokalu z historii (NaN, gdy lokalu jeszcze nie wyceniono)."""
    _, _, od, do = kwartal
    op = con.execute(SQL_OPERATY_KONTROLNE, {"od": od, "do_wylacznie": do + pd.Timedelta(days=1)}).df()
    w = _wyceny_lokali(hcon).rename(columns={"id_obiektu": "id_lokalu"})
    return op.merge(w, on="id_lokalu", how="left", validate="one_to_one")


def dane_portfela(con: duckdb.DuckDBPyConnection, hcon: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    lok = con.execute(SQL_PORTFEL).df()
    w = _wyceny_lokali(hcon).rename(columns={"id_obiektu": "id_lokalu"})
    return lok.merge(w, on="id_lokalu", how="left", validate="one_to_one")


def metryki_operatow(d: pd.DataFrame, mape_max: float, pokrycie_min: float, pokrycie_max: float) -> dict:
    """Błąd i pokrycie przedziału na lokalach przyjętych przez model (odmowa = brak liczby, liczona osobno)."""
    wycenione = d["odmowa"].notna()
    odmowa = d["odmowa"].eq(True)
    przyj = d[wycenione & ~odmowa & d["p50"].notna()]
    y = przyj["wartosc_operatu"].to_numpy(dtype=float)
    blad = przyj["p50"].to_numpy(dtype=float) / y - 1
    w_przedziale = (y >= przyj["p10"].to_numpy(dtype=float)) & (y <= przyj["p90"].to_numpy(dtype=float))
    mape = float(100 * np.mean(np.abs(blad))) if len(y) else float("nan")
    pokrycie = float(100 * np.mean(w_przedziale)) if len(y) else float("nan")
    return {
        "operaty": len(d),
        "bez_wyceny": int((~wycenione).sum()),
        "odmowy": int(odmowa.sum()),
        "przyjete": len(przyj),
        "mape": mape,
        "mdape": float(100 * np.median(np.abs(blad))) if len(y) else float("nan"),
        "mediana_bledu": float(100 * np.median(blad)) if len(y) else float("nan"),
        "pokrycie": pokrycie,
        "mape_ok": bool(mape <= mape_max),
        "pokrycie_ok": bool(pokrycie_min <= pokrycie <= pokrycie_max),
    }


def portfel(lokale: pd.DataFrame) -> dict:
    """Suma wycen lokali przyjętych przez model; lokale z odmową: suma ostatnich operatów rocznych (informacyjnie)."""
    odm = lokale["odmowa"].eq(True)
    przyj = lokale[lokale["odmowa"].eq(False)]
    return {
        "lokale": len(lokale),
        "przyjete": len(przyj),
        "odmowy": int(odm.sum()),
        "bez_wyceny": int(lokale["odmowa"].isna().sum()),
        "suma_p50": float(przyj["p50"].sum()),
        "suma_p10": float(przyj["p10"].sum()),
        "suma_p90": float(przyj["p90"].sum()),
        "odmowy_operat_roczny": float(lokale.loc[odm, "operat_roczny"].sum()),
    }


def rodzaje_powodow(powody: pd.Series) -> pd.DataFrame:
    """Liczba lokali z danym rodzajem powodu (lokal z kilkoma powodami liczy się w każdym)."""
    czesci = powody.dropna().str.split("; ")
    wiersze = []
    for prefiks, opis in RODZAJE_POWODOW:
        wiersze.append(
            {"powod": opis, "lokale": int(czesci.map(lambda c: any(x.startswith(prefiks) for x in c)).sum())}
        )
    znane = tuple(p for p, _ in RODZAJE_POWODOW)
    inne = int(czesci.map(lambda c: any(not x.startswith(znane) for x in c)).sum())
    wiersze.append({"powod": "inny (np. nietypowy według Isolation Forest)", "lokale": inne})
    return pd.DataFrame(wiersze)


def _md(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(brak wierszy)_"
    linie = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    linie += ["| " + " | ".join("" if pd.isna(x) else str(x) for x in w) + " |" for w in df.itertuples(index=False)]
    return "\n".join(linie)


def raport_markdown(
    con: duckdb.DuckDBPyConnection,
    kwartal,
    d_operaty: pd.DataFrame,
    lokale: pd.DataFrame,
    *,
    czas_przebiegu: datetime | None,
    wersja: str | None,
    czas_raportu: datetime | None = None,
) -> str:
    rok, q, od, do = kwartal
    z = wczytaj_zalozenia()
    mape_max = float(z["bank_mape_max_proc"]["wartosc"])
    pmin, pmax = float(z["bank_pokrycie_min_proc"]["wartosc"]), float(z["bank_pokrycie_max_proc"]["wartosc"])
    m = metryki_operatow(d_operaty, mape_max, pmin, pmax)
    lokale_pms = int(con.execute("SELECT count(*) FROM pms_lokale").fetchone()[0])
    p = portfel(lokale) if not lokale.empty else None
    odmowy = lokale[lokale["odmowa"].eq(True)] if not lokale.empty else pd.DataFrame()

    tak_nie = {True: "spełniony", False: "niespełniony"}
    wnioski = [
        (
            f"Na {m['operaty']} operatach kontrolnych z okresu {od:%d.%m.%Y}–{do:%d.%m.%Y} model wycenił "
            f"{m['przyjete']} lokali i pomylił się średnio o {_f(m['mape'], 2)}% (warunek banku: najwyżej "
            f"{_f(mape_max, 0)}%), więc warunek jest {tak_nie[m['mape_ok']]}."
            if m["przyjete"]
            else f"W okresie {od:%d.%m.%Y}–{do:%d.%m.%Y} nie ma operatów kontrolnych z wyceną modelu (brak w danych)."
        ),
        (
            f"Wartość z operatu mieściła się w przedziale wyceny (P10–P90) w {_f(m['pokrycie'], 1)}% przypadków "
            f"(norma {_f(pmin, 0)}–{_f(pmax, 0)}%), więc warunek jest {tak_nie[m['pokrycie_ok']]}."
            if m["przyjete"]
            else "Pokrycia przedziału nie da się policzyć bez wycen."
        ),
    ]
    if p:
        wnioski.append(
            f"Model nie wycenił {_f(p['odmowy'], 0)} z {_f(p['lokale'], 0)} lokali portfela "
            f"({_f(100 * p['odmowy'] / p['lokale'], 1)}%) "
            f"i odpowiedział „nie wiem” z podaniem powodu. Te lokale wymagają wyceny rzeczoznawcy (tabela 5)."
        )
        wnioski.append(
            f"Wartość portfela według modelu to {_mln(p['suma_p50'])} dla {_f(p['przyjete'], 0)} lokali. "
            "Lokale bez wyceny "
            f"modelu miały w ostatnich operatach rocznych łącznie {_mln(p['odmowy_operat_roczny'])}."
        )
    else:
        wnioski.append(f"Brak wycen lokali w historii: wartości portfela ({_f(lokale_pms, 0)} lokali) nie policzono.")
    wnioski.append("LTV nie da się policzyć: w danych nie ma kwoty zadłużenia portfela (brak w danych).")

    t1 = pd.DataFrame(
        [
            {
                "Operaty": m["operaty"],
                "Bez wyceny w historii": m["bez_wyceny"],
                "Odmowy": m["odmowy"],
                "Przyjęte": m["przyjete"],
                "MAPE": f"{_f(m['mape'], 2)}%",
                "MdAPE": f"{_f(m['mdape'], 2)}%",
                "Mediana błędu ze znakiem": f"{_f(m['mediana_bledu'], 2)}%",
                "Pokrycie P10–P90": f"{_f(m['pokrycie'], 1)}%",
                f"MAPE ≤ {_f(mape_max, 0)}%": tak_nie[m["mape_ok"]],
                f"Pokrycie {_f(pmin, 0)}–{_f(pmax, 0)}%": tak_nie[m["pokrycie_ok"]],
            }
        ]
    )
    miasta = []
    for miasto, g in d_operaty.groupby("miasto"):
        mm = metryki_operatow(g, mape_max, pmin, pmax)
        miasta.append(
            {"Miasto": miasto, "Operaty": mm["operaty"], "Odmowy": mm["odmowy"], "MAPE": f"{_f(mm['mape'], 2)}%",
             "Pokrycie": f"{_f(mm['pokrycie'], 1)}%", "Mediana błędu": f"{_f(mm['mediana_bledu'], 2)}%"}  # fmt: skip
        )
    t2 = pd.DataFrame(miasta)
    if p:
        t3 = pd.DataFrame(
            [
                {
                    "Lokale (PMS)": p["lokale"],
                    "Wycenione przez model": p["przyjete"],
                    "Suma P50": _mln(p["suma_p50"]),
                    "Suma P10": _mln(p["suma_p10"]),
                    "Suma P90": _mln(p["suma_p90"]),
                    "Odmowy": p["odmowy"],
                    "Ostatni operat roczny lokali z odmową": _mln(p["odmowy_operat_roczny"]),
                }
            ]
        )
        t5a = rodzaje_powodow(odmowy["powod"]).rename(columns={"powod": "Rodzaj powodu", "lokale": "Lokale"})
        t5 = odmowy.assign(metraz=odmowy["metraz"].map(lambda x: _f(x, 1)))[
            ["id_lokalu", "budynek", "miasto", "dzielnica", "metraz", "powod"]
        ].rename(columns={"id_lokalu": "Lokal", "budynek": "Budynek", "miasto": "Miasto", "dzielnica": "Dzielnica",
                          "metraz": "Metraż m²", "powod": "Powód"})  # fmt: skip
    else:
        t3 = t5a = t5 = pd.DataFrame()
    odm_operaty = d_operaty[d_operaty["odmowa"].eq(True)][["id_lokalu", "budynek", "miasto", "powod"]]

    stan = (
        f"Stan wycen: przebieg zadania nocnego z {_warszawa(czas_przebiegu)}, model `{wersja}`."
        if czas_przebiegu is not None
        else "Stan wycen: brak przebiegu zadania nocnego w historii."
    )
    utworzono = f" Raport utworzono {_warszawa(czas_raportu)}." if czas_raportu else ""
    return f"""# Raport kwartalny dla banku: wycena portfela Domilo, {rok} Q{q}

Okres raportu: {od:%Y-%m-%d} – {do:%Y-%m-%d}. {stan}{utworzono}
Dane: eksport 2026-09-30 23:59 Europe/Warsaw (`domilo.duckdb`); wyceny: tabela `wyceny_historia`.

## Wnioski

{chr(10).join(f"{i}. {w}" for i, w in enumerate(wnioski, 1))}

## Tabele

### 1. Sprawdzian na operatach kontrolnych (warunki banku z zalozenia.yaml)

Błąd = (wycena P50 − wartość operatu) / wartość operatu, liczony na lokalach przyjętych przez model. Odmowa to
odpowiedź „nie wiem”, bez liczby.

{_md(t1)}

### 2. Operaty kontrolne według miasta

{_md(t2)}

### 3. Wartość portfela

Suma P10 i suma P90 to sumy granic przedziałów pojedynczych lokali, a nie przedział 80% dla całego portfela (błędy
wycen lokali są ze sobą powiązane). Lokale z odmową nie mają wyceny modelu. Dla porównania podajemy ich ostatni
operat roczny.

{_md(t3)}

### 4. LTV

Brak w danych: LTV = zadłużenie zabezpieczone portfelem / wartość portfela, a w `data/` nie ma kwoty kredytu ani
zadłużenia. Do policzenia LTV potrzebna jest kwota od użytkownika (wpis w `valuation_bc/zalozenia.yaml` ze źródłem).

### 5. Odmowy („nie wiem”) z powodami

Rodzaje powodów (lokal z kilkoma powodami liczy się w każdym):

{_md(t5a)}

Odmowy wśród lokali z operatem kontrolnym:

{_md(odm_operaty.rename(columns={"id_lokalu": "Lokal", "budynek": "Budynek", "miasto": "Miasto", "powod": "Powód"}))}

Wszystkie lokale portfela z odmową:

{_md(t5)}

## SQL i kod

Raport tworzy krok `raport-kwartalny` funkcji Inngest `wyceny-nocne` (`api/api/inngest_app.py`) przez
`api.contexts_boundaries.valuation_bc.nocne.przebieg_raportu` i `raport_bank.raport`. Ręcznie, z katalogu `api/`:
`poetry run python -m api.contexts_boundaries.valuation_bc.nocne --nadpisz-raport`.

Najnowsza wycena każdego lokalu (`api/api/adapters/wyceny_historia.py`):

```sql
SELECT * FROM wyceny_historia
WHERE rodzaj = 'lokal'
QUALIFY row_number() OVER (PARTITION BY rodzaj, id_obiektu ORDER BY czas_przebiegu DESC) = 1;
```

Operaty kontrolne z kwartału (`$od` = {od}, `$do_wylacznie` = {do + pd.Timedelta(days=1):%Y-%m-%d}):

```sql
{SQL_OPERATY_KONTROLNE.strip()}
```

Portfel i ostatni operat roczny:

```sql
{SQL_PORTFEL.strip()}
```

Metryki: `metryki_operatow` (MAPE = średnia |P50 / operat − 1| na przyjętych, pokrycie = odsetek operatów w
[P10; P90]), `portfel` (sumy P50, P10, P90 lokali przyjętych), `rodzaje_powodow` (prefiksy powodów detektora OOD
`versions/v3_przedzialy/ood.py`). Warunki banku: `bank_mape_max_proc`, `bank_pokrycie_min_proc`,
`bank_pokrycie_max_proc` z `valuation_bc/zalozenia.yaml`.
"""


def raport(con: duckdb.DuckDBPyConnection, kwartal, czas_raportu: datetime | None = None) -> str:
    """Raport z bazy, w której są i dane, i historia wycen (domilo.duckdb)."""
    d = dane_operatow(con, con, kwartal)
    lokale = dane_portfela(con, con)
    w = _wyceny_lokali(con)
    czas = w["czas_przebiegu"].max() if not w.empty else None
    wersja = w.loc[w["czas_przebiegu"] == czas, "wersja_modelu"].iloc[0] if czas is not None else None
    if lokale["odmowa"].isna().all():
        lokale = pd.DataFrame()
    return raport_markdown(con, kwartal, d, lokale, czas_przebiegu=czas, wersja=wersja, czas_raportu=czas_raportu)
