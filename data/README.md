# Domilo S.A. — dane

Syntetyczne dane operatora najmu instytucjonalnego Domilo S.A. (7 200 mieszkań, 38 budynków, 6 miast, 140 wind)
do kursu „Zostań praktykiem modeli predykcyjnych”. Wszystkie firmy, osoby i adresy są fikcyjne.

- **Okres danych zdarzeniowych:** 2023-01-01 – 2026-09-30, **dzień eksportu 2026-09-30** (23:59 Europe/Warsaw).
- Wyjątki: historia najmów i umów w PMS od 2019-04 (rekordy sprzed 2023-03-01 to import — m.in. puste `data_podpisania`,
  puste `zrodlo` najemcy); rejestr transakcji `rcn_transakcje` do 2026-06-30 (publikacja z opóźnieniem 60–120 dni);
  CRM od 2023-01-01 (rekordy sprzed 2025-03-03 to migracja z poprzedniego CRM).
- Katalog jest **tylko do odczytu**: wyniki pośrednie, bazy i raporty zapisujemy poza `data/`.

## Pliki

| Katalog | Plik | 1 wiersz = |
|---|---|---|
| `pms/` | `pms_budynki.parquet` | budynek |
| | `pms_lokale.parquet` | lokal (status i czynsz katalogowy — stan na dzień eksportu) |
| | `pms_najemcy.parquet` | najemca |
| | `pms_najmy.parquet` | ciągły najem lokalu przez najemcę (puste `data_wyprowadzenia` = aktywny) |
| | `pms_umowy.parquet` | okres umowy (pierwsza / przedłużenie / średnioterminowa) |
| | `pms_platnosci.parquet` | umowa × miesiąc (od 2023-01) |
| | `pms_rekompensaty.parquet` | obniżka czynszu / rekompensata |
| `crm/` | `crm_leady.parquet` | zapytanie (lead) — `status` to stan na dzień eksportu |
| | `crm_historia_statusow.parquet` | zmiana statusu leada |
| | `crm_aktywnosci.parquet` | telefon / e-mail / SMS / prezentacja |
| | `crm_doradcy.parquet`, `crm_grafik.parquet` | doradca; doradca × dzień pracy |
| | `crm_firmy_b2b.parquet` | firma-klient B2B |
| | `www_sesje.parquet` | sesja na stronie www |
| `portal/` | `portal_zgloszenia.parquet`, `portal_wiadomosci.parquet` | zgłoszenie najemcy; wiadomość |
| | `portal_logowania_mies.parquet` | najemca × miesiąc kalendarzowy (agregat za **cały** miesiąc) |
| | `ankiety_satysfakcji.parquet` | wysyłka ankiety (puste `wynik_0_10` = brak odpowiedzi) |
| | `retencja_decyzje.parquet` | kończąca się umowa roczna od 2024-02 (score dostawcy, grupa oferty) |
| `serwis/` | `serwis_windy.parquet` | winda |
| | `serwis_zgloszenia.parquet`, `serwis_notatki.parquet` | zgłoszenie techniczne; notatka konserwatora |
| | `serwis_czesci.parquet`, `serwis_harmonogram.parquet` | wymieniona część; konserwacja / przegląd planowy |
| | `serwis_zloty_zbior.parquet` | zgłoszenie oznaczone ręcznie przez koordynatora (400) |
| `telemetra/` | `telemetra_windy/rok=YYYY/miesiac=MM/*.parquet` | winda × 10 minut (`ts_utc` = koniec okna) |
| | `telemetra_cieplo/rok=YYYY/miesiac=MM/*.parquet` | urządzenie ciepła × 15 minut |
| | `telemetra_urzadzenia_ciepla.parquet`, `telemetra_firmware.parquet` | węzeł / pompa ciepła; zmiana firmware |
| `radar/` | `radar_oferty.parquet` | ogłoszenie na jednym portalu |
| | `radar_pakiety.parquet`, `radar_dopasowania.parquet` | pakiet dewelopera; para oferta ↔ transakcja |
| | `rcn_transakcje.parquet` | transakcja z rejestru cen |
| | `operaty.parquet` | operat szacunkowy (roczny / kontrolny / due diligence) |
| | `lokale_domilo_opisy.parquet` | opis marketingowy lokalu Domilo |
| | `zdjecia/oferty/<id_oferty>/1–4.jpg`, `zdjecia/domilo/<id_lokalu>/1–4.jpg`, `zdjecia/metadane.parquet` | zdjęcie (JPEG 768 × 576) |
| `zewnetrzne/` | `geo_poi.parquet`, `gus_dzielnice.parquet` | punkt zainteresowania; dzielnica |
| `fk/` | `fk_koszty_serwisu.parquet`, `fk_rabaty.parquet`, `fk_koszty_rotacji.parquet` | pozycja kosztowa; umowa × miesiąc z rabatem; budynek × miesiąc |

## Konwencje systemów

- **Wszystkie tabele są w formacie Parquet** (zstd, typy kolumn zapisane w pliku, braki jako null). DuckDB czyta je
  bezpośrednio (`SELECT * FROM 'data/crm/crm_leady.parquet'`), pandas przez `read_parquet`. Systemy zapisują czas
  po swojemu:
  - **CRM** zapisuje czas jako tekst ISO 8601 z przesunięciem (`2026-03-14T09:12:00+01:00`) — kolumny `utworzono`,
    `data_statusu`, `data_czas` w `crm_*` i `www_sesje` są napisami;
  - **Serwisownik** zapisuje czas lokalny bez strefy (typ timestamp bez strefy, dokładność do minuty) — przy zmianie
    czasu 2025-10-26 godzina 02:00–03:00 występuje dwa razy; `serwis_czesci.koszt_netto` to tekst z eksportu
    z przecinkiem dziesiętnym (`1 234,50`).
- **Telemetra**: Parquet partycjonowany `rok=/miesiac=`, `ts_utc` = timestamp w **UTC**; `wibracje_rms_mg` puste przed
  montażem czujnika (`serwis_windy.czujnik_wibracji_od`); `tryb` = normalny / serwis / wylaczona.
- **PMS**: kwoty w PLN; `pms_lokale.status` i `czynsz_katalogowy` to stan na dzień eksportu. Najmy z `data_wprowadzenia`
  po dniu eksportu to umowy podpisane przed eksportem z wprowadzeniem w przyszłości (lokal ma jeszcze status „wolny”).
- Czas biznesowy: Europe/Warsaw.

## Dane zewnętrzne

`geo_poi` i `gus_dzielnice` są generowane według reguł: nazwy dzielnic są realne, geometria przybliżona.
