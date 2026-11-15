-- Rodzina `relacja`: kontakt najemcy z Domilo przez portal przed migawką (opis: docs/przecieki_najemcy.md).
--
-- Wszystko od początku bieżącego najmu (pms_najmy.data_wprowadzenia) do dnia migawki (zdarzenie < data_migawki).
-- Zgłoszenia (portal_zgloszenia): ten sam najemca i ten sam lokal. Nie czytamy portal_zgloszenia.status (stan na
--   dzień eksportu): zgłoszenie jest otwarte na migawkę, gdy utworzono < migawka i (zamknieto IS NULL albo
--   zamknieto >= migawka).
-- Oceny obsługi: ocena_obslugi zgłoszeń zamkniętych w 365 dniach przed migawką. W danych nie ma daty
--   wystawienia oceny; przyjmujemy, że ocena powstaje przy zamknięciu zgłoszenia (ryzyko: docs/przecieki_najemcy.md).
-- Ankiety (ankiety_satysfakcji, ASOF): ostatnia odpowiedź z data_odpowiedzi < migawka, od początku najmu.
--   ankieta_brak_wyniku = 1, gdy takiej odpowiedzi nie ma (wtedy wynik i dni są NULL).
--   ankiety_bez_odpowiedzi_365d: ankiety wysłane w 365 dniach przed migawką, bez odpowiedzi przed migawką.
-- Logowania (portal_logowania_mies): agregat za CAŁY miesiąc kalendarzowy, więc bierzemy tylko pełne miesiące
--   przed migawką: [miesiąc migawki - 3 miesiące, miesiąc migawki). Miesiąc migawki zawiera też dni po migawce,
--   w tym dzień wysłania oferty przedłużenia (docs/przecieki_najemcy.md). Brak wiersza = brak danych z portalu;
--   portal_miesiace_3m mówi, ile z 3 miesięcy ma wiersz (0 = brak danych, sumy wtedy NULL).
-- Logowania są na poziomie najemcy: dla B2B to cała firma (wszystkie jej lokale).
WITH m AS (
    SELECT
        mg.id_umowy,
        mg.id_najemcy,
        mg.id_lokalu,
        mg.data_migawki,
        n.data_wprowadzenia::DATE AS data_wprowadzenia
    FROM migawki_najemcy AS mg
    JOIN pms_najmy AS n USING (id_najmu)
),
zgloszenia AS (
    SELECT
        m.id_umowy,
        count(*) FILTER (WHERE z.utworzono::DATE >= m.data_migawki - 90) AS zgl_90d,
        count(*) FILTER (WHERE z.utworzono::DATE >= m.data_migawki - 365) AS zgl_365d,
        count(*) FILTER (WHERE z.zamknieto IS NULL OR z.zamknieto::DATE >= m.data_migawki) AS zgl_otwarte_na_migawke,
        avg(z.ocena_obslugi) FILTER (
            WHERE z.zamknieto::DATE < m.data_migawki AND z.zamknieto::DATE >= m.data_migawki - 365
        ) AS ocena_srednia_365d,
        min(z.ocena_obslugi) FILTER (
            WHERE z.zamknieto::DATE < m.data_migawki AND z.zamknieto::DATE >= m.data_migawki - 365
        ) AS ocena_min_365d,
        count(z.ocena_obslugi) FILTER (
            WHERE z.zamknieto::DATE < m.data_migawki AND z.zamknieto::DATE >= m.data_migawki - 365
        ) AS ocena_liczba_365d
    FROM m
    JOIN portal_zgloszenia AS z
        ON z.id_najemcy = m.id_najemcy
       AND z.id_lokalu = m.id_lokalu
       AND z.utworzono::DATE >= m.data_wprowadzenia
       AND z.utworzono::DATE < m.data_migawki
    GROUP BY m.id_umowy
),
odpowiedzi AS (
    SELECT id_najemcy, data_odpowiedzi::DATE AS data_odpowiedzi, wynik_0_10
    FROM ankiety_satysfakcji
    WHERE data_odpowiedzi IS NOT NULL
),
ankieta_asof AS (
    SELECT
        m.id_umowy,
        CASE WHEN a.data_odpowiedzi >= m.data_wprowadzenia THEN a.wynik_0_10 END AS ankieta_ostatni_wynik,
        CASE
            WHEN a.data_odpowiedzi >= m.data_wprowadzenia THEN date_diff('day', a.data_odpowiedzi, m.data_migawki)
        END AS ankieta_dni_od_odpowiedzi
    FROM m
    ASOF LEFT JOIN odpowiedzi AS a
        ON a.id_najemcy = m.id_najemcy
       AND m.data_migawki > a.data_odpowiedzi
),
ankiety_bez_odpowiedzi AS (
    SELECT m.id_umowy, count(*) AS ankiety_bez_odpowiedzi_365d
    FROM m
    JOIN ankiety_satysfakcji AS a
        ON a.id_najemcy = m.id_najemcy
       AND a.data_wysylki::DATE >= greatest(m.data_migawki - 365, m.data_wprowadzenia)
       AND a.data_wysylki::DATE < m.data_migawki
    WHERE a.data_odpowiedzi IS NULL OR a.data_odpowiedzi::DATE >= m.data_migawki
    GROUP BY m.id_umowy
),
logowania AS (
    SELECT
        m.id_umowy,
        count(*) AS portal_miesiace_3m,
        sum(l.liczba_logowan) AS portal_logowania_3m,
        sum(l.odslony_oferty_przedluzenia) AS portal_odslony_oferty_3m
    FROM m
    JOIN portal_logowania_mies AS l
        ON l.id_najemcy = m.id_najemcy
       AND strptime(l.miesiac, '%Y-%m')::DATE >= date_trunc('month', m.data_migawki) - INTERVAL 3 MONTH
       AND strptime(l.miesiac, '%Y-%m')::DATE < date_trunc('month', m.data_migawki)
       AND strptime(l.miesiac, '%Y-%m')::DATE >= date_trunc('month', m.data_wprowadzenia)
    GROUP BY m.id_umowy
)
SELECT
    m.id_umowy,
    coalesce(z.zgl_90d, 0) AS zgl_90d,
    coalesce(z.zgl_365d, 0) AS zgl_365d,
    coalesce(z.zgl_otwarte_na_migawke, 0) AS zgl_otwarte_na_migawke,
    z.ocena_srednia_365d,
    z.ocena_min_365d,
    coalesce(z.ocena_liczba_365d, 0) AS ocena_liczba_365d,
    a.ankieta_ostatni_wynik,
    a.ankieta_dni_od_odpowiedzi,
    (a.ankieta_ostatni_wynik IS NULL)::INTEGER AS ankieta_brak_wyniku,
    coalesce(b.ankiety_bez_odpowiedzi_365d, 0) AS ankiety_bez_odpowiedzi_365d,
    coalesce(l.portal_miesiace_3m, 0) AS portal_miesiace_3m,
    l.portal_logowania_3m,
    l.portal_odslony_oferty_3m
FROM m
LEFT JOIN zgloszenia AS z USING (id_umowy)
LEFT JOIN ankieta_asof AS a USING (id_umowy)
LEFT JOIN ankiety_bez_odpowiedzi AS b USING (id_umowy)
LEFT JOIN logowania AS l USING (id_umowy)
