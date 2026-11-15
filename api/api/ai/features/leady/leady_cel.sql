-- Target modelu kolejki zapytań: czy zapytanie (lead) skończy się umową w ciągu 45 dni (opis: docs/kolejka_target.md).
--
-- Jednostka: jedno zapytanie z crm_leady (klucz id_leada).
-- Umowa: pierwsze przejście na status 'umowa' w crm_historia_statusow albo umowa w pms_umowy przez
--   crm_leady.id_umowy (data_podpisania, początek dnia czasu warszawskiego). Obie ścieżki zgadzają się co do dnia
--   dla wszystkich umów w danych; zrodlo_umowy pokazuje, które źródło ją potwierdza.
-- umowa_45d = 1, gdy data_umowy <= utworzono + 45 dni; 0, gdy nie; NULL, gdy zapytanie jest cenzurowane, czyli
--   w dniu eksportu było młodsze niż 45 dni (utworzono + 45 dni > koniec eksportu). Cenzurowane mają NULL także
--   wtedy, gdy umowa już jest: inaczej młode zapytania miałyby tylko wczesne umowy, a nigdy późnych.
-- crm_leady.status to stan na dzień eksportu: nie używamy go. Status końcowy liczymy z crm_historia_statusow:
--   ostatnia zmiana statusu, przy czym okres 'w_toku' dłuższy niż 90 dni (do następnej zmiany albo do końca
--   eksportu) liczymy jako utratę w dniu wejścia w 'w_toku' + 90 dni (utracony_90d).
--   zamkniety = status końcowy 'umowa' albo 'utracony'.
-- obsluzony: co najmniej jedna aktywność doradcy lub call center (crm_aktywnosci, id_doradcy D.. albo CC)
--   w ciągu 45 dni od utworzenia, bez wyniku 'podpisanie' (to zapis samej umowy, nie kontakt z klientem).
-- okno_migracji: zapytanie utworzone 2025-03-03 – 2025-04-13 (czas warszawski), czyli start nowego CRM, gdy
--   zapytania obsługiwało zewnętrzne call center (crm_doradcy.id_doradcy = 'CC').
-- Koniec eksportu: 2026-09-30 23:59 Europe/Warsaw, tu jako granica półotwarta 2026-10-01 00:00 (+02:00).
-- Zapytanie działa na domilo.duckdb przez polacz() (strefa sesji Europe/Warsaw: dodawanie dni i rzutowanie
-- data_podpisania na TIMESTAMPTZ liczą się w czasie warszawskim).
WITH parametry AS (
    SELECT
        TIMESTAMPTZ '2026-10-01 00:00:00+02' AS koniec_eksportu,
        TIMESTAMPTZ '2025-03-03 00:00:00+01' AS okno_od,
        TIMESTAMPTZ '2025-04-14 00:00:00+02' AS okno_do
),
-- Przy remisie czasu (w danych 2 leady: w_toku i umowa w tej samej sekundzie) kolejność ustala etap statusu.
historia AS (
    SELECT
        id_leada,
        data_czas,
        status_na,
        lead(data_czas) OVER kolejnosc AS data_nastepnej,
        row_number() OVER kolejnosc AS nr,
        count(*) OVER (PARTITION BY id_leada) AS liczba_zmian
    FROM crm_historia_statusow
    WINDOW kolejnosc AS (
        PARTITION BY id_leada
        ORDER BY data_czas, CASE status_na WHEN 'otwarty' THEN 0 WHEN 'w_toku' THEN 1 ELSE 2 END, status_na
    )
),
ostatni_status AS (
    SELECT id_leada, status_na AS status_na_eksport, data_czas AS data_ostatniej
    FROM historia
    WHERE nr = liczba_zmian
),
umowa_crm AS (
    SELECT id_leada, min(data_czas) AS data_umowy_crm
    FROM crm_historia_statusow
    WHERE status_na = 'umowa'
    GROUP BY id_leada
),
w_toku_ponad_90d AS (
    SELECT h.id_leada, min(h.data_czas + INTERVAL 90 DAY) AS data_utraty_90d
    FROM historia AS h, parametry AS p
    WHERE h.status_na = 'w_toku'
      AND coalesce(h.data_nastepnej, p.koniec_eksportu) > h.data_czas + INTERVAL 90 DAY
    GROUP BY h.id_leada
),
kontakty AS (
    SELECT
        a.id_leada,
        count(*) AS liczba_kontaktow_45d,
        bool_or(a.id_doradcy = 'CC') AS obsluzony_cc,
        min(a.data_czas) AS pierwszy_kontakt
    FROM crm_aktywnosci AS a
    JOIN crm_leady AS l USING (id_leada)
    WHERE a.id_doradcy IS NOT NULL
      AND a.wynik IS DISTINCT FROM 'podpisanie'
      AND a.data_czas >= l.utworzono
      AND a.data_czas <= l.utworzono + INTERVAL 45 DAY
    GROUP BY a.id_leada
),
zlaczone AS (
    SELECT
        l.id_leada,
        l.utworzono,
        l.zrodlo,
        l.utworzono >= p.okno_od AND l.utworzono < p.okno_do AS okno_migracji,
        l.utworzono + INTERVAL 45 DAY > p.koniec_eksportu AS cenzurowany,
        u.id_umowy,
        coalesce(c.data_umowy_crm, CAST(u.data_podpisania AS TIMESTAMPTZ)) AS data_umowy,
        CASE
            WHEN c.data_umowy_crm IS NOT NULL AND u.id_umowy IS NOT NULL THEN 'crm+pms'
            WHEN c.data_umowy_crm IS NOT NULL THEN 'crm'
            WHEN u.id_umowy IS NOT NULL THEN 'pms'
        END AS zrodlo_umowy,
        s.status_na_eksport,
        s.data_ostatniej,
        w.data_utraty_90d,
        k.liczba_kontaktow_45d,
        k.obsluzony_cc,
        k.pierwszy_kontakt
    FROM crm_leady AS l
    CROSS JOIN parametry AS p
    LEFT JOIN umowa_crm AS c USING (id_leada)
    LEFT JOIN pms_umowy AS u ON u.id_umowy = l.id_umowy
    LEFT JOIN ostatni_status AS s USING (id_leada)
    LEFT JOIN w_toku_ponad_90d AS w USING (id_leada)
    LEFT JOIN kontakty AS k USING (id_leada)
),
ze_statusem AS (
    SELECT
        *,
        data_utraty_90d IS NOT NULL AND (data_umowy IS NULL OR data_umowy > data_utraty_90d) AS utracony_90d
    FROM zlaczone
)
SELECT
    id_leada,
    utworzono,
    zrodlo,
    okno_migracji,
    cenzurowany,
    CASE
        WHEN cenzurowany THEN NULL
        WHEN data_umowy <= utworzono + INTERVAL 45 DAY THEN 1
        ELSE 0
    END::INTEGER AS umowa_45d,
    id_umowy,
    data_umowy,
    zrodlo_umowy,
    epoch(data_umowy - utworzono) / 86400.0 AS dni_do_umowy,
    CASE
        WHEN utracony_90d THEN 'utracony'
        WHEN data_umowy IS NOT NULL THEN 'umowa'
        ELSE status_na_eksport
    END AS status_koncowy,
    utracony_90d,
    utracony_90d OR data_umowy IS NOT NULL OR status_na_eksport = 'utracony' AS zamkniety,
    CASE
        WHEN utracony_90d THEN data_utraty_90d
        WHEN data_umowy IS NOT NULL THEN data_umowy
        WHEN status_na_eksport = 'utracony' THEN data_ostatniej
    END AS data_zamkniecia,
    coalesce(liczba_kontaktow_45d, 0) > 0 AS obsluzony,
    coalesce(obsluzony_cc, FALSE) AS obsluzony_cc,
    coalesce(liczba_kontaktow_45d, 0) AS liczba_kontaktow_45d,
    pierwszy_kontakt,
    epoch(pierwszy_kontakt - utworzono) / 3600.0 AS godz_do_pierwszego_kontaktu
FROM ze_statusem
