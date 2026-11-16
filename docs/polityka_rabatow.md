# Polityka rabatów retencyjnych: komu opłaca się dać rabat (rekomendacja dla Joanny Michalak)

Stan: 2026-11-16. Liczy [`retention_bc/polityka_rabatow.py`](../api/api/contexts_boundaries/retention_bc/polityka_rabatow.py).
Wyniki są w `api/api/contexts_boundaries/retention_bc/wyniki/polityka_rabatow.json`, a wartość oczekiwana oferty dla
każdej umowy zbioru oceny w `wyniki/ev_najemcow.parquet`. Założenia ekonomiczne są w
[`retention_bc/zalozenia.yaml`](../api/api/contexts_boundaries/retention_bc/zalozenia.yaml).

## Wnioski i rekomendacja

1. **Przy rabacie 1 800 zł rocznie żadna z trzech polityk się nie opłaca.** W przeliczeniu na rok (5 985 kończących
   się umów) rabat dla wszystkich daje stratę 5,67 mln zł. Obecna reguła „górne 35% ryzyka” traci 0,91 mln zł, a
   „górne 20% upliftu” 1,04 mln zł. Każda z tych liczb oznacza stratę w porównaniu z brakiem ofert.
2. **Powód: rabat dostają głównie ci, którzy przedłużyliby i bez niego.** W obecnej regule na jedno dodatkowe
   przedłużenie przypada mniej więcej 4,6 wypłaconego rabatu. Jedno dodatkowe przedłużenie kosztuje więc około
   8 865 zł, a odejście najemcy kosztuje nas 4 920 zł.
3. **Wynik jest pewny co do kierunku.** Na całym losowym teście 2025 (4 734 umowy, bez modelu) obecna reguła też
   traci: 0,44 mln zł rocznie (95% przedział od 0,02 do 0,85 mln). Strata rośnie, jeśli liczyć rabat tak, jak
   księguje go FK (1 950 zł zamiast 1 800 zł).
4. **Model uplift nie ratuje rabatu w tej wysokości.** Polityka „górne 20% upliftu” nie jest lepsza od obecnej
   reguły: różnica wynosi od −0,96 do +0,75 mln zł rocznie. Model przy tym przeszacowuje efekt: przewiduje 266
   dodatkowych przedłużeń rocznie, a z eksperymentu wychodzi 136.
5. **Rekomendacja dla Joanny:** nie dawać rabatu 150 zł miesięcznie (1 800 zł rocznie) jako standardowej oferty,
   także w grupie górnych 35% ryzyka. Według danych oszczędza to 0,44–0,91 mln zł rocznie wobec obecnej reguły.
   Jeśli oferta retencyjna ma zostać, warto przetestować losowo mniejszy rabat w grupie górnych 35% ryzyka.
   Wychodzi ona na zero przy rabacie około 944–1 378 zł rocznie (79–115 zł miesięcznie), **pod warunkiem**, że
   mniejszy rabat zatrzyma tylu najemców co obecny. Tego dane nie pokazują, bo testowaliśmy tylko 150 zł miesięcznie.

## Wyniki

### Założenia (podane przez użytkownika, `retention_bc/zalozenia.yaml`)

| Symbol | Wartość | Co oznacza | Źródło | Odpowiedzialny |
|---|---:|---|---|---|
| R | 4 920 zł | koszt odejścia najemcy (wartość jednego dodatkowego przedłużenia) | FinKs i PMS 2025 | Monika Lis |
| D | 1 800 zł | roczny rabat dla każdego, kto przedłuży z ofertą | FinKs | Joanna Michalak |
| k | 60 zł | koszt kontaktu (wysłania jednej oferty) | szacunek | Joanna Michalak |

Wartość oczekiwana oferty dla najemcy: **EV = uplift × R − D × P(przedłuży | oferta) − k**. Uplift to różnica szansy
przedłużenia z ofertą i bez niej, a P(przedłuży | oferta) to szansa przedłużenia z ofertą. Obie wartości pochodzą
z modelu `v3_uplift_tlearner` ([churn_model/evals/uplift.md](../api/api/ai/churn_model/evals/uplift.md)).

### Jak liczymy

- **Zbiór oceny:** 1 413 umów z losowego testu oferty `test_2025` (końce umów 2025-07 – 2026-03). To ta sama część
  testowa (30% według `id_umowy`), której model nie widział przy uczeniu. Ofertę dostało 710 umów, 703 były
  w kontroli.
- **Polityki:**
  - rabat dla wszystkich;
  - **górne 35% ryzyka:** `score_polityki` ≥ 0,5182, czyli kwantyl 0,65 z części treningowej. Tak działa dziś
    firma;
  - **górne 20% upliftu:** 283 umowy z najwyższym upliftem v3;
  - dodatkowo **EV > 0:** tylko umowy, dla których wzór daje zysk.
- **Wynik polityki z eksperymentu** (liczby główne): oferta była przydzielana losowo, więc w umowach objętych
  polityką porównujemy % przedłużeń z ofertą i bez niej. Liczymy:
  - dodatkowe przedłużenia = (różnica odsetków) × liczba ofert;
  - wypłacone rabaty = % przedłużeń z ofertą × liczba ofert;
  - zysk netto = dodatkowe × R − rabaty × D − oferty × k, w porównaniu z brakiem ofert.

  Dla porównania podajemy też, ile obiecuje model, czyli sumę EV.
- **Rok:** wynik ze zbioru oceny × 5 985 / 1 413 = × 4,236. Liczba 5 985 to umowy roczne B2C / B2B z końcem
  2025-10-01 – 2026-09-30, czyli ostatnie 12 miesięcy danych.
- **95% przedziały:** bootstrap umów zbioru oceny, 2 000 losowań (te same dla wszystkich polityk), przeliczony na rok.

### Porównanie polityk w przeliczeniu na rok (5 985 kończących się umów)

| Polityka | Oferty | Dodatkowe przedłużenia | Wypłacone rabaty (liczba) | Koszt rabatów | Wartość dodatkowych przedłużeń (× R) | Koszt kontaktów | **Zysk netto** | 95% przedział zysku | Zysk na ofertę |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rabat dla wszystkich | 5 985 | 328 | 3 844 | 6,92 mln zł | 1,61 mln zł | 0,36 mln zł | **−5,67 mln zł** | −6,91 – −4,47 mln | −947 zł |
| Górne 35% ryzyka (obecna reguła) | 2 181 | 230 | 1 061 | 1,91 mln zł | 1,13 mln zł | 0,13 mln zł | **−0,91 mln zł** | −1,72 – −0,15 mln | −416 zł |
| Górne 20% upliftu (v3) | 1 199 | 136 | 909 | 1,64 mln zł | 0,67 mln zł | 0,07 mln zł | **−1,04 mln zł** | −1,59 – −0,48 mln | −866 zł |
| Tylko EV > 0 (dodatkowo) | 127 | 0 | 68 | 0,12 mln zł | 0,00 mln zł | 0,01 mln zł | **−0,13 mln zł** | −0,33 – +0,07 mln | −1 020 zł |
| Bez ofert (punkt zero) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |

| Polityka | Dodatkowe przedłużenia (95%) | Zysk względem obecnej reguły (95%) | Odsetek losowań bootstrapu ze stratą | Koszt jednego dodatkowego przedłużenia | Rabat roczny, przy którym wychodzi na zero | Model obiecuje: dodatkowe / zysk |
|---|---:|---:|---:|---:|---:|---:|
| Rabat dla wszystkich | 24 – 624 | −5,74 – −3,74 mln zł | 100,0% | 22 202 zł | 326 zł | 289 / −5,70 mln zł |
| Górne 35% ryzyka (obecna reguła) | 30 – 414 | 0 | 99,3% | 8 865 zł | 944 zł | 102 / −1,96 mln zł |
| Górne 20% upliftu (v3) | 12 – 265 | −0,96 – +0,75 mln zł | 100,0% | 12 538 zł | 658 zł | 266 / −0,42 mln zł |
| Tylko EV > 0 (dodatkowo) | −47 – +49 | +0,03 – +1,62 mln zł | 89,9% | — (brak dodatkowych) | — | 36 / +0,02 mln zł |

- **Koszt jednego dodatkowego przedłużenia** = (rabaty × D + oferty × k) / dodatkowe przedłużenia. Polityka się
  opłaca, gdy ten koszt jest niższy od R = 4 920 zł.
- **Rabat roczny „na zero”** = (dodatkowe × R − oferty × k) / rabaty, przy założeniu, że mniejszy rabat zatrzyma tylu
  najemców co obecny. **Tego dane nie sprawdzają.**
- „Tylko EV > 0” to 30 umów w zbiorze oceny (15 z ofertą, 15 w kontroli). Wynik jest przypadkowy, a jedyna różnica
  wobec obecnej reguły polega na tym, że ta polityka prawie nikomu nie daje rabatu.

### Wyniki na zbiorze oceny (przed przeliczeniem na rok)

| Polityka | Umowy | Z ofertą / w kontroli | % przedłużeń z ofertą | % przedłużeń bez oferty | Różnica (p.p.) | Dodatkowe przedłużenia | Rabaty | Zysk netto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rabat dla wszystkich | 1 413 | 710 / 703 | 64,2 | 58,7 | 5,5 | 77,4 | 907,5 | −1 337 520 zł |
| Górne 35% ryzyka | 515 | 255 / 260 | 48,6 | 38,1 | 10,6 | 54,3 | 250,4 | −214 347 zł |
| Górne 20% upliftu (v3) | 283 | 145 / 138 | 75,9 | 64,5 | 11,4 | 32,2 | 214,7 | −245 120 zł |
| Tylko EV > 0 | 30 | 15 / 15 | 53,3 | 53,3 | 0,0 | 0,0 | 16,0 | −30 600 zł |

„Górne 20% upliftu” wybiera najemców, którzy i bez oferty często przedłużają (64,5%). Rabat trafia więc do 75,9%
z nich, a dodatkowych przedłużeń jest niewiele więcej niż w obecnej regule.

### Sprawdzenie na całym teście 2025 (4 734 umowy, polityki bez modelu)

Polityki, które nie potrzebują modelu, można ocenić na całym losowym teście, czyli na ponad trzy razy większej
próbie. Przeliczenie na rok: × 5 985 / 4 734 = × 1,264.

| Polityka | Oferty na rok | Różnica % przedłużeń (p.p.) | Dodatkowe przedłużenia | Rabaty | **Zysk netto na rok** | 95% przedział | Rabat roczny „na zero” |
|---|---:|---:|---:|---:|---:|---:|---:|
| Rabat dla wszystkich | 5 985 | 5,2 | 312 | 3 778 | **−5,62 mln zł** | −6,32 – −4,90 mln | 311 zł |
| Górne 35% ryzyka (obecna reguła) | 2 121 | 15,1 | 321 | 1 052 | **−0,44 mln zł** | −0,85 – −0,02 mln | 1 378 zł |

Na większej próbie rabat w górnych 35% działa mocniej niż na zbiorze oceny (+15,1 wobec +10,6 p.p.). Mimo to
reguła traci pieniądze przy D = 1 800 zł.

### Wartość oczekiwana oferty dla najemców (model v3, zbiór oceny)

| Miara | Wartość |
|---|---:|
| Średnie EV na umowę | −952 zł |
| Mediana EV | −897 zł |
| 90. percentyl EV | −339 zł |
| Największe EV | +585 zł |
| Umowy z EV > 0 | 30 z 1 413 |
| Uplift potrzebny, żeby EV = 0 przy medianie P(przedłuży \| oferta) | 26,0 p.p. |

Model jest dobrze skalibrowany co do poziomu przedłużeń. Średnie P(przedłuży | oferta) w grupie z ofertą wynosi
0,626, a faktycznie przedłużyło 0,642. Średnie P(przedłuży | bez oferty) w kontroli wynosi 0,578 wobec faktycznych
0,587. Przeszacowuje jednak różnice między najemcami (uplift w czołówce; patrz punkt 4 wniosków).

### Wrażliwość: rabat tak, jak księguje go FK

`fk_rabaty` księguje 150 zł za każdy miesiąc kalendarzowy nowej umowy, także niepełny. Z 507 przedłużeń z ofertą
z końcem umowy 2025-07 – 2025-09 (tylko dla nich pełny rok widać w danych) 485 ma 13 pozycji, czyli 1 950 zł.

| Polityka (rok) | Zysk netto, D = 1 800 zł | Zysk netto, D = 1 950 zł |
|---|---:|---:|
| Rabat dla wszystkich | −5,67 mln zł | −6,24 mln zł |
| Górne 35% ryzyka | −0,91 mln zł | −1,07 mln zł |
| Górne 20% upliftu (v3) | −1,04 mln zł | −1,17 mln zł |
| Tylko EV > 0 | −0,13 mln zł | −0,14 mln zł |

### Czego te liczby nie obejmują

- Wartość odejścia R = 4 920 zł to jedna liczba dla wszystkich najemców (założenie użytkownika). Jeśli odejście
  B2B kosztuje więcej, wynik dla B2B może być inny; danych do rozbicia R nie ma (brak w danych).
- Rabat liczymy na jeden rok nowej umowy. Nie liczymy, czy najemca zatrzymany rabatem zostaje dłużej niż rok ani czy
  po roku znów oczekuje rabatu.
- Mniejszego rabatu nie testowaliśmy. Progi „na zero” są więc tylko punktem wyjścia do testu, a nie prognozą.

## SQL i kod

Uruchomienie (wymaga `domilo.duckdb` z `pypyr baza` i modelu v3 z `python -m api.ai.churn_model.evals.uplift`):

```bash
cd api && poetry run python -m api.contexts_boundaries.retention_bc.polityka_rabatow
cd api && poetry run pytest -q tests/test_retention_polityka.py
```

Liczba umów rocznie (podstawa przeliczenia na rok, 5 985):

```sql
SELECT count(*) AS umowy, min(data_do) AS od, max(data_do) AS do_
FROM migawki_najemcy
WHERE data_do BETWEEN DATE '2025-10-01' AND DATE '2026-09-30';
```

Rabat w FK (wrażliwość D = 1 950 zł: 507 przedłużeń, 485 z 13 pozycjami, mediana i maksimum 1 950 zł):

```sql
WITH f AS (SELECT id_umowy, sum(kwota_rabatu) AS suma, count(*) AS pozycje FROM fk_rabaty GROUP BY id_umowy)
SELECT count(*) AS przedluzenia_z_rabatem, count(*) FILTER (WHERE f.pozycje = 13) AS z_13_pozycjami,
       median(f.suma) AS mediana_suma, max(f.suma) AS max_suma, max(f.pozycje) AS max_pozycji
FROM retencja_decyzje AS r
JOIN migawki_najemcy AS m USING (id_umowy)
JOIN f ON f.id_umowy = m.id_umowy_nastepnej
WHERE r.okres = 'test_2025' AND r.grupa = 'oferta' AND r.data_konca < DATE '2025-10-01';
```

Zbiór oceny i podział: `features/najemcy/zbior.py` (`wczytaj_zbior`, `podziel_uplift`; SQL w
[uplift.md](../api/api/ai/churn_model/evals/uplift.md)). Próg ryzyka:
`np.quantile(trening.score_polityki, 0.65)` = 0,5182.

Kod (`api/api/contexts_boundaries/retention_bc/`):

- `zalozenia.yaml`, `zalozenia.py`: R, D, k ze źródłem, datą i osobą odpowiedzialną (`zalozenia_oferty()` zgłasza
  błąd, gdy któregoś pola brakuje);
- `polityka_rabatow.py`:
  - `wartosc_oferty`: EV = uplift × R − D × P(przedłuży | oferta) − k;
  - `wynik_polityki`: wynik z eksperymentu (+ suma z modelu), koszt dodatkowego przedłużenia, rabat „na zero”;
  - `na_rok`, `bootstrap_polityk`, `maski_polityk` i `main`;
- testy: `api/tests/test_retention_polityka.py`: wzór EV, wynik polityki na małym przykładzie, pusta polityka,
  przeliczenie na rok, założenia z pliku.
