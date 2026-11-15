-- Rodzina `tekst`: długość wiadomości i sygnały z oceny LLM v1 (prompt ocena_leada_v1).
-- sygnaly_v1: relacja (id_leada, sygnaly) rejestrowana przez cechy.py z ai/llm/cache (sygnaly_v1.wczytaj_sygnaly):
--   tekst „a,b” z zamkniętego słownika, '' = odpowiedź bez sygnałów, NULL = brak odpowiedzi v1.
-- syg_*: 1/0, NULL gdy brak odpowiedzi v1 (LightGBM traktuje to jako brak, a nie „brak sygnału”).
-- dlugosc_wiadomosci: liczba znaków, 0 gdy wiadomości nie ma.
WITH s AS (
    SELECT id_leada, string_split(sygnaly, ',') AS lista
    FROM sygnaly_v1
)
SELECT
    l.id_leada,
    coalesce(length(l.wiadomosc), 0) AS dlugosc_wiadomosci,
    CAST(list_contains(s.lista, 'konkretne_pytania') AS INTEGER) AS syg_konkretne_pytania,
    CAST(list_contains(s.lista, 'niedopasowanie_oferty') AS INTEGER) AS syg_niedopasowanie_oferty,
    CAST(list_contains(s.lista, 'pilny_termin') AS INTEGER) AS syg_pilny_termin,
    CAST(list_contains(s.lista, 'relokacja') AS INTEGER) AS syg_relokacja,
    CAST(list_contains(s.lista, 'budzet_niski') AS INTEGER) AS syg_budzet_niski,
    CAST(list_contains(s.lista, 'brak_informacji') AS INTEGER) AS syg_brak_informacji
FROM crm_leady AS l
LEFT JOIN s USING (id_leada)
