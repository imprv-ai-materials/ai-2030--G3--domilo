# Kolejka zapytań: metryki zespołu doradców jako modele dbt (2026-11-15)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` przebudowana 2026-11-15 (`pypyr baza`,
w tym `dbt build`: 4 modele, 68 testów, wszystkie przeszły).

## Wnioski

1. Wynik zespołu, czyli umowy z zapytań i przychód na godzinę doradcy, ma teraz jedną definicję w dbt
   (schemat `metryki` w `domilo.duckdb`). Raporty i eksperyment z kolejką mają czytać te tabele, a nie liczyć
   po swojemu.
2. Wartość wyjściowa dla 2026-Q2: **5 496,56 zł wartości podpisanych umów na godzinę pracy doradcy**.
   Na tę wartość złożyło się 867 podpisań z zapytań (931 lokali, 27 202 460 zł) i 4 949 godzin pracy 11 doradców.
3. Tydzień do tygodnia ten wynik waha się mocno. Od 2025-07-07 do 2026-06-28 (51 pełnych tygodni) odchylenie
   standardowe wyniosło **18,7% średniej** (994,21 zł przy średniej 5 316,27 zł; 95% CI z bootstrapu 13,0–23,3%).
   Sygnał z tygodnia na tydzień jest bez pamięci (autokorelacja −0,09). Zmiana kolejki, która podniosłaby wynik
   o kilka procent, zginie więc w szumie pojedynczych tygodni. Eksperyment musi trwać wiele tygodni albo porównywać
   grupy w tych samych tygodniach.
4. Część wahań wynika z mianownika, a nie ze sprzedaży. W tygodniach z małą liczbą godzin (2025-12-22: 175 godzin,
   2026-06-01: 259 godzin) wynik rośnie do 8 119 i 9 092 zł/h, bo wartość umów nie spada razem z godzinami
   (1 420 780 i 2 354 860 zł wobec średnio 2 042 545 zł tygodniowo). Sama wartość umów waha się o 15,1% średniej,
   godziny o 12,9%.
5. Do potwierdzenia: liczymy tylko umowy z zapytań CRM (bez nich wynik 2026-Q2 to 5 676,44 zł/h) i sumujemy
   czynsz po lokalach umowy ramowej, bo wzór „czynsz × miesiące × liczba lokali” na jednym wierszu daje
   o 0,85% mniej (5 449,72 zł/h). Szczegóły w „Decyzjach do potwierdzenia”.

## Definicje (modele dbt w `api/api/data_platform/dbt/models/kolejka/`)

| Model (`metryki.*`) | 1 wiersz = | Definicja |
|---|---|---|
| `umowa_45d` | zapytanie z `crm_leady` (161 556) | z `leady_cel`: 1 = umowa najpóźniej 45 dni po `utworzono`, 0 = brak, NULL = zapytanie cenzurowane (młodsze niż 45 dni w dniu eksportu); [kolejka_target.md](kolejka_target.md) |
| `obsluzony` | zapytanie z `crm_leady` (161 556) | z `leady_cel`: co najmniej jedna aktywność doradcy (D01–D15) lub call center (CC) w 45 dni od utworzenia, bez wyniku `podpisanie`. Dla zapytań cenzurowanych okno jeszcze trwa, więc do metryk brać `not cenzurowany` |
| `wartosc_umowy` | podpisanie: umowa poza ramową albo cała umowa ramowa (26 145) | Σ po lokalach (czynsz × miesiące umowy), czyli czynsz × miesiące × liczba lokali, gdy lokale mają ten sam czynsz. Miesiące = pełne miesiące od `data_od` do `data_do` (włącznie) + reszta dni / 30,4375. Kolumny: `z_zapytania` (umowa z `crm_leady.id_umowy`), `nowa_umowa` (bez przedłużeń), `wartosc_wg_wzoru` (wzór na umowie głównej, do kontroli) |
| `przychod_na_godzine_doradcy` | okres: tydzień (pon.–niedz., 196) albo kwartał (15) | Σ `wartosc_umowy` podpisań z zapytań według `data_podpisania` / Σ `crm_grafik.godziny_pracy` doradców w okresie. Flagi: `pelny_okres` (okres w całości w danych), `zawiera_okno_migracji` (godzin call center nie ma w `crm_grafik`, wynik zawyżony). Wariant `*_nowe_wszystkie`: wszystkie nowe umowy, także bez zapytania |

`umowa_45d` i `obsluzony` nie powtarzają SQL. Wystawiają `leady_cel` (`api/api/ai/features/leady/leady_cel.sql`),
więc dotychczasowe raporty kolejki i modele dbt liczą to samo.

### Testy dbt

| Rodzaj | Gdzie | Co sprawdza |
|---|---|---|
| unikalność | `unique` na kluczach (`id_leada`, `id_podpisania`, `id_umowy`), `unikalna_kombinacja` (`okres`, `poczatek_okresu`) i (`crm_grafik.id_doradcy`, `data`) | jeden wiersz na jednostkę |
| not null | klucze, flagi, wartości; `umowa_45d` tylko dla `not cenzurowany`, `godz_do_pierwszego_kontaktu` tylko dla obsłużonych, `przychod_na_godzine_doradcy` dla pełnych okresów | brak dziur w definicjach |
| zakresy (`tests/generic/zakres.sql`) | `umowa_45d` ∈ {0, 1}; `dni_do_umowy` 0–45; `godz_do_pierwszego_kontaktu` 0–1 080 (45 × 24); `miesiace_umowy` 0,5–24; `czynsz`, `liczba_lokali`, `wartosc_umowy` ≥ 1; `data_podpisania` 2023-01-01 – 2026-09-30; `dni_pracy` w tygodniu 0–7; `godziny_doradcow` ≥ 1 w pełnych okresach; przychód ≥ 0; `crm_grafik.godziny_pracy` 0–24 | wartości możliwe biznesowo |
| relacje i słowniki | `id_umowy` → `pms_umowy`, `obsluzony.id_leada` → `umowa_45d`; `typ`, `linia`, `okres` | spójność z PMS i CRM |
| testy własne (`tests/singular/`) | umowa ramowa ma tyle umów, ile lokali; każda umowa zapytania ma wiersz w `wartosc_umowy` i jest nową umową; sumy tygodni i kwartałów = suma `wartosc_umowy` z zapytań i suma `crm_grafik` | brak podwójnego liczenia i zgubionych umów |

## Wyniki

### T1. Wartość wyjściowa 2026-Q2 (2026-04-01 – 2026-06-30)

| Miara | Wartość |
|---|---:|
| **przychód na godzinę doradcy (umowy z zapytań)** | **5 496,56 zł/h** |
| wartość podpisanych umów z zapytań | 27 202 460 zł |
| podpisania z zapytań / lokale | 867 / 931 |
| godziny pracy doradców | 4 949 |
| doradcy / dni pracy | 11 / 75 |
| wariant: wszystkie nowe umowy (913 podpisań, 28 092 700 zł) | 5 676,44 zł/h |
| wariant: wzór czynsz × miesiące × liczba lokali na umowie głównej (26 970 680 zł) | 5 449,72 zł/h (−0,85%) |
| średnia z 12 pełnych tygodni kwartału (2026-04-06 – 2026-06-28) | 5 626,14 zł/h (odchylenie 22,96% średniej) |

Średnia tygodni nie jest równa wynikowi kwartału, bo kwartał to Σ wartości / Σ godzin, a każdy tydzień ma inną
liczbę godzin. Wartością wyjściową jest wynik kwartału.

### T2. Kwartały 2025-Q3 – 2026-Q2

| Kwartał | Doradcy | Godziny | Podpisania z zapytań | Lokale | Wartość umów | Przychód / h | Przychód / h, wszystkie nowe |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-Q3 | 12 | 5 376 | 985 | 1 063 | 28 633 360 zł | 5 326,15 zł | 5 326,15 zł |
| 2025-Q4 | 11 | 4 928 | 816 | 881 | 25 237 690 zł | 5 121,28 zł | 5 224,12 zł |
| 2026-Q1 | 11 | 5 089 | 840 | 914 | 25 917 490 zł | 5 092,85 zł | 5 371,49 zł |
| **2026-Q2** | 11 | 4 949 | 867 | 931 | 27 202 460 zł | **5 496,56 zł** | 5 676,44 zł |

### T3. Zmienność tygodniowa, 51 pełnych tygodni 2025-07-07 – 2026-06-28

| Seria tygodniowa | Średnia | Odchylenie std. (n − 1) | **Odchylenie w % średniej** (95% CI) | Mediana | Min | Maks | Autokorelacja (1 tydz.) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **przychód na godzinę doradcy** | 5 316,27 zł | 994,21 zł | **18,70%** (13,04–23,26) | 5 150,74 zł | 3 836,65 zł | 9 092,12 zł | −0,09 |
| przychód na godzinę, wszystkie nowe umowy | 5 472,57 zł | 1 057,83 zł | 19,33% (12,44–24,46) | 5 280,26 zł | 3 958,82 zł | 9 374,06 zł | −0,09 |
| wartość umów z zapytań (licznik) | 2 042 545 zł | 307 585 zł | 15,06% (12,04–17,70) | 2 049 720 zł | 1 396 540 zł | 2 723 440 zł | 0,13 |
| godziny doradców (mianownik) | 389,67 | 50,26 | 12,90% (8,16–17,78) | 406 | 175 | 448 | 0,28 |

Okres: tygodnie poniedziałek–niedziela w całości między 2025-07-01 a 2026-06-30. Niepełne tygodnie na brzegach
(2025-06-30 – 07-06 i 2026-06-29 – 07-05) pominięte. 95% CI: bootstrap tygodni (2 000 losowań ze zwracaniem,
ziarno 20261115). Okno migracji (2025-03) jest poza tym okresem.

### T4. Tygodnie skrajne

| Tydzień od | Dni pracy | Doradcy | Godziny | Podpisania | Wartość umów | Przychód / h |
|---|---:|---:|---:|---:|---:|---:|
| 2026-01-05 | 5 | 11 | 364 | 53 | 1 396 540 zł | 3 836,65 zł |
| 2025-07-14 | 6 | 11 | 441 | 65 | 1 745 840 zł | 3 958,82 zł |
| 2025-11-10 | 5 | 10 | 315 | 62 | 2 194 810 zł | 6 967,65 zł |
| 2025-12-22 | 3 | 10 | 175 | 48 | 1 420 780 zł | 8 118,74 zł |
| 2026-06-01 | 5 | 9 | 259 | 69 | 2 354 860 zł | 9 092,12 zł |

### T5. `wartosc_umowy`: wszystkie podpisania 2023-01 – 2026-09

| Z zapytania | Typ | Podpisania | Lokale | Miesiące umowy (min / mediana / maks) | Σ wartość umów | Σ wzór na umowie głównej |
|---|---|---:|---:|---|---:|---:|
| tak | pierwsza | 8 044 | 8 980 | 12 / 12 / 24 | 289 277 760 zł | 288 861 180 zł |
| tak | średnioterminowa | 4 067 | 4 067 | 1 / 5 / 6 | 64 689 580 zł | 64 689 580 zł |
| nie | pierwsza | 1 507 | 1 507 | 12 / 12 / 24 | 39 701 040 zł | 39 701 040 zł |
| nie | średnioterminowa | 887 | 887 | 1 / 5 / 6 | 13 923 030 zł | 13 923 030 zł |
| nie | przedłużenie | 11 640 | 11 640 | 12 / 12 / 12 | 330 758 640 zł | 330 758 640 zł |

12 111 podpisań z zapytań = 12 111 zapytań z umową w `leady_cel` ([kolejka_target.md](kolejka_target.md), R5).
Umowy roczne i dłuższe (bez MID) mają 12, 18 albo 24 pełne miesiące (20 358 / 521 / 312 umów). Każda z 655 umów
ramowych z więcej niż jednym lokalem ma lokale o różnym czynszu, stąd różnica w kolumnie „wzór”.

## Decyzje do potwierdzenia

- **Które umowy liczą się do wyniku zespołu:** tylko podpisania z zapytań CRM (`crm_leady.id_umowy`), bo tylko na nie
  wpływa kolejka. Bez przedłużeń, bo to praca retencji. Wariant ze wszystkimi nowymi umowami jest w tabeli
  (`*_nowe_wszystkie`).
- **Umowy ramowe:** w `pms_umowy` każdy lokal ramowej to osobny wiersz z `liczba_lokali` całej ramowej. Wzór
  „czynsz × miesiące × liczba lokali” na każdym wierszu liczyłby ramową N × N razy. Dlatego jednym wierszem jest
  podpisanie, a wartość to suma czynsz × miesiące po lokalach. Wzór na umowie głównej (tej z zapytania) jest
  w kolumnie `wartosc_wg_wzoru`: w 2026-Q2 daje 26 970 680 zł zamiast 27 202 460 zł.
- **Czynsz** bez rabatu (`rabat_mies`) i bez indeksacji w umowach dwuletnich. **Okres** według `data_podpisania`,
  a nie według dnia zapytania.
- **Godziny:** wszyscy doradcy z `crm_grafik`. Call center nie ma godzin w grafiku, więc okresy z oknem migracji
  (2025-03-03 – 2025-04-13) mają flagę `zawiera_okno_migracji`.
- **Tydzień:** poniedziałek–niedziela, w zmienności tylko tygodnie w całości w okresie 2025-07 – 2026-06.
  Odchylenie standardowe z próby (n − 1).

## SQL i kod

```bash
pypyr baza                     # baza z data/, leady_cel, dbt build (modele metryki.* i testy)
# albo osobno: cd api && poetry run python -m api.data_platform.dbt_uruchom build
cd api && poetry run python -m api.data_platform.kolejka_metryki   # liczby z T1–T4
poetry run pytest api/tests/test_kolejka_metryki.py
```

- Projekt dbt: `api/api/data_platform/dbt/` (`dbt_project.yml`, `profiles.yml` z `TimeZone = Europe/Warsaw`,
  modele `models/kolejka/*.sql`, testy w `models/kolejka/kolejka.yml`, `models/zrodla.yml`, `tests/`).
  dbt-core 1.12.7 + dbt-duckdb 1.11.1 (grupa dev w `pyproject.toml`).
- Uruchamianie: `api/api/data_platform/dbt_uruchom.py` (ustawia ścieżkę bazy `DOMILO_DUCKDB`).
- Liczby: `api/api/data_platform/kolejka_metryki.py`, wynik w `api/api/data_platform/wyniki/kolejka_metryki.json`,
  seria tygodniowa w `wyniki/przychod_tygodnie.parquet`.

**Q1. Wartość wyjściowa 2026-Q2** (`SQL_KWARTAL`):

```sql
SELECT * FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'kwartal' AND poczatek_okresu = DATE '2026-04-01';
```

**Q2. Tygodnie do zmienności** (`SQL_TYGODNIE`; średnia, odchylenie i bootstrap w `statystyki_tygodni`,
`bootstrap_odchylenia_proc`):

```sql
SELECT poczatek_okresu, godziny_doradcow, wartosc_umow_z_zapytan, przychod_na_godzine_doradcy,
       przychod_na_godzine_nowe_wszystkie
FROM metryki.przychod_na_godzine_doradcy
WHERE okres = 'tydzien' AND pelny_okres
  AND poczatek_okresu >= DATE '2025-07-01' AND koniec_okresu <= DATE '2026-06-30'
ORDER BY poczatek_okresu;
```

**Q3. Wzór na umowie głównej w 2026-Q2** (`SQL_WZOR`):

```sql
SELECT count(*) AS podpisania, sum(wartosc_umowy) AS wartosc_umowy, sum(wartosc_wg_wzoru) AS wartosc_wg_wzoru
FROM metryki.wartosc_umowy
WHERE z_zapytania AND data_podpisania BETWEEN DATE '2026-04-01' AND DATE '2026-06-30';
```

**Q4. Podsumowanie `wartosc_umowy` (T5):**

```sql
SELECT z_zapytania, typ, count(*) AS podpisania, sum(liczba_umow) AS lokale,
       min(miesiace_umowy), median(miesiace_umowy), max(miesiace_umowy),
       sum(wartosc_umowy), sum(wartosc_wg_wzoru)
FROM metryki.wartosc_umowy GROUP BY ALL ORDER BY ALL;
SELECT miesiace_umowy, count(*) FROM metryki.wartosc_umowy
WHERE typ <> 'średnioterminowa' GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) FILTER (WHERE liczba_lokali > 1),
       count(*) FILTER (WHERE liczba_lokali > 1 AND czynsz_mies_razem <> czynsz * liczba_lokali)
FROM metryki.wartosc_umowy;
```

**Rdzeń `wartosc_umowy.sql`** (miesiące umowy i suma po lokalach ramowej):

```sql
date_sub('month', data_od, data_do + 1) AS pelne_miesiace,
pelne_miesiace + date_diff('day', CAST(data_od + to_months(pelne_miesiace) AS DATE), data_do + 1) / 30.4375
    AS miesiace_umowy,
-- klucz podpisania: coalesce(id_umowy_ramowej, id_umowy); umowa główna = ta z zapytania, inaczej najmniejsze id
sum(czynsz * miesiace_umowy) AS wartosc_umowy
```

**Rdzeń `przychod_na_godzine_doradcy.sql`** (dla `week` i `quarter`):

```sql
-- godziny: crm_grafik × crm_doradcy, date_trunc(okres, data); umowy: wartosc_umowy WHERE nowa_umowa,
-- date_trunc(okres, data_podpisania); full outer join po początku okresu
wartosc_umow_z_zapytan / nullif(godziny_doradcow, 0) AS przychod_na_godzine_doradcy
```
