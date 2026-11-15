# Kolejka zapytań: target `umowa_45d` (tabela `leady_cel`)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw, baza `domilo.duckdb` przebudowana 2026-11-15 (`pypyr baza`).

## Wnioski

1. Spośród 154 743 zapytań, które do dnia eksportu miały pełne 45 dni na decyzję, umową skończyło się 11 856
   (7,66%). Najmłodsze 6 813 zapytań (utworzone od 2026-08-17) nie mają jeszcze wyniku, więc nie wchodzą ani do
   uczenia, ani do ocen. Konwersja liczona tylko z zamkniętych zapytań myli dla ostatnich miesięcy (wrzesień 2026:
   4,87%), bo odmowy zamykają się szybciej niż umowy.
2. To, czy zapytanie skończy się umową, zależy w dużej mierze od tego, czy ktoś się odezwał. Obsłużone zapytania
   kończą się umową w 9,05%, a nieobsłużone w 1,05%. Poza oknem migracji doradcy kontaktują się tylko z 40,8%
   zapytań z `domteraz` (z innych źródeł z 90–99%) i tak jest co roku od 2023. Dlatego `domteraz` wygląda na
   najsłabsze źródło (3,48%), choć gdy wszyscy byli obsłużeni (okno migracji), konwersja `domteraz` wyniosła 8,19%,
   czyli więcej niż `lokum24` (6,52%) i `social` (4,84%).
3. W oknie migracji (2025-03-03 – 2025-04-13) zewnętrzne call center skontaktowało się z każdym zapytaniem, a mediana
   czasu do pierwszego kontaktu spadła z ok. 74 do 12,5 godziny. Konwersja wyniosła wtedy 10,51% wobec
   7,30% w 6 tygodniach przed oknem, 7,28% w 6 tygodniach po nim oraz 7,12% i 7,77% w tych samych tygodniach 2024
   i 2026. Z danych nie da się rozdzielić, ile z tego wzrostu daje szybszy kontakt, ile kontakt z każdym, a ile
   inny sposób pracy call center.
4. Dla modelu oznacza to, że `umowa_45d` łączy jakość zapytania z decyzją zespołu, do kogo oddzwonić. Model uczony na
   całej historii przejmie obecne nawyki (np. „`domteraz` jest słabe”). Okno migracji (5 320 zapytań, wszystkie
   obsłużone) to jedyny okres, w którym wynik nie zależał od kolejki. Warto ocenić na nim model osobno.

## Definicja `leady_cel`

Jeden wiersz to jedno zapytanie z `crm_leady` (161 556 wierszy). SQL: `api/api/ai/features/leady/leady_cel.sql`.
`pypyr baza` buduje tabelę w drugim kroku, po przebudowie bazy.

| Kolumna | Znaczenie |
|---|---|
| `umowa_45d` | 1: umowa najpóźniej 45 dni po `utworzono`; 0: brak; NULL: zapytanie cenzurowane |
| `cenzurowany` | `utworzono + 45 dni > 2026-10-01 00:00` (+02:00), czyli w dniu eksportu zapytanie było młodsze niż 45 dni. Ma NULL także wtedy, gdy umowa już jest (255 takich zapytań), bo inaczej młode zapytania miałyby tylko szybkie umowy |
| `data_umowy`, `zrodlo_umowy`, `id_umowy`, `dni_do_umowy` | pierwsze przejście na status `umowa` w `crm_historia_statusow`; gdy go brak, `pms_umowy.data_podpisania` przez `crm_leady.id_umowy`. Obecnie wszystkie 12 111 umów są w obu źródłach (`crm+pms`), z tym samym dniem |
| `status_koncowy`, `zamkniety`, `data_zamkniecia`, `utracony_90d` | ostatni status z **historii** statusów, nie z `crm_leady.status`. Zapytanie `w_toku` dłużej niż 90 dni (do następnej zmiany statusu albo do eksportu) liczymy jako `utracony` z datą wejścia w `w_toku` + 90 dni. Zamknięte = `umowa` albo `utracony` |
| `obsluzony`, `obsluzony_cc`, `liczba_kontaktow_45d`, `pierwszy_kontakt`, `godz_do_pierwszego_kontaktu` | aktywność doradcy (`D01`–`D15`) lub call center (`CC`) w `crm_aktywnosci` w ciągu 45 dni od utworzenia, **bez** wyniku `podpisanie`, bo to zapis samej umowy, nie kontakt z klientem. Nieodebrany telefon też się liczy |
| `okno_migracji` | `utworzono` od 2025-03-03 00:00 do 2025-04-13 23:59 (czas warszawski) |

`umowa_45d`, `status_koncowy` i flagi to etykiety i opis. **Nie są cechami do predykcji**, bo znamy je dopiero po
fakcie. Przy remisie czasu w historii (2 zapytania: `w_toku` i `umowa` w tej samej sekundzie) kolejność ustala etap
statusu: `otwarty` → `w_toku` → status końcowy.

## Tabele

### Podsumowanie (R1)

| Zapytania | Cenzurowane | w tym z umową | Niecenzurowane | Umowy w 45 dni | Konwersja 45 dni | Zamknięte | w tym utracone po 90 dniach `w_toku` | Otwarte | Konwersja zamkniętych | Obsłużone (niecenz.) | Konwersja obsłużonych | Konwersja nieobsłużonych |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 161 556 | 6 813 | 255 | 154 743 | 11 856 | 7,66% | 159 154 | 618 | 2 402 | 7,61% | 82,59% | 9,05% | 1,05% |

Otwarte = 1 131 `w_toku` krócej niż 90 dni + 1 271 `otwarty`. Z 618 utraconych po 90 dniach 542 nadal miało w CRM
status `w_toku`, a 76 zostało później zamkniętych jako utracone.

### Okno migracji i poza nim (R2b)

| Okres | Zapytania | Niecenz. | Umowy 45 dni | Konwersja 45 dni | Zamknięte | Konwersja zamkniętych | Obsłużone | Obsłużone (niecenz.) | Konwersja obsłużonych | Konwersja nieobsłużonych |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| w oknie | 5 320 | 5 320 | 559 | 10,51% | 5 320 | 10,51% | 100,00% | 5 320 | 10,51% | brak (0 nieobsłużonych) |
| poza oknem | 156 236 | 149 423 | 11 297 | 7,56% | 153 834 | 7,51% | 81,97% | 122 485 | 8,99% | 1,05% |

### Źródło × okno migracji (R2)

| Źródło | Okres | Zapytania | Niecenz. | Umowy 45 dni | Konwersja 45 dni | Zamknięte | Konwersja zamkniętych | Obsłużone | Obsłużone (niecenz.) | Konwersja obsłużonych | Konwersja nieobsłużonych |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| domteraz | w oknie | 1 453 | 1 453 | 119 | 8,19% | 1 453 | 8,19% | 100,00% | 1 453 | 8,19% | — |
| domteraz | poza oknem | 41 260 | 39 475 | 1 375 | 3,48% | 40 401 | 3,49% | 40,80% | 16 107 | 6,96% | 1,09% |
| lokum24 | w oknie | 2 040 | 2 040 | 133 | 6,52% | 2 040 | 6,52% | 100,00% | 2 040 | 6,52% | — |
| lokum24 | poza oknem | 58 536 | 56 060 | 2 690 | 4,80% | 57 772 | 4,78% | 95,67% | 53 630 | 4,99% | 0,66% |
| polecenie | w oknie | 249 | 249 | 46 | 18,47% | 249 | 18,47% | 100,00% | 249 | 18,47% | — |
| polecenie | poza oknem | 7 618 | 7 324 | 1 162 | 15,87% | 7 527 | 15,70% | 98,92% | 7 245 | 16,00% | 3,80% |
| relokacja_b2b | w oknie | 359 | 359 | 79 | 22,01% | 359 | 22,01% | 100,00% | 359 | 22,01% | — |
| relokacja_b2b | poza oknem | 13 228 | 12 497 | 2 443 | 19,55% | 12 997 | 19,20% | 99,46% | 12 430 | 19,64% | 2,99% |
| social | w oknie | 248 | 248 | 12 | 4,84% | 248 | 4,84% | 100,00% | 248 | 4,84% | — |
| social | poza oknem | 7 868 | 7 544 | 233 | 3,09% | 7 763 | 3,05% | 90,42% | 6 821 | 3,33% | 0,83% |
| www | w oknie | 971 | 971 | 170 | 17,51% | 971 | 17,51% | 100,00% | 971 | 17,51% | — |
| www | poza oknem | 27 726 | 26 523 | 3 394 | 12,80% | 27 374 | 12,67% | 98,99% | 26 252 | 12,92% | 1,11% |

„—” = w oknie nie było nieobsłużonych zapytań. „Obsłużone” to odsetek wśród niecenzurowanych. Konwersja
obsłużonych i nieobsłużonych jest liczona na niecenzurowanych. Konwersja zamkniętych obejmuje też zamknięte
zapytania cenzurowane.

Przy małych liczbach umów w oknie (np. `social` 12, `polecenie` 46) różnice między oknem a resztą okresu mogą
być przypadkowe. Przedziałów ufności nie liczyliśmy.

### Okresy porównawcze po 6 tygodni (R3)

| Okres | Zapytania | Obsłużone | Obsłużone przez CC | Mediana godzin do 1. kontaktu | Konwersja 45 dni | Konwersja obsłużonych |
|---|---:|---:|---:|---:|---:|---:|
| te same tygodnie 2024 (2024-03-04 – 2024-04-14) | 4 674 | 81,02% | 0,00% | 74,5 | 7,12% | 8,42% |
| 6 tyg. przed oknem (2025-01-20 – 2025-03-02) | 4 861 | 83,32% | 0,00% | 74,4 | 7,30% | 8,54% |
| **okno migracji (2025-03-03 – 2025-04-13)** | 5 320 | 100,00% | 100,00% | 12,5 | **10,51%** | 10,51% |
| 6 tyg. po oknie (2025-04-14 – 2025-05-25) | 5 043 | 81,86% | 0,00% | 76,0 | 7,28% | 8,72% |
| te same tygodnie 2026 (2026-03-02 – 2026-04-12) | 5 056 | 83,27% | 0,00% | 74,5 | 7,77% | 9,05% |

### Obsłużone według źródła i roku, poza oknem migracji, niecenzurowane (R6)

| Źródło | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| domteraz | 40,0% | 40,7% | 41,9% | 40,5% |
| lokum24 | 95,5% | 95,8% | 95,6% | 95,8% |
| polecenie | 98,7% | 99,1% | 99,1% | 98,9% |
| relokacja_b2b | 99,4% | 99,6% | 99,5% | 99,3% |
| social | 90,0% | 90,3% | 91,1% | 90,3% |
| www | 99,1% | 98,8% | 99,2% | 98,8% |

### Mediana godzin do pierwszego kontaktu według źródła, niecenzurowane (R7)

| Źródło | poza oknem | w oknie |
|---|---:|---:|
| domteraz | 90,0 | 12,4 |
| lokum24 | 73,3 | 12,6 |
| polecenie | 69,9 | 12,9 |
| relokacja_b2b | 70,6 | 12,5 |
| social | 79,5 | 12,5 |
| www | 70,9 | 12,4 |

Mediana poza oknem jest liczona tylko dla zapytań obsłużonych. Nieobsłużone nie mają pierwszego kontaktu.

### Dlaczego nie „konwersja zamkniętych”: ostatnie miesiące (R4)

| Miesiąc utworzenia | Zapytania | Niecenz. | Konwersja 45 dni | Zamknięte | Konwersja zamkniętych |
|---|---:|---:|---:|---:|---:|
| 2026-04 | 3 733 | 3 733 | 7,80% | 3 733 | 7,80% |
| 2026-05 | 3 603 | 3 603 | 7,69% | 3 603 | 7,69% |
| 2026-06 | 4 181 | 4 181 | 7,65% | 4 180 | 7,66% |
| 2026-07 | 4 401 | 4 401 | 7,45% | 4 375 | 7,50% |
| 2026-08 | 4 547 | 2 278 | 6,50% | 4 459 | 6,57% |
| 2026-09 | 4 544 | 0 | brak (wszystkie cenzurowane) | 2 257 | 4,87% |

Sierpień 2026 ma też niższą konwersję 45 dni (6,50%). Liczymy ją tylko na zapytaniach z 1–16 sierpnia, więc
z tych danych nie wiadomo, czy to spadek, czy zmienność.

### Kontrole definicji (R5)

| Zapytania z umową | Umowa w CRM i PMS | Umowa po 45 dniach (niecenz.) | Maks. dni do umowy | Umowa bez kontaktu doradcy | `w_toku` > 90 dni, w CRM nadal `w_toku` | `w_toku` ≤ 90 dni | `otwarty` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 12 111 | 12 111 | 0 | 44,92 | 291 | 542 | 1 131 | 1 271 |

W danych żadna umowa nie powstała później niż 45 dni od zapytania (maks. 44,92 dnia). W tych danych `umowa_45d`
oznacza więc to samo co „umowa kiedykolwiek”. Dzień umowy w CRM zgadza się z `pms_umowy.data_podpisania`
dla wszystkich 11 856 umów w 45 dniach (zapytanie Z1 niżej). 291 umów powstało bez żadnej aktywności doradcy
(przejście `otwarty` → `umowa`).

## SQL i kod

Budowa tabeli: `pypyr baza` (przebudowa bazy, potem `python -m api.ai.features.leady.leady_cel`). Testy:
`pypyr test tests=api/tests/test_leady_cel.py` (granica 45 dni, cenzurowanie, reguła 90 dni, remis czasu,
`obsluzony` bez podpisania, granice okna migracji, niezależność od `crm_leady.status`).

Zapytania poniżej działają na `domilo.duckdb`. CLI `duckdb` 1.5 nie otworzy pliku w formacie 2.0, dlatego
uruchamiamy je z Pythona:

```python
# cd api && poetry run python
from api.adapters.duckdb_baza import polacz

con = polacz()  # strefa sesji Europe/Warsaw
print(con.execute("""<zapytanie>""").df().to_string())
```

R1, podsumowanie:

```sql
SELECT
    count(*) AS leady,
    count(*) FILTER (WHERE cenzurowany) AS cenzurowane,
    count(*) FILTER (WHERE cenzurowany AND data_umowy IS NOT NULL) AS cenzurowane_z_umowa,
    count(umowa_45d) AS niecenzurowane,
    sum(umowa_45d) AS umowy_45d,
    round(100 * avg(umowa_45d), 2) AS konwersja_45d_pct,
    count(*) FILTER (WHERE zamkniety) AS zamkniete,
    count(*) FILTER (WHERE utracony_90d) AS utracone_90d_w_toku,
    count(*) FILTER (WHERE NOT zamkniety) AS otwarte,
    round(100 * avg((status_koncowy = 'umowa')::INT) FILTER (WHERE zamkniety), 2) AS konwersja_zamknietych_pct,
    round(100 * avg(obsluzony::INT) FILTER (WHERE NOT cenzurowany), 2) AS obsluzone_pct,
    round(100 * avg(umowa_45d) FILTER (WHERE obsluzony), 2) AS konwersja_obsluzonych_pct,
    round(100 * avg(umowa_45d) FILTER (WHERE NOT obsluzony), 2) AS konwersja_nieobsluzonych_pct
FROM leady_cel;
```

R2 (źródło × okno) i R2b (razem): w R2b usuń `zrodlo` z listy kolumn i z `ORDER BY`.

```sql
SELECT
    zrodlo,
    CASE WHEN okno_migracji THEN 'w oknie' ELSE 'poza oknem' END AS okres,
    count(*) AS leady,
    count(umowa_45d) AS niecenzurowane,
    sum(umowa_45d) AS umowy_45d,
    round(100 * avg(umowa_45d), 2) AS konwersja_45d_pct,
    count(*) FILTER (WHERE zamkniety) AS zamkniete,
    round(100 * avg((status_koncowy = 'umowa')::INT) FILTER (WHERE zamkniety), 2) AS konwersja_zamknietych_pct,
    round(100 * avg(obsluzony::INT) FILTER (WHERE NOT cenzurowany), 2) AS obsluzone_pct,
    count(umowa_45d) FILTER (WHERE obsluzony) AS obsluzone_niecenz,
    round(100 * avg(umowa_45d) FILTER (WHERE obsluzony), 2) AS konwersja_obsluzonych_pct,
    round(100 * avg(umowa_45d) FILTER (WHERE NOT obsluzony), 2) AS konwersja_nieobsluzonych_pct
FROM leady_cel
GROUP BY ALL
ORDER BY zrodlo, okres DESC;
```

R3, okresy porównawcze:

```sql
WITH okresy(okres, od, do_) AS (
    VALUES
        ('a) te same tygodnie 2024', TIMESTAMPTZ '2024-03-04 00:00:00+01', TIMESTAMPTZ '2024-04-15 00:00:00+02'),
        ('b) 6 tyg. przed oknem', TIMESTAMPTZ '2025-01-20 00:00:00+01', TIMESTAMPTZ '2025-03-03 00:00:00+01'),
        ('c) okno migracji', TIMESTAMPTZ '2025-03-03 00:00:00+01', TIMESTAMPTZ '2025-04-14 00:00:00+02'),
        ('d) 6 tyg. po oknie', TIMESTAMPTZ '2025-04-14 00:00:00+02', TIMESTAMPTZ '2025-05-26 00:00:00+02'),
        ('e) te same tygodnie 2026', TIMESTAMPTZ '2026-03-02 00:00:00+01', TIMESTAMPTZ '2026-04-13 00:00:00+02')
)
SELECT
    o.okres,
    count(*) AS leady,
    round(100 * avg(c.obsluzony::INT), 2) AS obsluzone_pct,
    round(100 * avg(c.obsluzony_cc::INT), 2) AS obsluzone_cc_pct,
    round(median(c.godz_do_pierwszego_kontaktu), 1) AS mediana_godz_do_kontaktu,
    round(100 * avg(c.umowa_45d), 2) AS konwersja_45d_pct,
    round(100 * avg(c.umowa_45d) FILTER (WHERE c.obsluzony), 2) AS konwersja_obsluzonych_pct
FROM leady_cel AS c
JOIN okresy AS o ON c.utworzono >= o.od AND c.utworzono < o.do_
GROUP BY o.okres
ORDER BY o.okres;
```

R4, ostatnie miesiące:

```sql
SELECT
    strftime(utworzono, '%Y-%m') AS miesiac,
    count(*) AS leady,
    count(umowa_45d) AS niecenzurowane,
    round(100 * avg(umowa_45d), 2) AS konwersja_45d_pct,
    count(*) FILTER (WHERE zamkniety) AS zamkniete,
    round(100 * avg((status_koncowy = 'umowa')::INT) FILTER (WHERE zamkniety), 2) AS konwersja_zamknietych_pct
FROM leady_cel
WHERE utworzono >= TIMESTAMPTZ '2026-04-01 00:00:00+02'
GROUP BY ALL
ORDER BY miesiac;
```

R5, kontrole definicji:

```sql
SELECT
    count(*) FILTER (WHERE data_umowy IS NOT NULL) AS leady_z_umowa,
    count(*) FILTER (WHERE zrodlo_umowy = 'crm+pms') AS umowa_w_crm_i_pms,
    count(*) FILTER (WHERE data_umowy IS NOT NULL AND NOT cenzurowany AND umowa_45d = 0) AS umowa_po_45_dniach,
    round(max(dni_do_umowy), 2) AS max_dni_do_umowy,
    count(*) FILTER (WHERE data_umowy IS NOT NULL AND NOT obsluzony) AS umowa_bez_kontaktu,
    count(*) FILTER (WHERE utracony_90d AND status_na_eksport = 'w_toku') AS w_toku_90d_otwarte_w_crm,
    count(*) FILTER (WHERE status_koncowy = 'w_toku') AS w_toku_do_90d,
    count(*) FILTER (WHERE status_koncowy = 'otwarty') AS otwarty
FROM leady_cel AS c
JOIN (
    SELECT id_leada, status_na AS status_na_eksport
    FROM crm_historia_statusow
    QUALIFY row_number() OVER (
        PARTITION BY id_leada ORDER BY data_czas DESC, status_na IN ('umowa', 'utracony') DESC
    ) = 1
) USING (id_leada);
```

Z1, zgodność dnia umowy z PMS (wynik: 11 856 i 11 856):

```sql
SELECT
    count(*) FILTER (WHERE CAST(l.utworzono AS DATE) + 45 >= u.data_podpisania) AS pms_w_45_dniach,
    count(*) FILTER (WHERE c.umowa_45d = 1) AS umowa_45d
FROM leady_cel AS c
JOIN crm_leady AS l USING (id_leada)
JOIN pms_umowy AS u ON u.id_umowy = l.id_umowy
WHERE NOT c.cenzurowany;
```

R6, obsłużone według źródła i roku:

```sql
PIVOT (
    SELECT zrodlo, year(utworzono) AS rok, obsluzony
    FROM leady_cel
    WHERE NOT okno_migracji AND NOT cenzurowany
) ON rok USING round(100 * avg(obsluzony::INT), 1) GROUP BY zrodlo ORDER BY zrodlo;
```

R7, czas do pierwszego kontaktu:

```sql
SELECT
    zrodlo,
    round(median(godz_do_pierwszego_kontaktu) FILTER (WHERE NOT okno_migracji), 1) AS poza_oknem_h,
    round(median(godz_do_pierwszego_kontaktu) FILTER (WHERE okno_migracji), 1) AS w_oknie_h
FROM leady_cel
WHERE NOT cenzurowany
GROUP BY zrodlo
ORDER BY zrodlo;
```
