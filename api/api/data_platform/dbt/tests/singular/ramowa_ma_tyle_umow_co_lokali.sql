-- Umowa ramowa ma w pms_umowy po jednym wierszu na lokal, więc liczba umów = liczba_lokali.
-- Na tym opiera się wartosc_umowy (suma po lokalach zamiast wzoru na każdym wierszu).
select id_podpisania, liczba_umow, liczba_lokali
from {{ ref('wartosc_umowy') }}
where liczba_umow <> liczba_lokali
