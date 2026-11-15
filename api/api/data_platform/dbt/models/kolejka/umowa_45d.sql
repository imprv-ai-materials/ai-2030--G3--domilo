-- umowa_45d: czy zapytanie skończyło się umową w ciągu 45 dni od utworzenia (1 / 0; NULL = cenzurowane).
-- Jedno zapytanie z crm_leady na wiersz. Definicja jest w leady_cel.sql (docs/kolejka_target.md); ten model
-- jej nie powtarza, tylko wystawia, żeby raport i eksperyment czytały to samo.
select
    id_leada,
    utworzono,
    cast(utworzono as date) as data_utworzenia,  -- dzień w czasie warszawskim (TimeZone w profilu)
    zrodlo,
    okno_migracji,
    cenzurowany,
    umowa_45d,
    id_umowy,
    data_umowy,
    dni_do_umowy
from {{ source('domilo', 'leady_cel') }}
