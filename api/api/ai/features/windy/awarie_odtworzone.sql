-- awarie_odtworzone: awarie wind odtworzone z notatek (LLM) i telemetrii (opis i liczby: docs/b4_historia_awarii.md).
--
-- Wejście:
--   awarie_llm        — odpowiedzi ekstrakcji (api.ai.llm.ekstrakcja_awarii, zbiór `windy`): id_zgloszenia,
--                       czy_awaria, podzespol, objaw, pewnosc; rejestruje je awarie_odtworzone.py;
--   zgloszenia_wind   — zgłoszenia wind z ustaloną windą (tylko id_windy IS NOT NULL: przy windzie nieustalonej
--                       nie da się sięgnąć do telemetrii);
--   serie_przestoju   — serie okien bez jazdy (serie_przestoju.sql), tabela tymczasowa;
--   serwis_notatki, telemetra_windy.
--
-- Zdarzenie: zgłoszenia z czy_awaria = true tej samej windy, w których każde kolejne powstało najpóźniej 24 h po
--   poprzednim (łańcuch), są jedną awarią. Kotwica = pierwsze zgłoszenie zdarzenia (zawsze z czy_awaria = true).
--   Do zdarzenia dołączamy też zgłoszenia tej windy bez awarii wg LLM z okna (kotwica, ostatnie zgłoszenie z awarią
--   + 24 h], poza pracami planowymi (kategoria konserwacja / przegląd). To powtórne zgłoszenia tej samej awarii
--   („Dubel zgłoszenia — połączono z wcześniejszym.”, „Zgłoszenie od lokatora, serwis już jedzie.”, bez notatek),
--   których notatki nie potwierdzają postoju. Takie zgłoszenia nie zaczynają zdarzenia i nie przedłużają łańcucha.
-- Start z telemetrii: ostatnie okno z kursami > 0 (koniec okna) przed serią co najmniej 3 martwych okien (30 min;
--   kursy = 0 albo tryb = 'wylaczona'), która zaczęła się nie później niż w oknie kotwicy i nie wcześniej niż 24 h
--   przed nią; z kilku takich serii — najpóźniejsza.
-- Czas: Serwisownik to czas lokalny Europe/Warsaw bez strefy, telemetria to UTC. Różnice liczymy na TIMESTAMPTZ
--   (CAST lokalnego TIMESTAMP przy strefie sesji Europe/Warsaw, ustawia ją polacz()), a czasy w tabeli podajemy
--   jako lokalny TIMESTAMP Europe/Warsaw (kolumny *_tz to ten sam moment z przesunięciem).
--   Godzina 2025-10-26 02:00–03:00 Serwisownika jest niejednoznaczna; DuckDB przypisuje jej jedno przesunięcie.
WITH zgl AS (
    SELECT
        zw.id_zgloszenia, zw.id_windy, zw.id_budynku, zw.utworzono,
        CAST(zw.utworzono AS TIMESTAMPTZ) AS utworzono_tz,
        a.podzespol, a.objaw, a.pewnosc
    FROM zgloszenia_wind AS zw
    JOIN awarie_llm AS a USING (id_zgloszenia)
    WHERE a.czy_awaria AND zw.id_windy IS NOT NULL
),
kolejne AS (
    SELECT
        *,
        CASE
            WHEN lag(utworzono_tz) OVER w IS NULL OR utworzono_tz - lag(utworzono_tz) OVER w > INTERVAL 24 HOUR THEN 1
            ELSE 0
        END AS nowe
    FROM zgl
    WINDOW w AS (PARTITION BY id_windy ORDER BY utworzono_tz, id_zgloszenia)
),
numerowane AS (
    SELECT *, sum(nowe) OVER (PARTITION BY id_windy ORDER BY utworzono_tz, id_zgloszenia) AS nr
    FROM kolejne
),
-- podzespół zdarzenia: najczęstszy różny od 'brak'; remis -> ten z wcześniejszego zgłoszenia; same 'brak' -> 'brak'
podzespol_zdarzenia AS (
    SELECT id_windy, nr, podzespol
    FROM (
        SELECT id_windy, nr, podzespol, count(*) AS n, min(utworzono_tz) AS pierwsze
        FROM numerowane
        WHERE podzespol <> 'brak'
        GROUP BY id_windy, nr, podzespol
    )
    QUALIFY row_number() OVER (PARTITION BY id_windy, nr ORDER BY n DESC, pierwsze, podzespol) = 1
),
zdarzenia AS (
    SELECT
        id_windy,
        nr,
        any_value(id_budynku) AS id_budynku,
        min(utworzono) AS pierwsze_zgloszenie,
        min(utworzono_tz) AS kotwica,
        max(utworzono_tz) AS ostatnie_awaria_tz,
        count(*) AS liczba_zgloszen_awaria,
        list(id_zgloszenia ORDER BY utworzono_tz, id_zgloszenia) AS id_zgloszen_awaria,
        arg_min(objaw, utworzono_tz) AS objaw,
        max(pewnosc) AS pewnosc_max
    FROM numerowane
    GROUP BY id_windy, nr
),
dolaczone AS (
    SELECT z.id_windy, z.nr, zw.id_zgloszenia, zw.utworzono, CAST(zw.utworzono AS TIMESTAMPTZ) AS utworzono_tz
    FROM zdarzenia AS z
    JOIN zgloszenia_wind AS zw
        ON zw.id_windy = z.id_windy
       AND CAST(zw.utworzono AS TIMESTAMPTZ) > z.kotwica
       AND CAST(zw.utworzono AS TIMESTAMPTZ) <= z.ostatnie_awaria_tz + INTERVAL 24 HOUR
       AND zw.kategoria NOT IN ('konserwacja', 'przegląd')
    JOIN awarie_llm AS a ON a.id_zgloszenia = zw.id_zgloszenia AND NOT a.czy_awaria
    QUALIFY row_number() OVER (PARTITION BY zw.id_zgloszenia ORDER BY z.kotwica) = 1
),
wszystkie AS (
    SELECT id_windy, nr, id_zgloszenia, utworzono, utworzono_tz FROM numerowane
    UNION ALL
    SELECT id_windy, nr, id_zgloszenia, utworzono, utworzono_tz FROM dolaczone
),
zgloszenia_zdarzenia AS (
    SELECT
        id_windy, nr,
        count(*) AS liczba_zgloszen,
        list(id_zgloszenia ORDER BY utworzono_tz, id_zgloszenia) AS id_zgloszen,
        max(utworzono) AS ostatnie_zgloszenie
    FROM wszystkie
    GROUP BY id_windy, nr
),
notatki AS (
    SELECT
        w.id_windy, w.nr,
        min(sn.data_czas) AS pierwsza_notatka,
        min(sn.data_czas) FILTER (sn.autor <> 'KOORD') AS pierwsza_notatka_konserwatora
    FROM wszystkie AS w
    JOIN serwis_notatki AS sn USING (id_zgloszenia)
    GROUP BY w.id_windy, w.nr
),
zakres_telemetrii AS (
    SELECT id_windy, min(ts_utc) AS od, max(ts_utc) AS do
    FROM telemetra_windy
    GROUP BY id_windy
),
start AS (
    SELECT
        z.id_windy, z.nr,
        arg_max(s.ostatnie_aktywne, s.pierwsze_martwe) AS start_tz,
        arg_max(s.ostatnie_martwe, s.pierwsze_martwe) AS koniec_tz,
        arg_max(s.okna, s.pierwsze_martwe) AS okna,
        arg_max(s.wylaczona, s.pierwsze_martwe) AS wylaczona
    FROM zdarzenia AS z
    JOIN serie_przestoju AS s
        ON s.id_windy = z.id_windy
       AND s.okna >= 3
       AND s.ostatnie_aktywne IS NOT NULL
       AND s.pierwsze_martwe <= z.kotwica + INTERVAL 10 MINUTE
       AND s.pierwsze_martwe >= z.kotwica - INTERVAL 24 HOUR
    GROUP BY z.id_windy, z.nr
)
SELECT
    z.id_windy || '/' || z.id_zgloszen_awaria[1] AS id_awarii,
    z.id_windy,
    z.id_budynku,
    coalesce(p.podzespol, 'brak') AS podzespol,
    z.objaw,
    z.pewnosc_max,
    zz.liczba_zgloszen,
    z.liczba_zgloszen_awaria,
    zz.id_zgloszen,
    z.id_zgloszen_awaria,
    z.pierwsze_zgloszenie,
    zz.ostatnie_zgloszenie,
    timezone('Europe/Warsaw', st.start_tz) AS start_awarii,
    st.start_tz AS start_awarii_tz,
    timezone('Europe/Warsaw', st.koniec_tz) AS koniec_przestoju,
    st.okna AS okna_przestoju,
    round(epoch(st.koniec_tz - st.start_tz) / 3600, 2) AS przestoj_h,
    st.wylaczona,
    CASE
        WHEN st.start_tz IS NOT NULL THEN 'telemetria'
        WHEN zt.od IS NULL OR z.kotwica < zt.od + INTERVAL 24 HOUR OR z.kotwica > zt.do THEN 'brak_telemetrii'
        ELSE 'brak_serii'
    END AS zrodlo_startu,
    n.pierwsza_notatka,
    n.pierwsza_notatka_konserwatora,
    round(epoch(CAST(n.pierwsza_notatka AS TIMESTAMPTZ) - st.start_tz) / 60) AS minuty_start_do_notatki,
    round(epoch(CAST(n.pierwsza_notatka_konserwatora AS TIMESTAMPTZ) - st.start_tz) / 60)
        AS minuty_start_do_notatki_konserwatora,
    round(epoch(z.kotwica - st.start_tz) / 60) AS minuty_start_do_zgloszenia,
    coalesce(timezone('Europe/Warsaw', st.start_tz), z.pierwsze_zgloszenie) AS czas_awarii
FROM zdarzenia AS z
JOIN zgloszenia_zdarzenia AS zz USING (id_windy, nr)
LEFT JOIN podzespol_zdarzenia AS p USING (id_windy, nr)
LEFT JOIN notatki AS n USING (id_windy, nr)
LEFT JOIN start AS st USING (id_windy, nr)
LEFT JOIN zakres_telemetrii AS zt USING (id_windy)
ORDER BY czas_awarii, id_awarii
