-- Podział czasowy transakcji RCN dla modelu wyceny lokali (opis i liczności: docs/b1_dane.md).
--
-- Jednostka: jedna transakcja z rejestru cen (rcn_transakcje, klucz id_transakcji).
-- Target: cena transakcyjna (cena_pln, cena_m2), nie cena ofertowa.
-- O przydziale do zbioru decyduje data_aktu (dzień aktu notarialnego):
--   trening   2023-01-01 – 2025-06-30
--   walidacja 2025-07-01 – 2025-12-31
--   test      2026-01-01 – 2026-06-30
-- Pomijamy transakcje opublikowane w rejestrze po dniu eksportu (data_publikacji_rejestru > 2026-09-30):
-- w dniu eksportu 2026-09-30 nie były jeszcze znane (dotyczy tylko aktów z czerwca 2026).
-- Granice są półotwarte ([od, do)), więc data_aktu z godziną też trafi do właściwego zbioru.
-- Zapytanie działa na domilo.duckdb (tabela rcn_transakcje, połączenie przez polacz()).
SELECT
    t.id_transakcji,
    t.data_aktu,
    t.data_publikacji_rejestru,
    CASE
        WHEN t.data_aktu >= TIMESTAMP '2023-01-01' AND t.data_aktu < TIMESTAMP '2025-07-01' THEN 'trening'
        WHEN t.data_aktu >= TIMESTAMP '2025-07-01' AND t.data_aktu < TIMESTAMP '2026-01-01' THEN 'walidacja'
        WHEN t.data_aktu >= TIMESTAMP '2026-01-01' AND t.data_aktu < TIMESTAMP '2026-07-01' THEN 'test'
    END AS zbior
FROM rcn_transakcje AS t
WHERE t.data_aktu >= TIMESTAMP '2023-01-01'
  AND t.data_aktu < TIMESTAMP '2026-07-01'
  AND t.data_publikacji_rejestru < TIMESTAMP '2026-10-01'
