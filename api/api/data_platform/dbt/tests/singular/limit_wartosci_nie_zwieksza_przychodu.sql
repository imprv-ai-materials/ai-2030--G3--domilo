-- Ograniczenie wartości jednej umowy może tylko obniżyć sumę; umów nie więcej niż pierwszych kontaktów.
select tydzien, wartosc_umow, wartosc_umow_bez_limitu, umowy, pierwsze_kontakty
from {{ ref('przychod_z_kontaktow') }}
where wartosc_umow > wartosc_umow_bez_limitu + 0.01 or umowy > pierwsze_kontakty
