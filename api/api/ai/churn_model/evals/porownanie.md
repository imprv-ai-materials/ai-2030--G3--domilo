# Lista retencyjna najemców: porównanie wersji

Stan: 2026-11-16. Liczy [`ewaluacja_v1.py`](ewaluacja_v1.py). Wyniki są w `versions/v1_ryzyko/metryki.json`,
predykcje testu w `evals/wyniki/v1_ryzyko.parquet`, a runy w MLflow (eksperyment `najemcy`: `v1_ryzyko`,
`score_polityki`, `regula_b2b_potem_score`). Target i cechy:
[docs/target_najemcy.md](../../../../../docs/target_najemcy.md),
[docs/przecieki_najemcy.md](../../../../../docs/przecieki_najemcy.md).

## Wnioski

1. **v1_ryzyko nie jest lepszy od tego, co firma już ma.** Na całym teście (2 856 kończących się umów) trafia do
   górnych 10% listy 23,2% wszystkich odchodzących, a obecny score dostawcy (`score_polityki`) 16,7%. Cała ta
   przewaga bierze się jednak z tego, że model stawia na górze wyłącznie klientów firmowych (B2B), którzy odchodzą
   w 80,6%.
2. Prosta reguła „najpierw B2B, potem według `score_polityki`” daje to samo w górnych 10% (23,9%) i lepiej
   porządkuje całą listę (AUC 0,759 wobec 0,694 dla v1).
3. W obrębie jednej linii model jest gorszy od score dostawcy: u klientów prywatnych (B2C) AUC 0,569 wobec 0,672,
   a w górnych 10% łapie 13,7% odchodzących wobec 17,8%. Cechy z naszych danych (umowa, płatności, portal, windy)
   za słabo odróżniają odchodzących najemców prywatnych.
4. Dla Domilo: nie zastępujemy score dostawcy modelem v1. Jeśli lista ma się zmienić już teraz, to przez regułę
   „B2B najpierw” na score dostawcy, i to tylko wtedy, gdy oferta dla B2B ma sens biznesowy (prawie wszyscy B2B
   i tak odchodzą). `current.yaml` zostaje pusty.
5. Wynik zależy też od ofert: w teście 888 z 2 856 umów dostało ofertę według `score_polityki`, a oferta zmniejsza
   odejścia (losowy test 2025: −5,21 p.p., [target_najemcy.md](../../../../../docs/target_najemcy.md)). Ocena
   każdego rankingu na tym teście jest więc częściowo zaniżona tam, gdzie firma zadziałała.

## Podział i miary

| Zbiór | Umowy | Odejścia | Zakres |
|---|---:|---:|---|
| Trening | 14 903 | 5 931 | koniec umowy 2023-03 – 2025-12 |
| Test | 2 856 | 1 065 (37,3%) | koniec umowy 2026-04 – 2026-09, migawki 2026-01-31 – 2026-08-01 |
| Poza zbiorami | 1 472 | — | końce 2026-01 – 2026-03: przerwa, żeby wynik każdej umowy treningowej (najpóźniej 2025-12-31 + 30 dni na przeprowadzkę) był znany przed pierwszą migawką testu |

- **v1_ryzyko:** LightGBM na 28 cechach z dnia migawki (`features/najemcy/cechy.py`). Liczba drzew (131) pochodzi
  z wczesnego zatrzymania na migawkach treningu po 2025-05-01 (AUC walidacji 0,662). Potem model uczony jest od
  nowa na całym treningu. Parametry ustalono przed oceną; nie stroiliśmy ich na teście.
- **Punkt odniesienia:** `retencja_decyzje.score_polityki`, czyli score dostawcy, według którego firma daje oferty.
  Jest dla każdej umowy testowej.
- **Reguła kontrolna** `regula_b2b_potem_score`: najpierw B2B, w każdej linii według `score_polityki`. Nie jest
  modelem; pokazuje, ile daje samo ustawienie B2B na górze.
- **Miary:**
  - AUC;
  - recall w górnym decylu: odchodzący wśród 10% umów z najwyższym ryzykiem / wszyscy odchodzący;
  - precyzja w decylu i lift.

  Remis na granicy decyla liczymy jako wartość oczekiwaną losowej kolejności. W nawiasach 95% przedział
  z bootstrapu par (2 000 losowań, te same dla obu porównywanych rankingów).
- **Najwyższy możliwy recall w decylu** = k / odejścia: wszystkie 26,9%, bez wypowiedzenia 35,5%, B2C 34,5%,
  B2B 12,4%.

## Wyniki na teście

### Wszystkie umowy testu (2 856, 1 065 odejść, k = 286)

| Ranking | AUC | Recall w decylu | Precyzja w decylu | Lift | Udział B2B w decylu |
|---|---:|---:|---:|---:|---:|
| v1_ryzyko | 0,694 (0,672–0,714) | 23,2% (21,9–24,5) | 86,4% | 2,32 | 100,0% |
| **score_polityki (baseline)** | 0,682 (0,663–0,702) | 16,7% (15,2–18,1) | 62,2% | 1,67 | 26,2% |
| regula_b2b_potem_score | 0,759 (0,742–0,777) | 23,9% (22,6–25,3) | 89,2% | 2,39 | 100,0% |

### Bez wypowiedzenia złożonego przed migawką (2 493, 702 odejścia, k = 249)

| Ranking | AUC | Recall w decylu | Precyzja w decylu | Lift | Udział B2B w decylu |
|---|---:|---:|---:|---:|---:|
| v1_ryzyko | 0,692 (0,666–0,715) | 28,3% (26,3–30,2) | 79,9% | 2,84 | 100,0% |
| **score_polityki (baseline)** | 0,686 (0,663–0,708) | 18,2% (16,0–20,3) | 51,4% | 1,83 | 21,3% |
| regula_b2b_potem_score | 0,767 (0,746–0,787) | 29,1% (27,1–31,1) | 81,9% | 2,91 | 100,0% |

### Osobno w każdej linii

W jednej linii reguła kontrolna jest tym samym rankingiem co `score_polityki`.

| Linia | Umowy | Odejścia | k | Ranking | AUC | Recall w decylu | Precyzja w decylu |
|---|---:|---:|---:|---|---:|---:|---:|
| B2C | 2 397 | 695 (29,0%) | 240 | v1_ryzyko | 0,569 (0,544–0,593) | 13,7% (11,7–15,8) | 39,6% |
| B2C | | | | **score_polityki** | 0,672 (0,650–0,694) | 17,8% (15,4–19,5) | 51,7% |
| B2B | 459 | 370 (80,6%) | 46 | v1_ryzyko | 0,658 (0,596–0,723) | 11,4% (10,3–12,4) | 91,3% |
| B2B | | | | **score_polityki** | 0,716 (0,654–0,776) | 11,6% (10,5–12,4) | 93,5% |

### Okresy polityki ofert w teście (`retencja_decyzje.okres`)

| Okres | Umowy | Odejścia | Ranking | AUC | Recall w decylu |
|---|---:|---:|---|---:|---:|
| polityka_2026 (końce 2026-04 – 06) | 1 270 | 454 | v1_ryzyko | 0,683 (0,652–0,715) | 23,6% |
| | | | score_polityki | 0,681 (0,651–0,710) | 17,8% |
| | | | regula_b2b_potem_score | 0,760 (0,733–0,787) | 23,3% |
| kampania_2026q3 (końce 2026-07 – 09) | 1 586 | 611 | v1_ryzyko | 0,703 (0,677–0,731) | 22,7% |
| | | | score_polityki | 0,684 (0,658–0,711) | 15,9% |
| | | | regula_b2b_potem_score | 0,760 (0,736–0,783) | 24,5% |

### Różnice (95% CI z bootstrapu par)

| Segment | v1 − score_polityki: AUC | v1 − score_polityki: recall (p.p.) | v1 − reguła: AUC | v1 − reguła: recall (p.p.) |
|---|---|---|---|---|
| wszystkie | −0,017 … +0,039 (nierozstrzygnięta) | +4,7 … +8,4 | −0,086 … −0,045 | −1,9 … +0,4 (nierozstrzygnięta) |
| bez wypowiedzenia | −0,025 … +0,038 (nierozstrzygnięta) | +7,3 … +13,0 | −0,099 … −0,051 | −2,4 … +0,7 (nierozstrzygnięta) |
| B2C | −0,136 … −0,073 | −6,7 … −1,2 | jak obok | jak obok |
| B2B | −0,150 … +0,030 (nierozstrzygnięta) | −1,6 … +1,3 (nierozstrzygnięta) | jak obok | jak obok |
| polityka_2026 | −0,040 … +0,044 (nierozstrzygnięta) | +2,8 … +8,8 | −0,108 … −0,046 | −1,6 … +2,3 (nierozstrzygnięta) |
| kampania_2026q3 | −0,020 … +0,056 (nierozstrzygnięta) | +4,3 … +9,3 | −0,085 … −0,028 | −3,2 … −0,5 |

### Ważność cech v1 (udział w gain, 10 największych)

| Cecha | Udział |
|---|---:|
| linia | 40,8% |
| indeksacja_ostatnia_pct | 8,2% |
| czynsz_m2 | 7,9% |
| czynsz_do_podobnych | 7,5% |
| portal_logowania_3m | 5,3% |
| ankieta_dni_od_odpowiedzi | 3,1% |
| ocena_srednia_365d | 2,7% |
| nr_okresu | 2,4% |
| ankieta_ostatni_wynik | 2,4% |
| zgl_365d | 2,4% |

## Ograniczenia

- **Oferty zmieniają wynik.** W teście ofertę dostały umowy z wysokim `score_polityki` (888 z 2 856). Odejścia
  są przez to niższe dokładnie tam, gdzie baseline stawia najwyżej, więc jego miary mogą być zaniżone. v1 uczy się
  na latach, w których ta sama polityka działała. Czysta grupa kontrolna w teście (`kampania_2026q3`, `kontrola`)
  ma 111 umów, za mało na osobną ocenę.
- **Nie wiadomo, z czego liczony jest `score_polityki`** (brak w danych). Może zawierać informacje, których nie
  mamy w cechach, albo sprzed lub po dniu migawki.
- **Górny decyl v1 to same B2B.** Lista retencyjna złożona z samych firm nie musi być tą, której Domilo chce;
  wybór, komu dać ofertę, wymaga kosztu oferty i wartości utrzymania najemcy (założenia od użytkownika,
  `retention_bc/zalozenia.yaml` jest pusty).

## SQL i kod

- Kontrakt: `api/api/ai/churn_model/base.py` (`ModelNajemcow`, `KOLUMNY_WEJSCIA`, `KOLUMNY_ZAKAZANE`).
- Zbiór i podział: `api/api/ai/features/najemcy/zbior.py` (`SQL_MIGAWKI`, `podziel`).
- Model: `api/api/ai/churn_model/versions/v1_ryzyko/model.py`, zapisany `model.joblib`.
- Miary: `api/api/ai/churn_model/evals/metryki.py`.
- Uruchomienie (z `api/`, po `pypyr baza`): `poetry run python -m api.ai.churn_model.evals.ewaluacja_v1`
  (`--bez-mlflow` bez zapisu runów). Dwa przebiegi dają te same liczby (`deterministic`, `seed` 42).
- Testy: `poetry run pytest tests/test_churn_model.py`.

```sql
-- Wejście ewaluacji (zbior.SQL_MIGAWKI), złączone z cechy_najemcy po id_umowy
SELECT
    m.id_umowy, m.linia AS linia_umowy, m.data_do, m.data_migawki, m.miesiac_konca,
    m.wypowiedzenie_przed_migawka, m.odejdzie,
    r.score_polityki, r.okres, r.grupa
FROM migawki_najemcy AS m
LEFT JOIN retencja_decyzje AS r USING (id_umowy);

-- Wielkość zbiorów i pokrycie score_polityki
SELECT CASE WHEN miesiac_konca <= DATE '2025-12-01' THEN 'trening'
            WHEN miesiac_konca >= DATE '2026-04-01' THEN 'test' ELSE 'przerwa' END AS zbior,
       count(*), sum(odejdzie), count(r.id_umowy) AS z_score
FROM migawki_najemcy AS m LEFT JOIN retencja_decyzje AS r USING (id_umowy)
GROUP BY 1;

-- Oferty w teście
SELECT count(*) FILTER (WHERE r.grupa = 'oferta') AS oferty, count(*) AS n
FROM migawki_najemcy AS m JOIN retencja_decyzje AS r USING (id_umowy)
WHERE m.miesiac_konca BETWEEN DATE '2026-04-01' AND DATE '2026-09-01';
```

## v2_przezycie_cox: czas do końca najmu (2026-11-16)

Liczy [`ewaluacja_v2.py`](ewaluacja_v2.py); wyniki w `versions/v2_przezycie_cox/metryki.json`, predykcje testu
w `evals/wyniki/v2_przezycie_cox.parquet`, runy MLflow `v2_przezycie_cox` i `regula_b2b` (eksperyment `najemcy`).
Raport: [docs/przezycie_cox.md](../../../../../docs/przezycie_cox.md).

To inny kontrakt niż v1: jeden wiersz to okres umowy, cechy v1 liczone na jego początek, a target to czas do końca
najmu (model Coxa, lifelines). Wyniku nie da się więc porównać z AUC v1 na migawkach. Baseline to reguła
„B2B najpierw”, liczona na tym samym teście.

| Wynik | C-index, najmy od 2025-01, pierwszy okres (4 506) | C-index, wszystkie okresy tych najmów (5 396) |
|---|---:|---:|
| Reguła „B2B najpierw” (baseline) | 0,595 (0,574–0,615) | 0,599 (0,579–0,619) |
| Cox bez poprawek | 0,662 (0,638–0,690) | 0,655 (0,629–0,683) |
| **v2_przezycie_cox** | **0,664** (0,639–0,692) | **0,656** (0,629–0,685) |
| v2 tylko B2C / tylko B2B | 0,501 / 0,696 | 0,496 / 0,690 |

v2 − baseline: +0,069 (+0,042 … +0,100) na pierwszym okresie. Model jest lepszy od reguły dzięki porządkowaniu
B2B, ale wśród najemców prywatnych nie rozróżnia nikogo (C-index ≈ 0,5), podobnie jak v1 w B2C.
`current.yaml` zostaje pusty.

