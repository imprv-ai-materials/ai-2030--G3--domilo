"""Historia awarii wind w Serwisowniku: tabele do docs/b4_historia_awarii.md.

Czyta domilo.duckdb (tabele serwis_* z `api.adapters.serwisownik`, tabela pochodna `zgloszenia_wind`).
Uruchomienie (z katalogu api/): `python -m api.ai.failure_model.evals.historia_awarii [R1 R2 ...]`
— wypisuje tabele Markdown (wszystkie albo wybrane).

Losowanie notatek (R9) jest powtarzalne: kolejność według md5(id_notatki || ':' || ZIARNO), pierwsze 30.

R10–R14 (awarie odtworzone) czytają dodatkowo tabelę `awarie_odtworzone`, odpowiedzi ekstrakcji LLM
(`features/windy/awarie_llm/awaria_v1_windy.parquet`, rejestrowane jako `awarie_llm`) i tymczasową tabelę
`serie_przestoju` (`api.ai.features.windy.awarie_odtworzone`).
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
ORDER BY z.kategoria IS NULL, w_zlotym_zbiorze DESC, z.kategoria
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
ORDER BY kategoria = 'RAZEM', szac_awarii DESC, kategoria
""",
}

PODZESPOLY = "'drzwi', 'naped', 'hamulec_liny', 'sterownik', 'zewnetrzna', 'brak'"

ZAPYTANIA_AWARIE: dict[str, str] = {
    # Ekstrakcja LLM na wszystkich zgłoszeniach wind
    "R10": """
SELECT
    count(*) AS zgloszenia_wind,
    count(a.id_zgloszenia) AS z_odpowiedzia_llm,
    count(*) FILTER (a.czy_awaria) AS awaria_llm,
    count(*) FILTER (a.czy_awaria AND zw.id_windy IS NOT NULL) AS awaria_llm_winda_ustalona,
    count(*) FILTER (a.czy_awaria AND zw.id_windy IS NULL) AS awaria_llm_winda_nieustalona,
    count(*) FILTER (zw.kategoria = 'awaria') AS kategoria_awaria,
    count(*) FILTER (zw.kategoria = 'awaria' AND a.czy_awaria) AS kategoria_awaria_i_llm
FROM zgloszenia_wind AS zw
LEFT JOIN awarie_llm AS a USING (id_zgloszenia)
""",
    # Odpowiedź LLM według kategorii Serwisownika (wszystkie zgłoszenia wind)
    "R10b": """
SELECT
    coalesce(zw.kategoria, 'RAZEM') AS kategoria,
    count(*) AS zgloszenia,
    count(*) FILTER (a.czy_awaria) AS awaria_llm,
    round(100.0 * count(*) FILTER (a.czy_awaria) / count(*), 1) AS proc_awarii_llm
FROM zgloszenia_wind AS zw
JOIN awarie_llm AS a USING (id_zgloszenia)
GROUP BY ROLLUP (zw.kategoria)
ORDER BY zw.kategoria IS NULL, zgloszenia DESC
""",
    # Zdarzenia: łączenie zgłoszeń w awarie
    "R11": """
WITH odstepy AS (
    SELECT epoch(CAST(pierwsze_zgloszenie AS TIMESTAMPTZ) - CAST(lag(ostatnie_zgloszenie) OVER (
               PARTITION BY id_windy ORDER BY pierwsze_zgloszenie) AS TIMESTAMPTZ)) / 3600 AS h
    FROM awarie_odtworzone
)
SELECT
    count(*) AS awarie,
    count(DISTINCT id_windy) AS windy,
    sum(liczba_zgloszen_awaria) AS zgl_z_awaria,
    sum(liczba_zgloszen) - sum(liczba_zgloszen_awaria) AS zgl_dolaczone_bez_awarii,
    count(*) FILTER (liczba_zgloszen_awaria >= 2) AS awarie_z_2_i_wiecej_zgl_z_awaria,
    count(*) FILTER (liczba_zgloszen >= 2) AS awarie_z_2_i_wiecej_zgl,
    max(liczba_zgloszen) AS max_zgl,
    (SELECT round(min(h), 1) FROM odstepy) AS min_odstep_miedzy_awariami_windy_h,
    (SELECT count(*) FILTER (h <= 7 * 24) FROM odstepy) AS kolejna_awaria_windy_do_7_dni
FROM awarie_odtworzone
""",
    # Dołączone zgłoszenia bez awarii: treść zgłoszenia i pierwsza notatka (cyfry -> N)
    "R11c": """
WITH d AS (
    SELECT u.id_zgloszenia
    FROM awarie_odtworzone AS a, unnest(a.id_zgloszen) AS u(id_zgloszenia)
    WHERE NOT list_contains(a.id_zgloszen_awaria, u.id_zgloszenia)
),
n AS (
    SELECT id_zgloszenia, arg_min(tresc, data_czas) AS tresc FROM serwis_notatki GROUP BY id_zgloszenia
)
SELECT
    coalesce(regexp_replace(regexp_replace(n.tresc, '\\s+', ' ', 'g'), '[0-9]+', 'N', 'g'), '(brak notatek)')
        AS pierwsza_notatka,
    count(*) AS zgloszenia
FROM d
LEFT JOIN n USING (id_zgloszenia)
GROUP BY 1
ORDER BY zgloszenia DESC, pierwsza_notatka
LIMIT 10
""",
    # Skąd start awarii
    "R11b": """
SELECT
    coalesce(zrodlo_startu, 'RAZEM') AS zrodlo_startu,
    count(*) AS awarie,
    round(100.0 * count(*) / sum(count(*)) FILTER (zrodlo_startu IS NOT NULL) OVER (), 1) AS proc,
    count(*) FILTER (wylaczona) AS z_trybem_wylaczona,
    median(okna_przestoju) AS mediana_okien_przestoju,
    median(przestoj_h) AS mediana_przestoju_h,
    median(minuty_start_do_zgloszenia) AS mediana_min_start_do_zgloszenia
FROM awarie_odtworzone
GROUP BY ROLLUP (zrodlo_startu)
ORDER BY zrodlo_startu IS NULL, awarie DESC
""",
    # Walidacja startu: awarie zawierające zgłoszenie złotego zbioru z czy_awaria = true
    "R12": """
WITH z AS (
    SELECT a.id_awarii, a.start_awarii, a.zrodlo_startu, zz.id_zgloszenia, zz.start_awarii AS start_koordynatora
    FROM awarie_odtworzone AS a, unnest(a.id_zgloszen) AS u(id_zgloszenia)
    JOIN serwis_zloty_zbior AS zz USING (id_zgloszenia)
    WHERE zz.czy_awaria
)
SELECT
    (SELECT count(*) FROM serwis_zloty_zbior WHERE czy_awaria) AS awarie_zz,
    count(*) AS w_awariach_odtworzonych,
    count(start_awarii) AS ze_startem_z_telemetrii,
    count(*) FILTER (start_awarii = start_koordynatora) AS start_ten_sam,
    count(*) FILTER (abs(date_diff('minute', start_koordynatora, start_awarii)) <= 30) AS start_do_30_min,
    median(date_diff('minute', start_koordynatora, start_awarii)) AS mediana_roznicy_min,
    quantile_cont(abs(date_diff('minute', start_koordynatora, start_awarii)), 0.9) AS p90_abs_roznicy_min,
    max(abs(date_diff('minute', start_koordynatora, start_awarii))) AS max_abs_roznicy_min
FROM z
""",
    # Start z telemetrii -> pierwsza notatka / pierwsza notatka konserwatora / pierwsze zgłoszenie (minuty)
    "R13": """
SELECT miara, count(m) AS awarie, median(m) AS mediana_min, quantile_cont(m, 0.25) AS p25_min,
       quantile_cont(m, 0.75) AS p75_min, quantile_cont(m, 0.9) AS p90_min, count(*) FILTER (m < 0) AS ujemne
FROM (
    SELECT 'start -> pierwsza notatka' AS miara, minuty_start_do_notatki AS m, 1 AS k FROM awarie_odtworzone
    UNION ALL
    SELECT 'start -> pierwsza notatka konserwatora', minuty_start_do_notatki_konserwatora, 2 FROM awarie_odtworzone
    UNION ALL
    SELECT 'start -> pierwsze zgłoszenie', minuty_start_do_zgloszenia, 3 FROM awarie_odtworzone
)
WHERE m IS NOT NULL
GROUP BY miara, k
ORDER BY k
""",
    # Awarie miesięcznie według podzespołu (miesiąc startu z telemetrii, bez niego — pierwszego zgłoszenia)
    "R14": f"""
WITH a AS (SELECT strftime(czas_awarii, '%Y-%m') AS miesiac, podzespol FROM awarie_odtworzone),
p AS (PIVOT a ON podzespol IN ({PODZESPOLY}) USING count(*) GROUP BY miesiac),
k AS (
    SELECT strftime(utworzono, '%Y-%m') AS miesiac, count(*) AS zgl_kategoria_awaria
    FROM zgloszenia_wind
    WHERE kategoria = 'awaria' AND id_windy IS NOT NULL
    GROUP BY 1
)
SELECT
    coalesce(p.miesiac, k.miesiac) AS miesiac,
    coalesce(p.drzwi, 0) AS drzwi, coalesce(p.naped, 0) AS naped, coalesce(p.hamulec_liny, 0) AS hamulec_liny,
    coalesce(p.sterownik, 0) AS sterownik, coalesce(p.zewnetrzna, 0) AS zewnetrzna, coalesce(p.brak, 0) AS brak,
    coalesce(p.drzwi + p.naped + p.hamulec_liny + p.sterownik + p.zewnetrzna + p.brak, 0) AS razem,
    coalesce(k.zgl_kategoria_awaria, 0) AS zgl_kategoria_awaria
FROM p
FULL JOIN k USING (miesiac)
ORDER BY miesiac
""",
    # Według roku (rok 2026: styczeń–wrzesień)
    "R14b": """
SELECT
    coalesce(CAST(year(czas_awarii) AS VARCHAR), 'RAZEM') AS rok,
    count(*) FILTER (podzespol = 'drzwi') AS drzwi,
    count(*) FILTER (podzespol = 'naped') AS naped,
    count(*) FILTER (podzespol = 'hamulec_liny') AS hamulec_liny,
    count(*) FILTER (podzespol = 'sterownik') AS sterownik,
    count(*) FILTER (podzespol = 'zewnetrzna') AS zewnetrzna,
    count(*) FILTER (podzespol = 'brak') AS brak,
    count(*) AS razem
FROM awarie_odtworzone
GROUP BY ROLLUP (year(czas_awarii))
ORDER BY year(czas_awarii) IS NULL, year(czas_awarii)
""",
}

# Warianty reguły startu sprawdzane na złotym zbiorze (R12b). Kotwica = utworzenie zgłoszenia złotego zbioru.
# W awarie_odtworzone.sql jest wariant B (seria >= 3 okna, nie wcześniej niż 24 h przed kotwicą).
WARIANTY_STARTU: dict[str, str] = {
    "A: dowolna seria (≥ 1 okno), do 24 h przed": "s.pierwsze_martwe >= g.kotwica - INTERVAL 24 HOUR",
    "B: seria ≥ 3 okna (30 min), do 24 h przed [wybrany]": (
        "s.pierwsze_martwe >= g.kotwica - INTERVAL 24 HOUR AND s.okna >= 3"
    ),
    "C: seria ≥ 6 okien (1 h), do 24 h przed": "s.pierwsze_martwe >= g.kotwica - INTERVAL 24 HOUR AND s.okna >= 6",
    "D: seria trwająca w chwili zgłoszenia": "s.ostatnie_martwe >= g.kotwica",
}

SQL_WARIANT_STARTU = """
WITH g AS (
    SELECT zz.id_zgloszenia, zw.id_windy, CAST(zw.utworzono AS TIMESTAMPTZ) AS kotwica, zz.start_awarii
    FROM serwis_zloty_zbior AS zz
    JOIN zgloszenia_wind AS zw USING (id_zgloszenia)
    WHERE zz.czy_awaria
),
k AS (
    SELECT g.id_zgloszenia, g.start_awarii,
           timezone('Europe/Warsaw', arg_max(s.ostatnie_aktywne, s.pierwsze_martwe)) AS start_tel
    FROM g
    LEFT JOIN serie_przestoju AS s
        ON s.id_windy = g.id_windy AND s.ostatnie_aktywne IS NOT NULL
       AND s.pierwsze_martwe <= g.kotwica + INTERVAL 10 MINUTE AND {warunek}
    GROUP BY g.id_zgloszenia, g.start_awarii
)
SELECT
    ? AS wariant,
    count(*) AS awarie_zz,
    count(start_tel) AS ze_startem,
    count(*) FILTER (start_tel = start_awarii) AS start_ten_sam,
    count(*) FILTER (abs(date_diff('minute', start_awarii, start_tel)) <= 30) AS start_do_30_min,
    median(date_diff('minute', start_awarii, start_tel)) AS mediana_roznicy_min,
    quantile_cont(abs(date_diff('minute', start_awarii, start_tel)), 0.9) AS p90_abs_roznicy_min
FROM k
"""

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


def warianty_startu_md(con: duckdb.DuckDBPyConnection) -> str:
    """R12b: warianty reguły startu wobec start_awarii koordynatora (wymaga tabeli serie_przestoju)."""
    kolumny, wiersze = None, []
    for nazwa, warunek in WARIANTY_STARTU.items():
        kursor = con.execute(SQL_WARIANT_STARTU.format(warunek=warunek), [nazwa])
        kolumny = [k[0] for k in kursor.description]
        wiersze += kursor.fetchall()
    return tabela_md(kolumny, wiersze)


def przygotuj_awarie(con: duckdb.DuckDBPyConnection) -> None:
    """Rejestruje odpowiedzi LLM jako `awarie_llm` i tworzy tymczasową `serie_przestoju` (R10–R14)."""
    from api.ai.features.windy.awarie_odtworzone import utworz_serie_przestoju, wczytaj_llm

    con.register("awarie_llm", wczytaj_llm())
    utworz_serie_przestoju(con)


def main(wybrane: list[str]) -> None:
    from api.adapters.duckdb_baza import polacz

    con = polacz()
    for nazwa, sql in ZAPYTANIA.items():
        if not wybrane or nazwa in wybrane:
            print(f"### {nazwa}\n\n{zapytanie_md(con, sql)}\n")
    if not wybrane or "R9" in wybrane:
        print(f"### R9 pula\n\n{zapytanie_md(con, SQL_PULA_NOTATEK)}\n")
        print(f"### R9\n\n{notatki_obok_siebie(con)}\n")
    awarie = [n for n in ZAPYTANIA_AWARIE if not wybrane or n in wybrane]
    if awarie:
        przygotuj_awarie(con)
    for nazwa in awarie:
        print(f"### {nazwa}\n\n{zapytanie_md(con, ZAPYTANIA_AWARIE[nazwa])}\n")
        if nazwa == "R12":
            print(f"### R12b\n\n{warianty_startu_md(con)}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
