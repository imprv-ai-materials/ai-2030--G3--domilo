# Losowy test rabatu `test_2025`: czy losowanie się udało i komu rabat zmienia decyzję

Stan: 2026-11-16. Wszystkie liczby liczy
[`api/api/ai/churn_model/evals/eksperyment_rabatu_2025.py`](../api/api/ai/churn_model/evals/eksperyment_rabatu_2025.py)
na `domilo.duckdb` i zapisuje w `api/api/ai/churn_model/evals/wyniki/eksperyment_rabatu_2025.json`. Testy:
`api/tests/test_eksperyment_rabatu_2025.py`.

## Wnioski

1. **Losowanie się udało, jeśli patrzeć na to, co wiedzieliśmy o najemcach przed ofertą.** Grupy z ofertą i bez niej
   mają prawie identyczne 10 najważniejszych cech modelu v1 i score dostawcy. Największa standaryzowana różnica to
   0,038, przy zwykle przyjmowanym progu 0,1, a test łączny daje p = 0,905. Podział 2 332 / 2 402 nie odbiega od
   50/50 (p = 0,316).
2. **Oferta (rabat 150 zł miesięcznie w nowej umowie) podnosi odsetek przedłużeń z 57,9% do 63,1%,** czyli o
   5,2 p.p. (95% przedział: od 2,4 do 8,0 p.p.).
3. **Cały ten efekt pochodzi z górnych 35% `score_polityki`.** Tam przedłużenia rosną o 15,5 p.p. (od 10,8 do
   20,2), czyli mniej więcej 15 dodatkowych przedłużeń na 100 ofert. W dolnych 65% różnica wynosi −0,3 p.p.
   (od −3,5 do +2,9), więc rabat nie zmienia tam decyzji. Mimo to dostało go 1 067 przedłużających się najemców,
   którzy przedłużyliby umowę i bez niego.
4. **Jest jedno zastrzeżenie.** W górnych 35% najemcy z grupy z ofertą rzadziej składali wypowiedzenie jeszcze przed
   dniem migawki: 15,3% wobec 23,1%, choć oferta przyszła dopiero 45 dni przed końcem umowy. W dolnych 65% takiej
   różnicy nie ma. Możliwe są dwa wyjaśnienia: najemcy wiedzieli o ofercie wcześniej, niż pokazuje `data_oferty`,
   albo przydział w tym segmencie nie był w pełni losowy. Bez umów z wcześniejszym wypowiedzeniem efekt w górnych 35%
   nadal wynosi +14,3 p.p. (od 9,0 do 19,6), więc wniosek się nie zmienia. Trzeba jednak sprawdzić to w zespole
   retencji.
5. **Co to znaczy dla Domilo:** rabat ma sens tylko w górnych 35% score, czyli dokładnie tam, gdzie wskazuje go
   obecna flaga `kwalifikuje`. W dolnych 65% to koszt bez efektu. U klientów firmowych (B2B) wzrostu przedłużeń
   w ogóle nie widać, ale tej analizy nie planowaliśmy przed testem, więc to wskazówka do kolejnego testu, nie
   decyzja.

## Wyniki

### Populacja i definicje

- **Umowy:** wszystkie 4 734 umowy z `retencja_decyzje.okres = 'test_2025'`, czyli końce umów od 2025-07-01 do
  2026-03-31. Każda ma swój wiersz w `migawki_najemcy` i `cechy_najemcy`; złączenie nie gubi żadnej umowy.
- **Wynik:** przedłużenie = 1 − `migawki_najemcy.odejdzie`, czyli najem ma kolejny okres umowy.
- **Efekt (ATE):** % przedłużeń w grupie z ofertą minus % w kontroli. To efekt *wysłania* oferty, a nie jej
  przyjęcia: ofertę otworzyło 61,5% najemców z grupy oferta. Przedział 95% to przedział Walda (rozkład normalny,
  wariancja liczona osobno w każdej grupie). Dla sprawdzenia podajemy też przedział z bootstrapu po najemcach
  (2 000 losowań), bo 122 najemców ma w teście więcej niż jedną umowę, np. ramową B2B.
- **10 cech v1:** 10 cech `v1_ryzyko` o największym gain (`versions/v1_ryzyko/metryki.json`), z wartościami na dzień
  migawki.
- **Górne 35%:** `score_polityki` ≥ 0,52149, czyli kwantyl 0,65 liczony w całym `test_2025`. Do tej grupy należy
  1 657 umów, a do dolnych 65% 3 077. Firmowa flaga `kwalifikuje` to w praktyce górne 35% liczone osobno w każdym
  miesiącu końca umowy: z 1 656 umowami z flagą pokrywa się w 1 631 przypadkach. Wyniki dla tej flagi są w tabeli
  wrażliwości.
- **Oferta:** w całym teście `data_oferty` = `data_konca` − 45 dni, czyli 15 dni po migawce (60 dni przed końcem).

### 1. Czy losowanie się udało

**Podział grup**

| Umowy | Oferta | Kontrola | Udział oferty | p (test dwumianowy, 50/50) |
|---:|---:|---:|---:|---:|
| 4 734 | 2 332 | 2 402 | 49,26% | 0,316 |

| Miesiąc końca | Oferta | Kontrola |
|---|---:|---:|
| 2025-07 | 260 | 289 |
| 2025-08 | 264 | 243 |
| 2025-09 | 290 | 259 |
| 2025-10 | 264 | 300 |
| 2025-11 | 273 | 303 |
| 2025-12 | 249 | 268 |
| 2026-01 | 256 | 281 |
| 2026-02 | 210 | 225 |
| 2026-03 | 266 | 234 |

Udział oferty nie zależy od miesiąca końca umowy (test χ² miesiąc × grupa: p = 0,180).

**10 cech v1 na dzień migawki**

SMD to różnica średnich podzielona przez wspólne odchylenie standardowe. Wartość |SMD| < 0,1 zwykle uznaje się za
dobry balans. Dla `linia` podajemy udział B2B i test dwóch proporcji, dla pozostałych cech test Welcha (bez braków).

| Cecha (miejsce w v1 według gain) | Oferta | Kontrola | SMD | Braki: oferta | Braki: kontrola | p |
|---|---:|---:|---:|---:|---:|---:|
| 1. linia (udział B2B) | 0,160 | 0,160 | −0,001 | 0,0% | 0,0% | 0,975 |
| 2. indeksacja_ostatnia_pct | 4,25 | 4,24 | 0,003 | 45,4% | 45,3% | 0,931 |
| 3. czynsz_m2 | 46,84 | 46,85 | −0,002 | 0,0% | 0,0% | 0,958 |
| 4. czynsz_do_podobnych | 0,997 | 0,994 | 0,028 | 0,6% | 0,8% | 0,335 |
| 5. portal_logowania_3m | 11,09 | 11,26 | −0,019 | 0,0% | 0,0% | 0,509 |
| 6. ankieta_dni_od_odpowiedzi | 242,62 | 249,34 | −0,028 | 55,5% | 55,7% | 0,527 |
| 7. ocena_srednia_365d | 3,42 | 3,43 | −0,008 | 47,8% | 49,2% | 0,846 |
| 8. nr_okresu | 1,97 | 1,94 | 0,027 | 0,0% | 0,0% | 0,350 |
| 9. ankieta_ostatni_wynik | 7,47 | 7,54 | −0,038 | 55,5% | 55,7% | 0,387 |
| 10. zgl_365d | 1,94 | 1,93 | 0,002 | 0,0% | 0,0% | 0,945 |
| score_polityki (poza 10 cechami) | 0,429 | 0,426 | 0,012 | 0,0% | 0,0% | 0,683 |
| wypowiedzenie_przed_migawka (poza 10 cechami) | 0,119 | 0,140 | −0,063 | 0,0% | 0,0% | 0,030 |

Test łączny sprawdza, czy 10 cech razem pozwala przewidzieć, kto dostał ofertę. To regresja logistyczna
`oferta ~ cechy` z brakami zastąpionymi średnią i wskaźnikami braku; dwie cechy ankiety mają ten sam wzór braków,
więc dostają jeden wskaźnik. Porównujemy ją z modelem pustym testem ilorazu wiarygodności: LR = 7,69, 14 stopni
swobody, **p = 0,905**. Cechy nie przewidują grupy.

**W segmentach score** (tam też liczymy efekt)

| Cecha | SMD: górne 35% | p | SMD: dolne 65% | p |
|---|---:|---:|---:|---:|
| linia (udział B2B) | 0,053 | 0,284 | −0,037 | 0,305 |
| indeksacja_ostatnia_pct | 0,044 | 0,538 | −0,015 | 0,744 |
| czynsz_m2 | 0,033 | 0,498 | −0,021 | 0,552 |
| czynsz_do_podobnych | −0,024 | 0,627 | 0,057 | 0,118 |
| portal_logowania_3m | −0,028 | 0,569 | −0,014 | 0,689 |
| ankieta_dni_od_odpowiedzi | −0,174 | 0,026 | 0,038 | 0,476 |
| ocena_srednia_365d | −0,005 | 0,936 | −0,008 | 0,879 |
| nr_okresu | −0,008 | 0,865 | 0,046 | 0,205 |
| ankieta_ostatni_wynik | −0,050 | 0,523 | −0,031 | 0,561 |
| zgl_365d | 0,016 | 0,747 | −0,006 | 0,862 |

| Segment | Umowy | Oferta | Kontrola | p (50/50) | Test łączny: LR (14 st. sw.) | p |
|---|---:|---:|---:|---:|---:|---:|
| górne 35% | 1 657 | 817 | 840 | 0,589 | 10,76 | 0,705 |
| dolne 65% | 3 077 | 1 515 | 1 562 | 0,407 | 7,15 | 0,929 |

Tylko jeden z 20 testów cech w segmentach ma p < 0,05: `ankieta_dni_od_odpowiedzi` w górnych 35%, liczona wyłącznie
dla umów z odpowiedzią na ankietę. Przy 20 testach mniej więcej jednego takiego wyniku należy się spodziewać
przypadkiem, a test łączny w segmencie tego nie potwierdza (p = 0,705).

**Wypowiedzenia złożone przed ofertą (zastrzeżenie z wniosku 4)**

| Segment | Wypowiedzenie przed migawką: oferta | kontrola | p | Wypowiedzenie przed ofertą: oferta | kontrola | p | Wśród odchodzących: z wypowiedzeniem przed ofertą, oferta | kontrola |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| wszystkie | 11,9% | 14,0% | 0,030 | 23,4% | 27,3% | 0,0020 | 63,3% | 64,5% |
| górne 35% | 15,3% | 23,1% | < 0,0001 | 32,9% | 41,9% | 0,0002 | 64,9% | 63,2% |
| dolne 65% | 10,0% | 9,1% | 0,375 | 18,3% | 19,5% | 0,404 | 61,7% | 66,0% |

Wypowiedzenia złożone przed ofertą są rzadsze w grupie z ofertą tylko w górnych 35%, czyli tam, gdzie oferta działa.
Wśród odchodzących odsetek osób z wczesnym wypowiedzeniem jest w obu grupach podobny (64,9% i 63,2%). Tak by to
wyglądało, gdyby oferta zmieniała decyzję o odejściu, zanim najemca złożył wypowiedzenie, czyli gdyby najemcy znali
ofertę wcześniej niż `data_oferty`. Tak samo mogłoby jednak wyglądać nieczyste losowanie w tym segmencie, np.
przenoszenie do kontroli osób, które już złożyły wypowiedzenie. Same dane tego nie rozstrzygają (pytanie na końcu).

### 2. Efekt oferty na przedłużenia

| Segment | Score | Umowy: oferta | Umowy: kontrola | % przedłużeń: oferta | % przedłużeń: kontrola | ATE (p.p.) | 95% przedział | 95% bootstrap po najemcach | p | % ofert otwartych |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wszystkie | 0,0063 – 0,9787 | 2 332 | 2 402 | 63,1 | 57,9 | **+5,2** | +2,4 – +8,0 | +2,3 – +8,0 | 0,0002 | 61,5 |
| górne 35% | 0,5216 – 0,9787 | 817 | 840 | 49,4 | 33,9 | **+15,5** | +10,8 – +20,2 | +10,8 – +20,1 | < 0,0001 | 63,3 |
| dolne 65% | 0,0063 – 0,5214 | 1 515 | 1 562 | 70,5 | 70,8 | **−0,3** | −3,5 – +2,9 | −3,5 – +2,8 | 0,849 | 60,5 |

**Różnica efektów, górne 35% minus dolne 65%: +15,8 p.p. (95%: od +10,1 do +21,5; p < 0,0001).** Segmenty są
rozłączne, więc wariancje się sumują.

**Komu rabat faktycznie wypłacono** (`fk_rabaty` dla następnej umowy przedłużającego się najemcy)

| Segment | Przedłużenia: oferta | z rabatem | Kwota rabatu (zł / mies.) | Przedłużenia: kontrola | z rabatem |
|---|---:|---:|---:|---:|---:|
| wszystkie | 1 472 | 1 468 | 150 | 1 391 | 0 |
| górne 35% | 404 | 401 | 150 | 285 | 0 |
| dolne 65% | 1 068 | 1 067 | 150 | 1 106 | 0 |

### 3. Sprawdzenia wrażliwości

| Segment | ATE: wszyscy (95%) | Bez wypowiedzenia przed migawką: umowy oferta / kontrola | % przedłużeń: oferta | % przedłużeń: kontrola | ATE (95%) | ATE ważony warstwami wypowiedzenia (95%) |
|---|---:|---:|---:|---:|---:|---:|
| wszystkie | +5,2 (+2,4 – +8,0) | 2 055 / 2 066 | 71,6 | 67,2 | +4,4 (+1,5 – +7,2) | +3,8 (+1,3 – +6,2) |
| górne 35% | +15,5 (+10,8 – +20,2) | 692 / 646 | 58,2 | 44,0 | +14,3 (+9,0 – +19,6) | +11,6 (+7,3 – +15,9) |
| dolne 65% | −0,3 (−3,5 – +2,9) | 1 363 / 1 420 | 78,4 | 77,8 | +0,5 (−2,5 – +3,6) | +0,4 (−2,4 – +3,2) |

Jeśli wczesne wypowiedzenie jest już skutkiem oferty, wyłączenie tych umów albo ważenie po nich zaniża efekt. Jeśli
jest skutkiem nieczystego losowania, oba sprawdzenia dają wynik bliższy prawdy. Zakres od +11,6 do +15,5 p.p.
w górnych 35% obejmuje oba scenariusze. W każdym z nich efekt jest wyraźnie dodatni, a w dolnych 65% bliski zera.

**Podział według flagi firmy `kwalifikuje`** (górne 35% w każdym miesiącu) zamiast progu z całego okresu:

| Segment | Score | Umowy: oferta | Umowy: kontrola | % przedłużeń: oferta | % przedłużeń: kontrola | ATE (p.p.) | 95% przedział | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| kwalifikuje | 0,4867 – 0,9787 | 820 | 836 | 49,5 | 33,4 | +16,1 | +11,5 – +20,8 | < 0,0001 |
| nie kwalifikuje | 0,0063 – 0,5333 | 1 512 | 1 566 | 70,5 | 71,0 | −0,5 | −3,7 – +2,7 | 0,758 |

Różnica: +16,6 p.p. (od +11,0 do +22,3).

**Analiza dodatkowa (nieplanowana przed testem): linie B2C / B2B**

| Segment | Umowy: oferta | Umowy: kontrola | % przedłużeń: oferta | % przedłużeń: kontrola | ATE (p.p.) | 95% przedział | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| B2C | 1 959 | 2 017 | 71,0 | 64,2 | +6,8 | +3,8 – +9,7 | < 0,0001 |
| B2B | 373 | 385 | 22,0 | 24,9 | −3,0 | −9,0 – +3,1 | 0,337 |
| B2C, górne 35% | 628 | 664 | 60,4 | 40,2 | +20,1 | +14,8 – +25,5 | < 0,0001 |
| B2C, dolne 65% | 1 331 | 1 353 | 76,0 | 76,0 | 0,0 | −3,3 – +3,2 | 0,990 |
| B2B, górne 35% | 189 | 176 | 13,2 | 10,2 | +3,0 | −3,6 – +9,6 | 0,372 |
| B2B, dolne 65% | 184 | 209 | 31,0 | 37,3 | −6,3 | −15,7 – +3,0 | 0,184 |

Różnica B2C − B2B: +9,7 p.p. (od +3,0 do +16,4). Umów B2B jest w teście niewiele (758), więc przedziały są szerokie.

## SQL i kod

Uruchomienie (wymaga `domilo.duckdb` z tabelami `migawki_najemcy` i `cechy_najemcy`, czyli `pypyr baza`):

```bash
cd api && poetry run python -m api.ai.churn_model.evals.eksperyment_rabatu_2025
cd api && poetry run pytest -q tests/test_eksperyment_rabatu_2025.py
```

Zbiór analizy (`sql_testu` w skrypcie; 10 cech czyta z `versions/v1_ryzyko/metryki.json`, pole `waznosc_cech[:10]`):

```sql
SELECT r.id_umowy, r.data_konca, r.score_polityki, r.kwalifikuje, r.grupa, r.data_oferty, r.czy_otwarta,
       m.id_najemcy, m.id_umowy_ramowej, m.linia, m.wypowiedzenie_przed_migawka,
       coalesce(m.wypowiedzenie_data < m.data_do - INTERVAL 45 DAY, false) AS wypowiedzenie_przed_oferta,
       m.odejdzie, 1 - m.odejdzie AS przedluzona,
       f.id_umowy IS NOT NULL AS rabat_w_nastepnej, f.kwota_rabatu,
       c.indeksacja_ostatnia_pct, c.czynsz_m2, c.czynsz_do_podobnych, c.portal_logowania_3m,
       c.ankieta_dni_od_odpowiedzi, c.ocena_srednia_365d, c.nr_okresu, c.ankieta_ostatni_wynik, c.zgl_365d
FROM retencja_decyzje AS r
JOIN migawki_najemcy AS m USING (id_umowy)
JOIN cechy_najemcy AS c USING (id_umowy)
LEFT JOIN (SELECT id_umowy, max(kwota_rabatu) AS kwota_rabatu FROM fk_rabaty GROUP BY id_umowy) AS f
    ON f.id_umowy = m.id_umowy_nastepnej
WHERE r.okres = 'test_2025';
```

Sprawdzenia z SQL (uruchamiane przez `polacz()` przy analizie danych):

```sql
-- Grupy i liczby w retencja_decyzje (test_2025: 4 734 umowy, oferta 2 332, kontrola 2 402)
SELECT okres, grupa, kwalifikuje, count(*), min(data_konca), max(data_konca), count(data_oferty)
FROM retencja_decyzje GROUP BY ALL ORDER BY ALL;

-- Oferta zawsze 45 dni przed końcem umowy
SELECT date_diff('day', data_oferty, data_konca) AS dni, count(*)
FROM retencja_decyzje WHERE okres = 'test_2025' AND grupa = 'oferta' GROUP BY 1;

-- Górne 35% z całego okresu a flaga kwalifikuje (1 631 zgodnych, 26 + 25 rozbieżnych)
WITH t AS (SELECT *, quantile_cont(score_polityki, 0.65) OVER () AS q65
           FROM retencja_decyzje WHERE okres = 'test_2025')
SELECT kwalifikuje, score_polityki >= q65 AS gorne_35, count(*) FROM t GROUP BY ALL ORDER BY ALL;

-- kwalifikuje = górne 35% w miesiącu końca umowy (rozbieżne 2 umowy)
WITH t AS (SELECT *, quantile_cont(score_polityki, 0.65) OVER (PARTITION BY date_trunc('month', data_konca)) AS q
           FROM retencja_decyzje WHERE okres = 'test_2025')
SELECT kwalifikuje, score_polityki >= q AS gorne_35_w_miesiacu, count(*) FROM t GROUP BY ALL ORDER BY ALL;

-- Losowanie na poziomie umowy: 52 z 93 wielolokalowych umów ramowych ma umowy w obu grupach
SELECT count(*) AS ramowe, sum((n > 1)::INT) AS wielolokalowe, sum((g > 1)::INT) AS w_obu_grupach
FROM (SELECT m.id_umowy_ramowej, count(*) AS n, count(DISTINCT r.grupa) AS g
      FROM retencja_decyzje AS r JOIN migawki_najemcy AS m USING (id_umowy)
      WHERE r.okres = 'test_2025' AND m.id_umowy_ramowej IS NOT NULL GROUP BY 1);

-- Wypowiedzenia przed ofertą w segmentach score i grupach
WITH t AS (
    SELECT r.grupa, m.odejdzie, m.wypowiedzenie_przed_migawka,
           r.score_polityki >= (SELECT quantile_cont(score_polityki, 0.65) FROM retencja_decyzje
                                WHERE okres = 'test_2025') AS gorne_35,
           coalesce(date_diff('day', m.wypowiedzenie_data, m.data_do) > 45
                    AND m.wypowiedzenie_data <= m.data_do, false) AS wyp_przed_oferta
    FROM retencja_decyzje AS r JOIN migawki_najemcy AS m USING (id_umowy)
    WHERE r.okres = 'test_2025')
SELECT gorne_35, grupa, count(*) AS n,
       round(100 * avg(wypowiedzenie_przed_migawka::INT), 2) AS pct_wyp_przed_migawka,
       round(100 * avg(wyp_przed_oferta::INT), 2) AS pct_wyp_przed_oferta,
       round(100 * sum(wyp_przed_oferta::INT) / sum(odejdzie), 2) AS pct_odchodzacych_z_wyp_przed_oferta
FROM t GROUP BY ROLLUP (gorne_35, grupa) ORDER BY 1, 2;
```

Statystyka (funkcje w `eksperyment_rabatu_2025.py`):

- `efekt`: ATE = p̂_oferta − p̂_kontrola, SE = √(p̂ₒ(1−p̂ₒ)/nₒ + p̂ₖ(1−p̂ₖ)/nₖ), przedział ATE ± 1,96·SE, p z testu z;
- `roznica_efektow`: różnica ATE dwóch rozłącznych segmentów, SE = √(SE₁² + SE₂²);
- `ate_bootstrap_klastrow`: 2 000 losowań najemców ze zwracaniem (ziarno 42), przedział percentylowy 2,5–97,5;
- `efekt_stratyfikowany`: ATE w warstwach `wypowiedzenie_przed_migawka`, ważony udziałem warstw;
- `balans_cechy`: średnie, SMD (wspólne odchylenie = √((s²ₒ + s²ₖ)/2); dla udziału √((pₒqₒ + pₖqₖ)/2)), braki, p;
- `laczny_test_balansu`: regresja logistyczna metodą Newtona na standaryzowanych cechach, statystyka LR, rozkład χ².
