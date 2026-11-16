"""Historia awarii wind w Serwisowniku: tabele do docs/b4_historia_awarii.md.

Czyta domilo.duckdb (tabele serwis_* z `api.adapters.serwisownik`, tabela pochodna `zgloszenia_wind`).
Uruchomienie (z katalogu api/): `python -m api.ai.failure_model.evals.historia_awarii [R1 R2 ...]`
— wypisuje tabele Markdown (wszystkie albo wybrane).

Losowanie notatek (R9) jest powtarzalne: kolejność według md5(id_notatki || ':' || ZIARNO), pierwsze 30.
"""

import sys
from decimal import Decimal

import duckdb

ZIARNO = "b4_historia_awarii"
LICZBA_NOTATEK = 30

ZAPYTANIA: dict[str, str] = {
    # Serwisownik ogółem
    "R1": """
SELECT
    (SELECT count(*) FROM serwis_zgloszenia) AS zgloszenia,
    (SELECT count(*) FROM serwis_notatki) AS notatki,
    (SELECT count(DISTINCT id_zgloszenia) FROM serwis_notatki) AS zgloszenia_z_notatka,
    (SELECT count(*) FROM serwis_czesci) AS pozycje_czesci,
    (SELECT count(DISTINCT id_zgloszenia) FROM serwis_czesci) AS zgloszenia_z_czesciami,
    (SELECT sum(koszt_netto) FROM serwis_czesci) AS koszt_czesci_netto,
    (SELECT strftime(min(utworzono), '%Y-%m-%d %H:%M') FROM serwis_zgloszenia) AS pierwsze,
    (SELECT strftime(max(utworzono), '%Y-%m-%d %H:%M') FROM serwis_zgloszenia) AS ostatnie,
    (SELECT count(*) FROM serwis_zgloszenia
      WHERE utworzono >= '2025-10-26 02:00' AND utworzono < '2025-10-26 03:00') AS zgl_w_podwojnej_godzinie
""",
    # Które zgłoszenia dotyczą wind: typ_urzadzenia × co jest w id_urzadzenia
    "R2": """
SELECT
    z.typ_urzadzenia,
    count(*) AS zgloszenia,
    count(*) FILTER (w.id_windy IS NOT NULL) AS id_to_winda,
    count(*) FILTER (z.id_urzadzenia IS NOT NULL AND w.id_windy IS NULL) AS id_inne_urzadzenie,
    count(*) FILTER (z.id_urzadzenia IS NULL) AS id_puste,
    count(*) FILTER (w.id_windy IS NOT NULL OR (z.id_urzadzenia IS NULL AND z.typ_urzadzenia = 'winda'))
        AS dotyczy_windy
FROM serwis_zgloszenia AS z
LEFT JOIN serwis_windy AS w ON w.id_windy = z.id_urzadzenia
GROUP BY ROLLUP (z.typ_urzadzenia)
ORDER BY z.typ_urzadzenia IS NULL, zgloszenia DESC
""",
    # Ustalenie windy w zgłoszeniach wind
    "R3": """
SELECT
    ustalenie_windy,
    count(*) AS zgloszenia,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS proc,
    count(DISTINCT id_budynku) AS budynki,
    list(DISTINCT liczba_wind_budynku ORDER BY liczba_wind_budynku) AS liczba_wind_w_budynku
FROM zgloszenia_wind
GROUP BY ustalenie_windy
ORDER BY zgloszenia DESC
""",
    # Budynki według liczby wind
    "R3b": """
SELECT liczba_wind, count(*) AS budynki, list(id_budynku ORDER BY id_budynku) AS id_budynkow
FROM (SELECT id_budynku, count(*) AS liczba_wind FROM serwis_windy GROUP BY id_budynku)
GROUP BY liczba_wind
ORDER BY liczba_wind
""",
    # Kontrola typ_urzadzenia przy pustym id_urzadzenia: słownik treści z wierszy, w których id_urzadzenia wskazuje
    # urządzenie. Treść „windowa” = występuje tylko przy windach, „inna” = tylko przy innych urządzeniach albo nigdy
    # z id (np. „Cieknie z sufitu”).
    "R4": """
WITH slownik AS (
    SELECT
        z.tresc_zgloszenia,
        CASE
            WHEN count(*) FILTER (w.id_windy IS NOT NULL) > 0
             AND count(*) FILTER (z.id_urzadzenia IS NOT NULL AND w.id_windy IS NULL) = 0 THEN 'windowa'
            WHEN count(*) FILTER (w.id_windy IS NOT NULL) = 0 THEN 'inna'
            ELSE 'mieszana'
        END AS rodzaj_tresci
    FROM serwis_zgloszenia AS z
    LEFT JOIN serwis_windy AS w ON w.id_windy = z.id_urzadzenia
    GROUP BY z.tresc_zgloszenia
)
SELECT
    CASE WHEN z.typ_urzadzenia = 'winda' THEN 'winda' ELSE 'inny typ' END AS typ_urzadzenia,
    count(*) AS zgl_bez_id,
    count(*) FILTER (s.rodzaj_tresci = 'windowa') AS tresc_windowa,
    count(*) FILTER (s.rodzaj_tresci = 'inna') AS tresc_inna,
    count(*) FILTER (s.rodzaj_tresci = 'mieszana') AS tresc_mieszana
FROM serwis_zgloszenia AS z
JOIN slownik AS s USING (tresc_zgloszenia)
WHERE z.id_urzadzenia IS NULL
GROUP BY ALL
ORDER BY 1 DESC
""",
    # Kategorie zgłoszeń wind
    "R5": """
WITH cz AS (
    SELECT id_zgloszenia, sum(koszt_netto) AS koszt FROM serwis_czesci GROUP BY id_zgloszenia
),
nt AS (
    SELECT id_zgloszenia, count(*) AS notatki FROM serwis_notatki GROUP BY id_zgloszenia
)
SELECT
    coalesce(z.kategoria, 'RAZEM') AS kategoria,
    count(*) AS zgloszenia,
    round(100.0 * count(*) / (SELECT count(*) FROM zgloszenia_wind), 1) AS proc,
    round(100.0 * count(*) FILTER (z.priorytet = 'pilny') / count(*), 1) AS proc_pilnych,
    round(100.0 * count(nt.id_zgloszenia) / count(*), 1) AS proc_z_notatka,
    round(100.0 * count(cz.id_zgloszenia) / count(*), 1) AS proc_z_czesciami,
    sum(cz.koszt) AS koszt_czesci_netto,
    round(median(date_diff('minute', z.utworzono, z.zamknieto)) / 60.0, 1) AS mediana_godz_do_zamkniecia
FROM zgloszenia_wind AS z
LEFT JOIN cz USING (id_zgloszenia)
LEFT JOIN nt USING (id_zgloszenia)
GROUP BY ROLLUP (z.kategoria)
ORDER BY z.kategoria IS NULL, zgloszenia DESC
""",
    # Kategoria „awaria”: wszystkie urządzenia i windy, według roku
    "R6": """
SELECT
    coalesce(CAST(year(utworzono) AS VARCHAR), 'RAZEM') AS rok,
    count(*) FILTER (kategoria = 'awaria') AS awaria_wszystkie_urzadzenia,
    count(*) FILTER (kategoria = 'awaria' AND id_zgloszenia IN (SELECT id_zgloszenia FROM zgloszenia_wind))
        AS awaria_windy,
    count(*) FILTER (kategoria = 'awaria' AND id_zgloszenia IN (
        SELECT id_zgloszenia FROM zgloszenia_wind WHERE ustalenie_windy <> 'nieustalona')) AS awaria_winda_ustalona,
    count(*) FILTER (kategoria = 'awaria' AND typ_urzadzenia = 'winda') AS awaria_typ_winda
FROM serwis_zgloszenia
GROUP BY ROLLUP (year(utworzono))
ORDER BY year(utworzono) IS NULL, year(utworzono)
""",
    # Treść zgłoszenia windy × kategoria (cyfry piętra zastąpione przez N)
    "R7": """
PIVOT (
    SELECT regexp_replace(tresc_zgloszenia, '[0-9]+', 'N', 'g') AS tresc_zgloszenia, kategoria
    FROM zgloszenia_wind
)
ON kategoria IN ('awaria', 'interwencja', 'usterka', 'inne', 'przegląd', 'konserwacja')
USING count(*)
GROUP BY tresc_zgloszenia
ORDER BY awaria DESC, interwencja DESC, tresc_zgloszenia
""",
    # Złoty zbiór koordynatora (serwis_zloty_zbior.czy_awaria) × kategoria, zgłoszenia wind
    "R8": """
SELECT
    coalesce(z.kategoria, 'RAZEM') AS kategoria,
    count(*) AS w_zlotym_zbiorze,
    count(*) FILTER (zz.czy_awaria) AS czy_awaria_tak,
    count(*) FILTER (NOT zz.czy_awaria) AS czy_awaria_nie,
    round(100.0 * count(*) FILTER (zz.czy_awaria) / count(*), 1) AS proc_awarii
FROM zgloszenia_wind AS z
JOIN serwis_zloty_zbior AS zz USING (id_zgloszenia)
GROUP BY ROLLUP (z.kategoria)
ORDER BY z.kategoria IS NULL, w_zlotym_zbiorze DESC
""",
    # Przeniesienie złotego zbioru na wszystkie zgłoszenia wind: liczba zgłoszeń kategorii × odsetek awarii w złotym
    # zbiorze tej kategorii. ZAŁOŻENIE: złoty zbiór jest losowy w obrębie kategorii (jak go wybrano — brak w danych).
    "R8b": """
WITH zz AS (
    SELECT z.kategoria, count(*) AS w_zlotym_zbiorze, avg(CAST(zz.czy_awaria AS INTEGER)) AS odsetek_awarii
    FROM zgloszenia_wind AS z
    JOIN serwis_zloty_zbior AS zz USING (id_zgloszenia)
    GROUP BY z.kategoria
),
wszystkie AS (
    SELECT kategoria, count(*) AS zgloszenia FROM zgloszenia_wind GROUP BY kategoria
),
szac AS (
    SELECT w.kategoria, w.zgloszenia, zz.w_zlotym_zbiorze, zz.odsetek_awarii, w.zgloszenia * zz.odsetek_awarii AS awarie
    FROM wszystkie AS w
    JOIN zz USING (kategoria)
)
SELECT kategoria, zgloszenia, w_zlotym_zbiorze, round(100 * odsetek_awarii, 1) AS proc_awarii_zz,
    CAST(round(awarie) AS BIGINT) AS szac_awarii, round(100 * awarie / sum(awarie) OVER (), 1) AS proc_szac_awarii
FROM szac
UNION ALL
SELECT 'RAZEM', sum(zgloszenia), sum(w_zlotym_zbiorze), NULL, CAST(round(sum(awarie)) AS BIGINT), 100.0
FROM szac
ORDER BY kategoria = 'RAZEM', szac_awarii DESC
""",
}

# Notatki do porównania: pula = notatki zgłoszeń wind z daną kategorią.
SQL_PULA_NOTATEK = """
SELECT z.kategoria, count(*) AS notatki, count(DISTINCT n.id_zgloszenia) AS zgloszenia
FROM serwis_notatki AS n
JOIN zgloszenia_wind AS z USING (id_zgloszenia)
WHERE z.kategoria IN ('awaria', 'interwencja')
GROUP BY z.kategoria
ORDER BY z.kategoria
"""

SQL_LOSOWANIE = """
SELECT
    n.id_notatki,
    n.id_zgloszenia,
    z.tresc_zgloszenia,
    n.autor,
    n.tresc AS notatka
FROM serwis_notatki AS n
JOIN zgloszenia_wind AS z USING (id_zgloszenia)
WHERE z.kategoria = ?
ORDER BY md5(n.id_notatki || ':' || ?)
LIMIT ?
"""


def _komorka(x) -> str:
    if x is None:
        return ""
    if isinstance(x, bool):
        return "tak" if x else "nie"
    if isinstance(x, int):
        return f"{x:,}".replace(",", " ")
    if isinstance(x, Decimal):  # kwoty PLN
        return f"{x:,.2f}".replace(",", " ").replace(".", ",")
    if isinstance(x, float):  # odsetki i godziny, zaokrąglone w SQL do 0,1
        return f"{x:.1f}".replace(".", ",")
    if isinstance(x, list):
        return ", ".join(_komorka(e) for e in x)
    # notatki konserwatorów bywają wielowierszowe: nowa linia psuje tabelę Markdown
    return str(x).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def tabela_md(kolumny: list[str], wiersze: list[tuple]) -> str:
    linie = ["| " + " | ".join(kolumny) + " |", "|" + "---|" * len(kolumny)]
    linie += ["| " + " | ".join(_komorka(x) for x in w) + " |" for w in wiersze]
    return "\n".join(linie)


def zapytanie_md(con: duckdb.DuckDBPyConnection, sql: str, parametry: list | None = None) -> str:
    kursor = con.execute(sql, parametry or [])
    return tabela_md([k[0] for k in kursor.description], kursor.fetchall())


def wylosuj_notatki(con: duckdb.DuckDBPyConnection, kategoria: str, n: int = LICZBA_NOTATEK) -> list[tuple]:
    """n notatek ze zgłoszeń wind danej kategorii, powtarzalnie (md5 z ZIARNO)."""
    return con.execute(SQL_LOSOWANIE, [kategoria, ZIARNO, n]).fetchall()


def notatki_obok_siebie(con: duckdb.DuckDBPyConnection) -> str:
    """Tabela R9: wiersz i = i-ta wylosowana notatka „awaria” i i-ta notatka „interwencja”."""
    awaria = wylosuj_notatki(con, "awaria")
    interwencja = wylosuj_notatki(con, "interwencja")
    kolumny = ["#", "awaria: zgłoszenie", "awaria: notatka", "interwencja: zgłoszenie", "interwencja: notatka"]
    wiersze = [
        (i, f"{a[1]} „{a[2]}” ({a[3]})", a[4], f"{b[1]} „{b[2]}” ({b[3]})", b[4])
        for i, (a, b) in enumerate(zip(awaria, interwencja, strict=True), start=1)
    ]
    return tabela_md(kolumny, wiersze)


def main(wybrane: list[str]) -> None:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    for nazwa, sql in ZAPYTANIA.items():
        if not wybrane or nazwa in wybrane:
            print(f"### {nazwa}\n\n{zapytanie_md(con, sql)}\n")
    if not wybrane or "R9" in wybrane:
        print(f"### R9 pula\n\n{zapytanie_md(con, SQL_PULA_NOTATEK)}\n")
        print(f"### R9\n\n{notatki_obok_siebie(con)}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
