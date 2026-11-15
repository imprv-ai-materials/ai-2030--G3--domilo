-- obsluzony: czy doradca (D01–D15) lub call center (CC) wykonał przy zapytaniu co najmniej jedną aktywność
-- w ciągu 45 dni od utworzenia, bez wyniku 'podpisanie' (nieodebrany telefon też się liczy).
-- Definicja jest w leady_cel.sql (docs/kolejka_target.md). Dla zapytań cenzurowanych okno 45 dni jeszcze trwało
-- w dniu eksportu, więc obsluzony = false może się jeszcze zmienić: do metryk bierz `not cenzurowany`.
select
    id_leada,
    utworzono,
    cast(utworzono as date) as data_utworzenia,
    zrodlo,
    okno_migracji,
    cenzurowany,
    obsluzony,
    obsluzony_cc,
    liczba_kontaktow_45d,
    pierwszy_kontakt,
    godz_do_pierwszego_kontaktu
from {{ source('domilo', 'leady_cel') }}
