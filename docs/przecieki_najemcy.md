# Lista retencyjna: cechy na dzień migawki i przecieki (tabela `cechy_najemcy`)

Stan danych: eksport 2026-09-30 23:59 Europe/Warsaw; tabele `migawki_najemcy` i `cechy_najemcy` zbudowane
w `domilo.duckdb` 2026-11-16. Definicja migawki i targetu `odejdzie`: [target_najemcy.md](target_najemcy.md).

## Wnioski

1. Wszystkie cechy liczymy tak, jak wyglądały dane rano w dniu migawki (60 dni przed końcem umowy): tylko
   zdarzenia z datą wcześniejszą niż dzień migawki. Tego samego dnia w ciągu dnia (8:00–20:00) najemca dostaje
   w portalu ofertę przedłużenia: 18 212 takich wiadomości wysłano dokładnie w dniu migawki. Wszystko, co dzieje się
   od tej chwili, to reakcja na ofertę, a nie sygnał do jej przygotowania.
2. Logowania do portalu są w danych tylko jako suma za cały miesiąc kalendarzowy. Miesiąc migawki obejmuje średnio
   w 51,5% dni od migawki wzwyż, w tym dzień wysłania oferty. Gdyby go wliczyć, odsetek najemców, którzy oglądali
   ofertę przedłużenia, wzrósłby z 38,44% do 70,05%, czyli model widziałby reakcję na ofertę, której w dniu decyzji
   jeszcze nie ma. W dniu migawki suma za bieżący miesiąc w ogóle nie istnieje, więc bierzemy tylko 3 pełne miesiące
   przed miesiącem migawki.
3. `czynsz_katalogowy` to cennik z dnia eksportu (2026), a nie z dnia migawki. Czynsz względem niego rośnie z roku
   na rok (mediana 0,858 w 2023 i 0,950 w 2026), więc taka cecha rozpoznaje głównie rok migawki (AUC 0,873 dla „rok
   2025 lub później”). Zastąpiliśmy ją porównaniem z czynszem nowych umów w podobnych lokalach z 12 miesięcy przed
   migawką; ta cecha nie zależy od roku (AUC 0,473).
4. Podobnie stan na dzień eksportu psuje inne pola. `status` zgłoszeń z portalu nie pokazuje żadnego otwartego
   zgłoszenia (w dniu migawki otwartych było 275). Ostatnia ankieta liczona do dnia eksportu różni się od tej znanej
   w dniu migawki w 6 853 umowach. Końcowe opóźnienie płatności różni się od znanego w dniu migawki w 550 umowach.
5. Pojedynczo cechy słabo przewidują odejście: AUC od 0,418 (`nr_okresu`) do 0,618 (linia B2B). Płatności nie
   wnoszą prawie nic (AUC 0,494–0,502). To dopiero materiał dla modelu, który trzeba porównać z punktem odniesienia
   w `evals/porownanie.md`. Nie używamy `rok_urodzenia` ani `jezyk_kontaktu`
   (`wykluczone.yaml`), a rodziny cech w ogóle nie czytają `pms_najemcy`.

## Cechy (`cechy_najemcy`, jeden wiersz na umowę z `migawki_najemcy`, 19 231 wierszy)

Migawka = stan na początek dnia `data_migawki` (`data_do` − 60 dni). Okno „90 dni” to [migawka − 90 dni, migawka).

| Rodzina | Cecha | Definicja | Braki % |
|---|---|---|---:|
| umowa | `linia`, `miesiecy_umowy`, `nr_okresu` | z bieżącej umowy | 0,00 |
| umowa | `staz_dni` | dni od `pms_najmy.data_wprowadzenia` do migawki | 0,00 |
| umowa | `indeksacja_ostatnia_pct` | `indeksacja_pct` bieżącej umowy (ostatnie przedłużenie przed migawką); NULL przy pierwszej umowie | 52,90 |
| umowa | `czynsz_m2` | czynsz bieżącej umowy / metraż | 0,00 |
| umowa | `czynsz_do_podobnych` | czynsz / (mediana czynszu za m² nowych umów `pierwsza` w podobnych lokalach × metraż). Podobne: ta sama linia najmu i liczba pokoi, `data_od` w 365 dniach przed migawką, inny lokal; najpierw budynek, a gdy jest tam < 5 umów, miasto (`podobne_poziom`, `podobne_liczba`). NULL, gdy także w mieście jest < 5 umów | 0,63 |
| platnosci | `plat_liczba_90d` | miesiące z terminem płatności (10. dnia miesiąca) w oknie 90 dni; płatności wszystkich umów najmu | 0,00 |
| platnosci | `plat_spoznione_90d`, `plat_max_opoznienie_90d`, `plat_srednie_opoznienie_90d` | opóźnienie znane w dniu migawki: `dni_opoznienia`, gdy zapłacono przed migawką, inaczej dni od terminu do migawki | 0,00 / 0,56 / 0,56 |
| platnosci | `plat_zalegle_na_migawke` | miesiące po terminie niezapłacone przed migawką | 0,00 |
| relacja | `zgl_90d`, `zgl_365d` | zgłoszenia w portalu (ten najemca i lokal, od początku najmu) | 0,00 |
| relacja | `zgl_otwarte_na_migawke` | utworzone przed migawką i niezamknięte przed migawką (`zamknieto`, nie `status`) | 0,00 |
| relacja | `ocena_srednia_365d`, `ocena_min_365d`, `ocena_liczba_365d` | `ocena_obslugi` zgłoszeń zamkniętych w 365 dniach przed migawką | 52,59 / 52,59 / 0,00 |
| relacja | `ankieta_ostatni_wynik`, `ankieta_dni_od_odpowiedzi` | ASOF: ostatnia odpowiedź z `data_odpowiedzi` < migawka, od początku najmu | 62,47 |
| relacja | `ankieta_brak_wyniku` | 1, gdy takiej odpowiedzi nie ma | 0,00 |
| relacja | `ankiety_bez_odpowiedzi_365d` | ankiety wysłane w 365 dniach przed migawką bez odpowiedzi przed migawką | 0,00 |
| relacja | `portal_miesiace_3m`, `portal_logowania_3m`, `portal_odslony_oferty_3m` | `portal_logowania_mies` z 3 pełnych miesięcy przed miesiącem migawki (od miesiąca wprowadzenia); brak wiersza = brak danych | 0,00 / 1,41 / 1,41 |
| budynek | `liczba_wind`, `windy_awarie_90d`, `windy_awarie_90d_na_winde` | `serwis_zgloszenia` z `typ_urzadzenia = 'winda'` i `kategoria = 'awaria'` w budynku lokalu, `utworzono` w oknie 90 dni | 0,00 |

Kolumny pomocnicze `czynsz`, `podobne_poziom`, `podobne_liczba` i `podobne_mediana_m2` są w tabeli, ale poza
`KOLUMNY_CECH` (`cechy.py`).

AUC pojedynczej cechy względem `odejdzie` (wszystkie umowy, braki pominięte; `linia_b2b` = 1 dla B2B):

| Cecha | AUC | Cecha | AUC |
|---|---:|---|---:|
| `linia_b2b` | 0,618 | `zgl_365d` | 0,516 |
| `miesiecy_umowy` | 0,537 | `zgl_otwarte_na_migawke` | 0,501 |
| `nr_okresu` | 0,418 | `ocena_srednia_365d` | 0,477 |
| `staz_dni` | 0,433 | `ocena_min_365d` | 0,476 |
| `indeksacja_ostatnia_pct` | 0,554 | `ocena_liczba_365d` | 0,508 |
| `czynsz_m2` | 0,562 | `ankieta_ostatni_wynik` | 0,479 |
| `czynsz_do_podobnych` | 0,487 | `ankieta_dni_od_odpowiedzi` | 0,456 |
| `plat_liczba_90d` | 0,494 | `ankieta_brak_wyniku` | 0,522 |
| `plat_spoznione_90d` | 0,502 | `ankiety_bez_odpowiedzi_365d` | 0,521 |
| `plat_zalegle_na_migawke` | 0,501 | `portal_miesiace_3m` | 0,493 |
| `plat_max_opoznienie_90d` | 0,502 | `portal_logowania_3m` | 0,526 |
| `plat_srednie_opoznienie_90d` | 0,502 | `portal_odslony_oferty_3m` | 0,525 |
| `zgl_90d` | 0,524 | `liczba_wind` | 0,497 |
| | | `windy_awarie_90d` | 0,513 |
| | | `windy_awarie_90d_na_winde` | 0,512 |

## Przecieki: wersja z przeciekiem wobec wersji na dzień migawki

AUC to wynik pojedynczej cechy względem `odejdzie` na wszystkich 19 231 umowach (braki pominięte). AUC < 0,5
oznacza, że wyższa wartość cechy idzie w parze z przedłużeniem.

### 1. `portal_logowania_mies`: tylko pełne miesiące przed migawką

Dlaczego:
- wiersz to suma za **cały** miesiąc kalendarzowy, a miesiąc migawki obejmuje średnio w 51,5% dni od migawki
  wzwyż;
- oferta przedłużenia (wiadomość `do_najemcy`, temat `przedłużenie`) przychodzi w dniu migawki (tabela niżej),
  więc odsłony oferty w miesiącu migawki są głównie reakcją na tę ofertę;
- w dniu migawki (gdy model ma liczyć listę) suma za bieżący miesiąc jeszcze nie istnieje, więc model uczony
  z nią dostawałby w użyciu inne dane niż przy uczeniu.

| Dni od migawki do wysłania oferty | Wiadomości |
|---:|---:|
| 0 | 18 212 |
| 1 | 92 |
| −1 | 91 |
| 2 | 73 |
| −2 | 72 |

| Wariant | Umowy z danymi | % z wartością > 0 | % odejść, gdy > 0 | % odejść, gdy 0 | AUC |
|---|---:|---:|---:|---:|---:|
| **Odsłony oferty, 3 pełne miesiące przed miesiącem migawki (używamy)** | 18 960 | 38,44 | 41,95 | 37,53 | 0,525 |
| Odsłony oferty, 3 miesiące kończące się miesiącem migawki | 19 221 | 70,05 | 40,43 | 36,73 | 0,541 |
| Odsłony oferty, sam miesiąc migawki | 19 221 | 55,60 | 41,45 | 36,65 | 0,535 |
| **Logowania, 3 pełne miesiące (używamy)** | 18 960 | 97,60 | 39,30 | 34,03 | 0,526 |
| Logowania, 3 miesiące kończące się miesiącem migawki | 19 221 | 99,00 | 39,41 | 30,60 | 0,526 |

### 2. `czynsz_katalogowy`: cennik z dnia eksportu, nie z dnia migawki

`pms_lokale.czynsz_katalogowy` ma jedną wartość, z 2026-09-30. Czynsz umów z wcześniejszych lat wygląda względem
niego na coraz tańszy, im starsza migawka. Zamiast tego porównujemy czynsz z nowymi umowami podobnych lokali sprzed
migawki (rodzina `umowa`).

| Rok migawki | Umowy | Mediana czynsz / `czynsz_katalogowy` własnego lokalu | Mediana `czynsz_do_podobnych` |
|---:|---:|---:|---:|
| 2022 | 10 | 0,834 | 0,966 |
| 2023 | 4 341 | 0,858 | 1,000 |
| 2024 | 5 591 | 0,893 | 1,000 |
| 2025 | 5 946 | 0,926 | 0,993 |
| 2026 | 3 343 | 0,950 | 0,992 |

| Cecha | AUC dla `odejdzie` | AUC dla „rok migawki ≥ 2025” |
|---|---:|---:|
| czynsz / `czynsz_katalogowy` (przeciek) | 0,458 | 0,873 |
| **`czynsz_do_podobnych` (używamy)** | 0,487 | 0,473 |

### 3. Pozostałe pola ze stanem na dzień eksportu albo z przyszłości

| Pole | Wersja z przeciekiem | Wersja na dzień migawki | Różnica |
|---|---|---|---|
| `pms_platnosci.dni_opoznienia` | końcowe opóźnienie płatności z terminem w oknie | opóźnienie znane w dniu migawki | 550 z 19 231 umów ma inną wartość maksimum; 802 umowy mają w dniu migawki zaległość; AUC 0,502 w obu wersjach |
| `portal_zgloszenia.status` | `status = 'otwarte'` (stan na eksport) | `zamknieto` ≥ migawka albo NULL | status: 0 umów z otwartym zgłoszeniem (AUC 0,500); na migawkę: 275 (AUC 0,501) |
| `ankiety_satysfakcji` | ostatnia odpowiedź w najmie do dnia eksportu | ASOF: ostatnia odpowiedź przed migawką | 6 853 umowy z inną wartością; AUC 0,502 do eksportu, 0,479 na migawkę |
| `portal_wiadomosci` (`przedłużenie`) | — | nie używamy | oferta przychodzi w dniu migawki (tabela w p. 1) |
| `pms_najmy.wypowiedzenie_data` | — | nie jest cechą | wypowiedzenie prawie przesądza wynik ([target_najemcy.md](target_najemcy.md)); flaga zostaje w `migawki_najemcy` |
| `retencja_decyzje` | — | nie używamy | `data_oferty` przypada 15 dni po migawce (wszystkie 5 886 ofert); grupa i oferta to decyzja po migawce |

Kontrole w kodzie: `wykluczone.py` (`ZAKAZANE_W_SQL`) odrzuca plik SQL rodziny, który poza komentarzami czyta
`odejdzie`, kolumny wyniku z `migawki_najemcy`, `wypowiedzenie_*`, `czynsz_katalogowy`, `status`, `pms_najemcy`,
`retencja_decyzje`, `rok_urodzenia` lub `jezyk_kontaktu`. Test `test_zdarzenia_po_migawce_nie_zmieniaja_cech`
dopisuje zdarzenia w dniu migawki i później (płatność, zgłoszenie, ankieta, logowania, awaria windy) i sprawdza,
że cechy się nie zmieniają.

### 4. Ryzyka, których nie da się sprawdzić w danych

- **Data wystawienia oceny obsługi** (`portal_zgloszenia.ocena_obslugi`): brak w danych. Przyjmujemy, że ocena
  powstaje przy zamknięciu zgłoszenia, i liczymy tylko zgłoszenia zamknięte przed migawką. Jeśli najemcy oceniają
  później, część ocen mogła powstać po migawce.
- **Kategoria zgłoszenia serwisowego** (`serwis_zgloszenia.kategoria = 'awaria'`): brak historii zmian. Jeśli
  koordynator zmienia kategorię po zamknięciu, w dniu migawki mogła być inna.
- **Logowania B2B** są na poziomie najemcy, czyli całej firmy (wszystkich jej lokali), a nie jednego lokalu.
- **Początek danych:** dane zdarzeniowe zaczynają się 2023-01-01. U 874 umów okno 90 dni, a u 4 351 umów okno
  365 dni zaczyna się wcześniej, więc liczniki są tam zaniżone. Najwcześniejsza migawka to 2022-12-31.

## SQL i kod

- Rodziny: `api/api/ai/features/najemcy/sql/umowa.sql`, `platnosci.sql`, `relacja.sql`, `budynek.sql`
  (wejście: `migawki_najemcy`; opis każdej cechy w komentarzu na początku pliku).
- Złączenie i zapis tabeli: `api/api/ai/features/najemcy/cechy.py` (`zbuduj_cechy`, `zbuduj_tabele_cech`);
  budowa `cd api && poetry run python -m api.ai.features.najemcy.cechy` (wynik: `cechy_najemcy: 19 231 wierszy`),
  także krok `pypyr baza` po `migawki_najemcy`.
- Pola wykluczone: `api/api/ai/features/najemcy/wykluczone.yaml`, `wykluczone.py`.
- Tabele przecieków: `cd api && poetry run python -m api.ai.features.najemcy.przecieki`
  (`api/api/ai/features/najemcy/przecieki.py`, SQL każdej tabeli w stałych `SQL_*`).
- Testy: `cd api && poetry run pytest tests/test_cechy_najemcy.py` (19 testów na danych syntetycznych:
  granice okien, ASOF, pełne miesiące, zdarzenia po migawce, pola zakazane).

Braki w tabeli cech:

```sql
SELECT column_name, null_percentage, min, max, round(TRY_CAST(avg AS DOUBLE), 2)
FROM (SUMMARIZE cechy_najemcy) WHERE column_name <> 'id_umowy';
```

Najważniejsze zapytania z `przecieki.py`:

```sql
-- Oferta przedłużenia względem dnia migawki
SELECT date_diff('day', m.data_migawki, w.data_czas::DATE) AS dni_od_migawki, count(*) AS wiadomosci
FROM migawki_najemcy AS m
JOIN portal_wiadomosci AS w
    ON w.id_najemcy = m.id_najemcy AND w.kierunek = 'do_najemcy' AND w.temat = 'przedłużenie'
   AND w.data_czas >= m.data_migawki - INTERVAL 30 DAY AND w.data_czas < m.data_do + INTERVAL 1 DAY
GROUP BY 1 ORDER BY 2 DESC LIMIT 5;

-- Udział dni miesiąca migawki od dnia migawki wzwyż
WITH m AS (
    SELECT data_migawki, date_trunc('month', data_migawki)::DATE AS poczatek,
           (date_trunc('month', data_migawki) + INTERVAL 1 MONTH)::DATE AS koniec
    FROM migawki_najemcy
)
SELECT round(100 * avg(date_diff('day', data_migawki, koniec) / date_diff('day', poczatek, koniec)), 1) FROM m;

-- Odsłony oferty: pełne miesiące wobec miesięcy z miesiącem migawki
WITH m AS (
    SELECT mg.id_umowy, mg.id_najemcy, mg.odejdzie, date_trunc('month', mg.data_migawki) AS mies_m,
           date_trunc('month', n.data_wprowadzenia)::DATE AS mies_wpr
    FROM migawki_najemcy AS mg JOIN pms_najmy AS n USING (id_najmu)
),
l AS (SELECT id_najemcy, strptime(miesiac, '%Y-%m')::DATE AS mies, liczba_logowan, odslony_oferty_przedluzenia
      FROM portal_logowania_mies)
SELECT m.id_umowy, m.odejdzie,
       sum(l.odslony_oferty_przedluzenia) FILTER (WHERE l.mies >= m.mies_m - INTERVAL 3 MONTH AND l.mies < m.mies_m)
           AS odslony_pelne_3m,
       sum(l.odslony_oferty_przedluzenia) FILTER (WHERE l.mies > m.mies_m - INTERVAL 3 MONTH AND l.mies <= m.mies_m)
           AS odslony_z_miesiacem_migawki_3m
FROM m LEFT JOIN l ON l.id_najemcy = m.id_najemcy AND l.mies >= m.mies_wpr
GROUP BY ALL;

-- Czynsz względem katalogu (stan na eksport) i względem nowych umów sprzed migawki
SELECT year(m.data_migawki) AS rok_migawki, count(*) AS umowy,
       round(median(c.czynsz / l.czynsz_katalogowy), 3) AS med_czynsz_do_katalogu,
       round(median(c.czynsz_do_podobnych), 3) AS med_czynsz_do_podobnych
FROM migawki_najemcy AS m
JOIN cechy_najemcy AS c USING (id_umowy)
JOIN pms_lokale AS l USING (id_lokalu)
GROUP BY 1 ORDER BY 1;

-- Oferta z retencja_decyzje względem dnia migawki
SELECT date_diff('day', m.data_migawki, r.data_oferty::DATE) AS dni_od_migawki, count(*) AS oferty
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE r.data_oferty IS NOT NULL GROUP BY 1 ORDER BY 1;

-- Okna sprzed początku danych zdarzeniowych
SELECT count(*) FILTER (WHERE data_migawki - 90 < DATE '2023-01-01'),
       count(*) FILTER (WHERE data_migawki - 365 < DATE '2023-01-01'), count(*)
FROM migawki_najemcy;
```

AUC w Pythonie: `sklearn.metrics.roc_auc_score(odejdzie, cecha)` na wierszach bez braku (`przecieki.auc`).
