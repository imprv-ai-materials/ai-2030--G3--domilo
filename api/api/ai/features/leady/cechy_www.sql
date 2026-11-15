-- Rodzina `www`: sesje na stronie powiązane z zapytaniem (www_sesje.id_leada), tylko rozpoczęte PRZED utworzeniem
-- zapytania. W danych 202 182 z 486 260 powiązanych sesji jest po utworzeniu (docs/kolejka_v2_lgbm_naiwny.md, C1);
-- byłyby przeciekiem przyszłości (klient wraca na stronę, bo już rozmawia z doradcą).
-- Brak sesji = 0 sesji, 0 dla flag.
SELECT
    l.id_leada,
    count(s.id_sesji) AS www_liczba_sesji,
    CAST(coalesce(bool_or(s.czy_spacer_3d), FALSE) AS INTEGER) AS www_spacer_3d,
    CAST(coalesce(bool_or(s.czy_kalkulator), FALSE) AS INTEGER) AS www_kalkulator
FROM crm_leady AS l
LEFT JOIN www_sesje AS s
    ON s.id_leada = l.id_leada
   AND s.data_czas < l.utworzono
GROUP BY l.id_leada
