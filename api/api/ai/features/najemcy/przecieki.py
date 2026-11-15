"""Tabele do docs/przecieki_najemcy.md: cechy liczone poprawnie (stan na migawkę) wobec wersji z przeciekiem.

Uruchomienie (z katalogu api/, po `pypyr baza`): `poetry run python -m api.ai.features.najemcy.przecieki`.
AUC pojedynczej cechy względem odejdzie (sklearn.metrics.roc_auc_score; braki pominięte). AUC < 0,5 znaczy,
że wyższa wartość cechy idzie w parze z przedłużeniem.
"""

import duckdb
import pandas as pd
from api.ai.features.najemcy.cechy import KOLUMNY_CECH
from sklearn.metrics import roc_auc_score

# 1. Logowania i odsłony oferty: pełne miesiące przed migawką / z miesiącem migawki / sam miesiąc migawki.
SQL_LOGOWANIA = """
WITH m AS (
    SELECT mg.id_umowy, mg.id_najemcy, mg.odejdzie, mg.data_migawki, date_trunc('month', mg.data_migawki) AS mies_m,
           date_trunc('month', n.data_wprowadzenia)::DATE AS mies_wpr
    FROM migawki_najemcy AS mg JOIN pms_najmy AS n USING (id_najmu)
),
l AS (SELECT id_najemcy, strptime(miesiac, '%Y-%m')::DATE AS mies, liczba_logowan, odslony_oferty_przedluzenia
      FROM portal_logowania_mies)
SELECT
    m.id_umowy, m.odejdzie,
    sum(l.odslony_oferty_przedluzenia) FILTER (WHERE l.mies >= m.mies_m - INTERVAL 3 MONTH AND l.mies < m.mies_m)
        AS odslony_pelne_3m,
    sum(l.odslony_oferty_przedluzenia) FILTER (WHERE l.mies > m.mies_m - INTERVAL 3 MONTH AND l.mies <= m.mies_m)
        AS odslony_z_miesiacem_migawki_3m,
    sum(l.odslony_oferty_przedluzenia) FILTER (WHERE l.mies = m.mies_m) AS odslony_miesiac_migawki,
    sum(l.liczba_logowan) FILTER (WHERE l.mies >= m.mies_m - INTERVAL 3 MONTH AND l.mies < m.mies_m)
        AS logowania_pelne_3m,
    sum(l.liczba_logowan) FILTER (WHERE l.mies > m.mies_m - INTERVAL 3 MONTH AND l.mies <= m.mies_m)
        AS logowania_z_miesiacem_migawki_3m
FROM m LEFT JOIN l ON l.id_najemcy = m.id_najemcy AND l.mies >= m.mies_wpr
GROUP BY ALL
"""

# Ile dni miesiąca migawki przypada na dzień migawki i później (średnio).
SQL_DNI_PO_MIGAWCE = """
WITH m AS (
    SELECT data_migawki, date_trunc('month', data_migawki)::DATE AS poczatek,
           (date_trunc('month', data_migawki) + INTERVAL 1 MONTH)::DATE AS koniec
    FROM migawki_najemcy
)
SELECT round(100 * avg(date_diff('day', data_migawki, koniec) / date_diff('day', poczatek, koniec)), 1)
    AS pct_dni_miesiaca_od_migawki
FROM m
"""

# Wiadomość z ofertą przedłużenia (portal_wiadomosci, do_najemcy, temat 'przedłużenie') względem dnia migawki.
SQL_OFERTA = """
SELECT date_diff('day', m.data_migawki, w.data_czas::DATE) AS dni_od_migawki, count(*) AS wiadomosci
FROM migawki_najemcy AS m
JOIN portal_wiadomosci AS w
    ON w.id_najemcy = m.id_najemcy AND w.kierunek = 'do_najemcy' AND w.temat = 'przedłużenie'
   AND w.data_czas >= m.data_migawki - INTERVAL 30 DAY AND w.data_czas < m.data_do + INTERVAL 1 DAY
GROUP BY 1 ORDER BY 2 DESC LIMIT 5
"""

# 2. Czynsz: względem czynsz_katalogowy własnego lokalu (stan na eksport) i względem nowych umów sprzed migawki.
SQL_CZYNSZ = """
SELECT year(m.data_migawki) AS rok_migawki, count(*) AS umowy,
       round(median(c.czynsz / l.czynsz_katalogowy), 3) AS med_czynsz_do_katalogu,
       round(median(c.czynsz_do_podobnych), 3) AS med_czynsz_do_podobnych
FROM migawki_najemcy AS m
JOIN cechy_najemcy AS c USING (id_umowy)
JOIN pms_lokale AS l USING (id_lokalu)
GROUP BY 1 ORDER BY 1
"""
SQL_CZYNSZ_AUC = """
SELECT m.odejdzie, year(m.data_migawki) AS rok_migawki, c.czynsz / l.czynsz_katalogowy AS czynsz_do_katalogu,
       c.czynsz_do_podobnych
FROM migawki_najemcy AS m JOIN cechy_najemcy AS c USING (id_umowy) JOIN pms_lokale AS l USING (id_lokalu)
"""

# 3. Płatności: końcowe dni_opoznienia (wersja naiwna) wobec opóźnienia znanego w dniu migawki.
SQL_PLATNOSCI = """
WITH plat AS (
    SELECT u.id_najmu, strptime(p.miesiac, '%Y-%m')::DATE + 9 AS termin, max(p.dni_opoznienia) AS dni_opoznienia
    FROM pms_platnosci AS p JOIN pms_umowy AS u USING (id_umowy) GROUP BY u.id_najmu, p.miesiac
),
naiwne AS (
    SELECT m.id_umowy, max(p.dni_opoznienia) AS plat_max_naiwne
    FROM migawki_najemcy AS m
    JOIN plat AS p ON p.id_najmu = m.id_najmu AND p.termin >= m.data_migawki - 90 AND p.termin < m.data_migawki
    GROUP BY 1
)
SELECT m.id_umowy, m.odejdzie, c.plat_max_opoznienie_90d, n.plat_max_naiwne, c.plat_zalegle_na_migawke
FROM migawki_najemcy AS m JOIN cechy_najemcy AS c USING (id_umowy) LEFT JOIN naiwne AS n USING (id_umowy)
"""

# 4. Zgłoszenia otwarte: status (stan na eksport) wobec zamknieto względem migawki.
SQL_ZGLOSZENIA = """
SELECT m.id_umowy, m.odejdzie, c.zgl_otwarte_na_migawke,
       count(z.id_zgloszenia) FILTER (WHERE z.status = 'otwarte') AS zgl_otwarte_status_eksport
FROM migawki_najemcy AS m
JOIN cechy_najemcy AS c USING (id_umowy)
JOIN pms_najmy AS n USING (id_najmu)
LEFT JOIN portal_zgloszenia AS z
    ON z.id_najemcy = m.id_najemcy AND z.id_lokalu = m.id_lokalu
   AND z.utworzono::DATE >= n.data_wprowadzenia::DATE AND z.utworzono::DATE < m.data_migawki
GROUP BY ALL
"""

# 5. Ankieta: ostatnia odpowiedź przed migawką (ASOF) wobec ostatniej odpowiedzi w najmie do dnia eksportu.
SQL_ANKIETA = """
WITH ost AS (
    SELECT m.id_umowy, arg_max(a.wynik_0_10, a.data_odpowiedzi) AS wynik_do_eksportu
    FROM migawki_najemcy AS m JOIN pms_najmy AS n USING (id_najmu)
    JOIN ankiety_satysfakcji AS a
        ON a.id_najemcy = m.id_najemcy AND a.data_odpowiedzi IS NOT NULL
       AND a.data_odpowiedzi::DATE >= n.data_wprowadzenia::DATE
    GROUP BY 1
)
SELECT m.id_umowy, m.odejdzie, c.ankieta_ostatni_wynik, o.wynik_do_eksportu
FROM migawki_najemcy AS m JOIN cechy_najemcy AS c USING (id_umowy) LEFT JOIN ost AS o USING (id_umowy)
"""

# Oferta z retencja_decyzje względem dnia migawki (dni od migawki do data_oferty).
SQL_RETENCJA = """
SELECT date_diff('day', m.data_migawki, r.data_oferty::DATE) AS dni_od_migawki, count(*) AS oferty
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE r.data_oferty IS NOT NULL
GROUP BY 1 ORDER BY 1
"""

# 6. Okna sięgające przed początek danych zdarzeniowych (2023-01-01).
SQL_POCZATEK = """
SELECT count(*) FILTER (WHERE data_migawki - 90 < DATE '2023-01-01') AS okno_90d_przed_danymi,
       count(*) FILTER (WHERE data_migawki - 365 < DATE '2023-01-01') AS okno_365d_przed_danymi,
       count(*) AS umowy
FROM migawki_najemcy
"""


def auc(y: pd.Series, x: pd.Series) -> float:
    maska = x.notna()
    return round(float(roc_auc_score(y[maska], x[maska])), 3)


def tabele(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    wynik: dict[str, pd.DataFrame] = {}

    log = con.execute(SQL_LOGOWANIA).df()
    wiersze = []
    for kol in (
        "odslony_pelne_3m",
        "odslony_z_miesiacem_migawki_3m",
        "odslony_miesiac_migawki",
        "logowania_pelne_3m",
        "logowania_z_miesiacem_migawki_3m",
    ):
        x = log[kol]
        wiersze.append(
            {
                "cecha": kol,
                "umowy_z_danymi": int(x.notna().sum()),
                "pct_z_wartoscia_gt_0": round(100 * float((x > 0).mean()), 2),
                "pct_odejsc_gdy_gt_0": round(100 * float(log.loc[x > 0, "odejdzie"].mean()), 2),
                "pct_odejsc_gdy_0": round(100 * float(log.loc[x == 0, "odejdzie"].mean()), 2),
                "auc": auc(log["odejdzie"], x),
            }
        )
    wynik["logowania"] = pd.DataFrame(wiersze)
    wynik["dni_po_migawce"] = con.execute(SQL_DNI_PO_MIGAWCE).df()
    wynik["oferta"] = con.execute(SQL_OFERTA).df()

    wynik["czynsz"] = con.execute(SQL_CZYNSZ).df()
    cz = con.execute(SQL_CZYNSZ_AUC).df()
    wynik["czynsz_auc"] = pd.DataFrame(
        [
            {
                "cecha": k,
                "auc_odejdzie": auc(cz["odejdzie"], cz[k]),
                "auc_rok_od_2025": auc(cz["rok_migawki"] >= 2025, cz[k]),
            }
            for k in ("czynsz_do_katalogu", "czynsz_do_podobnych")
        ]
    )

    pl = con.execute(SQL_PLATNOSCI).df()
    rozne = pl["plat_max_naiwne"].fillna(-1) != pl["plat_max_opoznienie_90d"].fillna(-1)
    wynik["platnosci"] = pd.DataFrame(
        [
            {
                "umowy": len(pl),
                "umowy_z_rozna_wartoscia": int(rozne.sum()),
                "umowy_z_zaleglosc_na_migawke": int((pl["plat_zalegle_na_migawke"] > 0).sum()),
                "auc_naiwne": auc(pl["odejdzie"], pl["plat_max_naiwne"]),
                "auc_na_migawke": auc(pl["odejdzie"], pl["plat_max_opoznienie_90d"]),
            }
        ]
    )

    zg = con.execute(SQL_ZGLOSZENIA).df()
    wynik["zgloszenia"] = pd.DataFrame(
        [
            {
                "cecha": k,
                "umowy_z_otwartym": int((zg[k] > 0).sum()),
                "auc": auc(zg["odejdzie"], zg[k]),
            }
            for k in ("zgl_otwarte_na_migawke", "zgl_otwarte_status_eksport")
        ]
    )

    an = con.execute(SQL_ANKIETA).df()
    rozne_an = an["wynik_do_eksportu"].fillna(-1) != an["ankieta_ostatni_wynik"].fillna(-1)
    wynik["ankieta"] = pd.DataFrame(
        [
            {
                "umowy": len(an),
                "umowy_z_rozna_wartoscia": int(rozne_an.sum()),
                "auc_na_migawke": auc(an["odejdzie"], an["ankieta_ostatni_wynik"]),
                "auc_do_eksportu": auc(an["odejdzie"], an["wynik_do_eksportu"]),
            }
        ]
    )
    wynik["poczatek_danych"] = con.execute(SQL_POCZATEK).df()
    wynik["retencja_oferta"] = con.execute(SQL_RETENCJA).df()

    cechy = con.execute(
        "SELECT m.odejdzie, c.* FROM migawki_najemcy AS m JOIN cechy_najemcy AS c USING (id_umowy)"
    ).df()
    cechy["linia_b2b"] = (cechy["linia"] == "B2B").astype(float)
    liczbowe = ["linia_b2b", *(k for k in KOLUMNY_CECH if k != "linia")]
    wynik["auc_cech"] = pd.DataFrame(
        [{"cecha": k, "auc": auc(cechy["odejdzie"], cechy[k].astype(float))} for k in liczbowe]
    )
    return wynik


if __name__ == "__main__":
    from api.adapters.duckdb_baza import polaczenie

    with polaczenie() as polaczenie_bazy:
        for nazwa, tabela in tabele(polaczenie_bazy).items():
            print(f"\n## {nazwa}\n{tabela.to_string(index=False)}")
