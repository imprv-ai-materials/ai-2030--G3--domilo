# B1. Cena w opisie ogłoszenia jako cecha modelu wyceny: celowy przeciek

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw). Policzono 2026-11-15
skryptem `api/api/ai/valuation_model/evals/przeciek_opisu.py`; każda tabela ma numer sekcji z wydruku skryptu.
Podział i metryki są takie jak w `docs/b1_dane.md` i `docs/b3_wycena_v2_geo.md`: trening 2023-01 – 2025-06,
walidacja 2025-07 – 2025-12, test 2026-01 – 2026-06 według `data_aktu`, target `rcn_transakcje.cena_pln`.

## Wnioski

1. Prawie co trzecie ogłoszenie podaje w opisie kwotę: 54 913 ze 176 859 (31,1%), a z 49 668 (28,1%) da się
   odczytać cenę sprzedaży. W 79,2% przypadków jest ona dokładnie równa cenie ofertowej z ogłoszenia, a w 93,3%
   różni się od niej najwyżej o 1%. Opis to więc kopia ceny ofertowej, a nie dodatkowa wiedza o lokalu.
2. Model z ceną z opisu wygląda na testowym zbiorze dopasowań na znacznie lepszy: MAPE spada z 10,6% do 5,1%,
   a na całym teście z 10,2% do 8,4%. To złudzenie. Na 300 operatach kontrolnych, czyli tam, gdzie bank sprawdza
   model, wynik jest gorszy niż bez tej cechy (7,9% wobec 7,5%), bo lokale Domilo nie są wystawione na sprzedaż
   i ich opisy nie zawierają ceny.
3. Opisy lokali Domilo (`lokale_domilo_opisy`) podają **miesięczny czynsz najmu**: 5 811 z 7 200 opisów, kwoty od
   780 do 8 120 zł. Ceny sprzedaży nie ma w żadnym. Gdy taką kwotę weźmie się za cenę, model z przeciekiem myli się
   na operatach kontrolnych średnio o 56,8% i zaniża wycenę o 69,2% (mediana). Cena z opisu **nie może** być cechą
   modelu wyceny.
4. Duplikaty między portalami: 26 794 lokale ukazały się w dwóch ogłoszeniach w ciągu 3 dni (53 588 ogłoszeń).
   Wcześniejsze liczenie w `b1_dane.md` (21 445) zaniżało tę liczbę, bo w 5 939 parach jeden portal nie podał roku
   budowy. Żadna grupa nie trafiła jednocześnie do treningu i testu, więc podział nie wymagał poprawek. Osobno
   zostaje 8 odsprzedaży tego samego lokalu w różnych zbiorach, w tym 2 z testem (decyzja do podjęcia, pytanie 2).
5. Przy okazji powstał pierwszy sprawdzian na 300 operatach kontrolnych. Obecny model v1 ma tam MAPE 7,1%, a więc
   mieści się w warunku banku ≤ 8%, przy baseline v0 13,4%. Model zaniża jednak wycenę (mediana −5,4%), więc wynik
   wymaga osobnej analizy, zanim uznamy warunek za spełniony.

## Tabele

### 1. Wzmianki o cenie w `radar_oferty.opis`

Typy wzmianek (oferta może mieć kilka): kwota = „Cena: 414 000 zł.”, „Cena 1305 tys.”, „Cena 518 tys. zł.”,
„Cena do negocjacji: 605 000.”; zł/m² = „Tylko 17 800 zł/m².”; rata = „Rata od 1 880 zł miesięcznie.”;
obniżka = „Obniżka z 814 do 761 tys.”. Zdania bez kwoty („cena uwzględnia nakłady”, „Niski czynsz administracyjny”)
nie są wliczone. Po wycięciu tych szablonów liczba z „zł”, „tys.”, „mln” albo „PLN” zostaje tylko w 1 opisie: to
oferta z ujemną ceną („Obniżka z -286 do -273 tys.”), którą parser w Pythonie też liczy jako obniżkę (zapytanie
kontrolne na końcu raportu).

| Wzmianka | Ogłoszenia | Odsetek |
|---|---:|---:|
| kwota | 36 312 | 20,5% |
| zł/m² | 7 182 | 4,1% |
| rata | 5 245 | 3,0% |
| obniżka | 6 174 | 3,5% |
| **dowolna kwota** | **54 913** | **31,1%** |
| cena sprzedaży do odczytania (kwota, obniżka albo zł/m² × metraż) | 49 668 | 28,1% |
| wszystkie ogłoszenia | 176 859 | 100% |

| Portal | Ogłoszenia | Z kwotą | Z ceną do odczytania | Odsetek z kwotą |
|---|---:|---:|---:|---:|
| deweloper | 1 726 | 525 | 469 | 30,4% |
| domteraz | 60 519 | 18 634 | 16 915 | 30,8% |
| lokum24 | 81 013 | 25 311 | 22 857 | 31,2% |
| sprzedajemy_mieszkania | 33 601 | 10 443 | 9 427 | 31,1% |

#### 1a. Cena z opisu a `cena_ofertowa`

Iloraz = cena z opisu ÷ cena ofertowa. Bez 1 oferty z ceną ofertową ≤ 0 („Obniżka z -286 do -273 tys.”).

| Szablon | Ogłoszenia | Równa ofertowej | W granicach ±1% | Wyższa | Niższa | Różne: min ilorazu | Mediana | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Cena: … zł | 17 165 | 90,2% | 90,2% | 1 674 | 0 | 1,0398 | 1,0695 | 1,1003 |
| Cena … tys. | 12 989 | 87,3% | 87,3% | 1 649 | 0 | 1,0397 | 1,0697 | 1,1011 |
| Cena do negocjacji: … | 6 158 | 100% | 100% | 0 | 0 | — | — | — |
| … zł/m² × metraż | 7 182 | 2,2% | 99,9% | 3 542 | 3 482 | 0,9812 | 1,0001 | 1,0273 |
| Obniżka z … do … tys. | 6 173 | 100% | 100% | 0 | 0 | — | — | — |
| **razem** | **49 667** | **79,2%** | **93,3%** | 6 865 | 3 482 | 0,9812 | 1,0016 | 1,1011 |

W 3 323 ogłoszeniach z „Cena: … zł” albo „Cena … tys.” cena w opisie jest o 4,0–10,1% **wyższa** od ofertowej,
nigdy niższa. Hipoteza (niesprawdzona w danych): opis nie został poprawiony po obniżce ceny. Przy zł/m² różnica
±2,7% wynika z zaokrąglenia ceny za m².

### 2. Co jest w `lokale_domilo_opisy`

| Opisy | Z czynszem najmu | Ze wzmianką o cenie sprzedaży | Z ceną sprzedaży | Czynsz = `pms_lokale.czynsz_katalogowy` | Czynsz min | Mediana | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 7 200 | 5 811 | 0 | 0 | 5 811 | 780 zł | 2 450 zł | 8 120 zł |

Formy czynszu: „Miesięcznie 2 550 zł (plus media wg zużycia)”, „Czynsz 3 540 zł + media”, „Czynsz: 3 230 zł/mies.
+ media”. Czynsz w opisie zawsze równa się `czynsz_katalogowy`, a ten opisuje stan na dzień eksportu (CLAUDE.md).
Dla innych modeli (np. retencji) opis jest więc tym samym przeciekiem stanu z końca eksportu co sama kolumna.
Z 300 lokali z operatem kontrolnym czynsz w opisie ma 228 (76,0%).

### 3. Deduplikacja ofert i grupy lokali

Definicja (`api/api/ai/features/wycena/grupy_lokali.sql`): ten sam lokal = te same `lat`, `lon`, `metraz`,
`pietro`. Kolejna publikacja należy do grupy, jeśli ukazała się najwyżej 3 dni po poprzedniej. Transakcja
dostaje grupę dopasowanej oferty (`radar_dopasowania`), a bez dopasowania tworzy własną grupę.

#### 3a. Grupy ofert

| Ogłoszenia | Grupy | Grupy z > 1 ogłoszeniem | Ich ogłoszenia | W tym jeden portal bez roku budowy | Każde ogłoszenie na innym portalu | Ten sam portal 2× | Grupy dłuższe niż 3 dni | Max ogłoszeń w grupie |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 176 859 | 150 065 | 26 794 | 53 588 | 5 939 | 26 789 | 5 | 0 | 2 |

Łańcuchy dłuższe niż 3 dni nie wystąpiły (każda grupa ma najwyżej 2 ogłoszenia). `b1_dane.md` (tabela 1b) łączył
ogłoszenia także po `rok_budowy`. Para, w której jeden portal nie podał roku (NULL), nie łączyła się wtedy, stąd
21 445 zamiast 26 794.

#### 3b. Rozłączność zbiorów po grupie

| Zbiór | Transakcje | Z dopasowaną ofertą | Grupa także w innym zbiorze | Usunięte | Po usunięciu |
|---|---:|---:|---:|---:|---:|
| trening | 38 522 | 14 361 | 0 | 0 | 38 522 |
| walidacja | 7 686 | 3 139 | 0 | 0 | 7 686 |
| test | 7 487 | 2 882 | 0 | 0 | 7 487 |

Reguła (`bez_grup_z_wczesniejszych_zbiorow`): wiersz walidacji albo testu z grupą widzianą we wcześniejszym zbiorze
odpada. Tutaj nie odpadł żaden, bo każda grupa ofert ma najwyżej jedną transakcję.

#### 3c. Ten sam lokal bez okna dat (odsprzedaże)

| Lokale (lat, lon, metraż, piętro) z > 1 transakcją | Ich transakcje | W różnych zbiorach | W tym z testem |
|---:|---:|---:|---:|
| 28 | 56 | 8 | 2 |

To osobne sprzedaże tego samego lokalu (inna data aktu). Grupa z okna 3 dni ich nie łączy, więc zostały w zbiorach.
`b1_dane.md` podaje 22 takie lokale, bo liczył je na kluczu z liczbą pokoi i na całym RCN.

### 4. Model z przeciekiem: cena z opisu jako cecha

Cecha `cena_z_opisu` = cena z opisu dopasowanej oferty, a gdy jej tam nie ma, z drugiej oferty tej samej grupy
opublikowanej nie później niż akt. Dwa modele LightGBM o tych samych hiperparametrach (`v2_lightgbm`), na tych samych
wierszach treningu, z wczesnym zatrzymaniem na walidacji. Liczba drzew: bez przecieku 265, z przeciekiem 872.

#### 4a. Pokrycie cechy

| Zbiór | Transakcje | Z dopasowaniem | Z ceną z opisu | W tym z dopasowanej oferty |
|---|---:|---:|---:|---:|
| trening | 38 522 | 14 361 | 12 672 (32,9%) | 12 360 |
| walidacja | 7 686 | 3 139 | 2 776 | 2 707 |
| test | 7 487 | 2 882 | 2 533 (33,8%) | 2 480 |

#### 4b. MAPE: bez przecieku i z przeciekiem

Baseline: `v0_mediana_dzielnicy` (mediana ceny m² dzielnicy z treningu × metraż); obecny model: `v1_liniowa`.
Operaty kontrolne: 300 lokali Domilo, `data_wyceny` 2026-09-01 – 2026-09-28. Cechy lokalu pochodzą z `pms_lokale`
i `pms_budynki` (`rok_oddania` jako rok budowy), a wartością odniesienia jest `operaty.wartosc_pln`.

| Model | Zbiór | n | MAPE | MdAPE | Mediana błędu ze znakiem | MAE |
|---|---|---:|---:|---:|---:|---:|
| v0_mediana_dzielnicy (baseline) | test: dopasowania z ceną w opisie | 2 533 | 13,9% | 11,5% | −6,7% | 86 560 zł |
| v1_liniowa (obecna) | test: dopasowania z ceną w opisie | 2 533 | 10,6% | 8,6% | −6,5% | 65 852 zł |
| bez przecieku (v2_lightgbm) | test: dopasowania z ceną w opisie | 2 533 | 10,6% | 8,4% | −6,5% | 65 974 zł |
| **z przeciekiem** | **test: dopasowania z ceną w opisie** | 2 533 | **5,1%** | 4,2% | −2,1% | 35 421 zł |
| v0_mediana_dzielnicy (baseline) | test: wszystkie dopasowania | 2 882 | 13,9% | 11,5% | −6,7% | 86 028 zł |
| v1_liniowa (obecna) | test: wszystkie dopasowania | 2 882 | 10,7% | 8,6% | −6,5% | 65 581 zł |
| bez przecieku (v2_lightgbm) | test: wszystkie dopasowania | 2 882 | 10,7% | 8,5% | −6,6% | 65 844 zł |
| **z przeciekiem** | **test: wszystkie dopasowania** | 2 882 | **5,9%** | 4,5% | −2,5% | 39 152 zł |
| v0_mediana_dzielnicy (baseline) | test: bez dopasowania | 4 605 | 13,1% | 11,1% | −6,3% | 81 757 zł |
| v1_liniowa (obecna) | test: bez dopasowania | 4 605 | 9,9% | 8,1% | −6,2% | 61 794 zł |
| bez przecieku (v2_lightgbm) | test: bez dopasowania | 4 605 | 9,8% | 8,1% | −6,3% | 61 374 zł |
| z przeciekiem | test: bez dopasowania | 4 605 | 10,0% | 8,2% | −6,5% | 62 885 zł |
| v0_mediana_dzielnicy (baseline) | test: wszystkie | 7 487 | 13,4% | 11,3% | −6,4% | 83 401 zł |
| v1_liniowa (obecna) | test: wszystkie | 7 487 | 10,2% | 8,3% | −6,3% | 63 252 zł |
| bez przecieku (v2_lightgbm) | test: wszystkie | 7 487 | 10,2% | 8,3% | −6,4% | 63 095 zł |
| z przeciekiem | test: wszystkie | 7 487 | 8,4% | 6,5% | −4,5% | 53 749 zł |
| v0_mediana_dzielnicy (baseline) | 300 operatów kontrolnych | 300 | 13,4% | 13,3% | −13,3% | 115 192 zł |
| v1_liniowa (obecna) | 300 operatów kontrolnych | 300 | 7,1% | 6,3% | −5,4% | 63 542 zł |
| bez przecieku (v2_lightgbm) | 300 operatów kontrolnych | 300 | 7,5% | 6,5% | −5,9% | 67 634 zł |
| **z przeciekiem: opis Domilo bez ceny (brak cechy)** | **300 operatów kontrolnych** | 300 | **7,9%** | 6,8% | −6,2% | 70 659 zł |
| **z przeciekiem: czynsz z opisu Domilo wzięty za cenę** | **300 operatów kontrolnych** | 300 | **56,8%** | 69,2% | −69,2% | 482 721 zł |

W ostatnim wierszu 72 z 300 opisów nie ma kwoty, więc dla nich cecha jest pusta. Pozostałe 228 dostają czynsz
miesięczny (780–8 120 zł) jako „cenę”.

#### 4c. Dlaczego to przeciek, choć wskaźnik ważności go nie pokazuje

| Cecha (model z przeciekiem) | Udział w zysku (gain) |
|---|---:|
| metraz | 72,2% |
| dzielnica | 20,4% |
| rok_budowy | 3,8% |
| cena_z_opisu | 3,3% |
| pietro | 0,3% |
| pokoje | 0,0% |
| miasto | 0,0% |

Cena z opisu ma tylko 3,3% udziału w zysku, bo 2/3 transakcji jej nie ma. Mimo to na transakcjach, które ją mają,
MAPE spada z 10,6% do 5,1%, czyli o połowę. Ranking ważności cech nie wykryje więc przecieku, a porównanie MAPE
między zbiorem, w którym cecha jest, a zbiorem, w którym jej brak, wykrywa go od razu.

| Wycena | Zbiór | n | MAPE | MdAPE | Mediana błędu ze znakiem | MAE |
|---|---|---:|---:|---:|---:|---:|
| sama cena z opisu (bez modelu) | test: dopasowania z ceną w opisie | 2 533 | 7,4% | 6,6% | +6,6% | 48 867 zł |

Sama cena z opisu, bez żadnego modelu, ma MAPE 7,4%: zawyża, bo transakcja zamyka się poniżej ceny ofertowej
(`b1_dane.md`: mediana 0,941). Model z przeciekiem uczy się tego rabatu i dochodzi do 5,1%. Cała jego „przewaga”
to cena ofertowa tego samego lokalu, której przy wycenie lokalu Domilo nie ma.

## SQL i kod

Pliki:
- `api/api/ai/features/wycena/ceny_w_opisie.py`: wzorce kwot (`wzmianki_o_cenie`, `cena_z_opisu`,
  `szablon_ceny`, `czynsz_najmu_z_opisu`);
- `api/api/ai/features/wycena/grupy_lokali.sql` i `grupy_lokali.py`: grupy ofert, grupy transakcji, rozłączność;
- `api/api/ai/valuation_model/evals/przeciek_opisu.py`: wszystkie tabele tego raportu. Model z przeciekiem
  (`ModelZPrzeciekiem`) jest tylko w tym skrypcie: nie ma go w `versions/` i nie zapisujemy go;
- testy: `api/tests/test_wycena_przeciek_opisu.py`.

Uruchomienie (z katalogu `api/`, wymaga `pypyr baza`):

```bash
poetry run python -m api.ai.valuation_model.evals.przeciek_opisu
```

Wzorce kwot (Python, `ceny_w_opisie.py`); liczba = `-?\d{1,3}(?:[   ]\d{3})+|-?\d+`:

```text
kwota:    Cena: (liczba) zł  |  Cena (liczba) tys\.  |  Cena do negocjacji: (liczba)
zl_m2:    (liczba) zł/m²
rata:     Rata od (liczba) zł
obnizka:  Obniżka z (liczba) do (liczba) tys\.
czynsz:   (?:Miesięcznie|Czynsz:?) (liczba) zł
cena_z_opisu: Cena: zł > Cena do negocjacji > Cena tys. ×1000 > obniżka (druga liczba) ×1000 > zł/m² × metraż
```

Grupy ofert (`grupy_lokali.sql`):

```sql
WITH uporzadkowane AS (
    SELECT id_oferty, portal, data_publikacji, lat, lon, metraz, pietro,
           CASE WHEN data_publikacji - lag(data_publikacji) OVER w <= INTERVAL 3 DAY THEN 0 ELSE 1 END AS nowa_grupa
    FROM radar_oferty
    WINDOW w AS (PARTITION BY lat, lon, metraz, pietro ORDER BY data_publikacji, id_oferty)
),
numerowane AS (
    SELECT *, sum(nowa_grupa) OVER (PARTITION BY lat, lon, metraz, pietro ORDER BY data_publikacji, id_oferty
                                    ROWS UNBOUNDED PRECEDING) AS nr_grupy
    FROM uporzadkowane
)
SELECT id_oferty,
       'G' || first(id_oferty ORDER BY data_publikacji, id_oferty)
           OVER (PARTITION BY lat, lon, metraz, pietro, nr_grupy) AS id_grupy
FROM numerowane
```

Grupa transakcji (`grupy_transakcji`):

```sql
SELECT t.id_transakcji, coalesce(g.id_grupy, 'T' || t.id_transakcji) AS id_grupy
FROM rcn_transakcje t
LEFT JOIN radar_dopasowania d USING (id_transakcji)
LEFT JOIN (/* grupy_lokali.sql */) g ON g.id_oferty = d.id_oferty
```

Statystyki grup (tabela 3a):

```sql
WITH g AS (/* grupy_lokali.sql */), o AS (SELECT * FROM radar_oferty JOIN g USING (id_oferty)),
grupy AS (
    SELECT id_grupy, count(*) AS oferty, count(DISTINCT portal) AS portale,
           max(data_publikacji) - min(data_publikacji) AS rozpietosc,
           count(*) FILTER (rok_budowy IS NULL) AS puste_rok_budowy
    FROM o GROUP BY id_grupy
)
SELECT (SELECT count(*) FROM radar_oferty) AS oferty, count(*) AS grupy,
       count(*) FILTER (oferty > 1) AS grupy_z_wiecej_niz_1_oferta,
       CAST(sum(oferty) FILTER (oferty > 1) AS INTEGER) AS ich_oferty,
       count(*) FILTER (oferty > 1 AND puste_rok_budowy > 0) AS w_tym_rok_budowy_pusty_w_jednej,
       count(*) FILTER (oferty > 1 AND portale = oferty) AS kazda_oferta_na_innym_portalu,
       count(*) FILTER (oferty > portale) AS ten_sam_portal_dwa_razy,
       count(*) FILTER (rozpietosc > INTERVAL 3 DAY) AS grupy_dluzsze_niz_3_dni,
       max(oferty) AS max_ofert_w_grupie
FROM grupy;
```

Odsprzedaże (tabela 3c):

```sql
WITH p AS (/* podzial.sql */),
t AS (SELECT t.*, p.zbior FROM rcn_transakcje t JOIN p USING (id_transakcji)),
l AS (SELECT lat, lon, metraz, pietro, count(*) AS n, count(DISTINCT zbior) AS zbiory, bool_or(zbior = 'test') AS z_testem
      FROM t GROUP BY ALL HAVING count(*) > 1)
SELECT count(*) AS lokale_z_kilkoma_transakcjami, CAST(sum(n) AS INTEGER) AS ich_transakcje,
       count(*) FILTER (zbiory > 1) AS w_roznych_zbiorach, count(*) FILTER (zbiory > 1 AND z_testem) AS w_tym_z_testem
FROM l;
```

Oferty, z których bierzemy cenę dla transakcji (cecha z przeciekiem):

```sql
WITH g AS (/* grupy_lokali.sql */)
SELECT d.id_transakcji, o.id_oferty, o.data_publikacji, o.metraz, o.opis, (o.id_oferty = d.id_oferty) AS dopasowana
FROM radar_dopasowania d
JOIN g gd ON gd.id_oferty = d.id_oferty
JOIN g ON g.id_grupy = gd.id_grupy
JOIN radar_oferty o ON o.id_oferty = g.id_oferty
JOIN rcn_transakcje t ON t.id_transakcji = d.id_transakcji
WHERE o.data_publikacji <= t.data_aktu
-- w Pythonie: pierwsza z ceną, najpierw dopasowana oferta, potem najnowsza z grupy
```

Operaty kontrolne z cechami lokalu i opisem:

```sql
SELECT op.id_operatu, op.id_lokalu, op.data_wyceny, op.wartosc_pln,
       b.miasto, b.dzielnica, l.metraz, l.pokoje, l.pietro, b.rok_oddania AS rok_budowy,
       l.czynsz_katalogowy, ld.opis_marketingowy
FROM operaty op
JOIN pms_lokale l USING (id_lokalu)
JOIN pms_budynki b USING (id_budynku)
LEFT JOIN lokale_domilo_opisy ld USING (id_lokalu)
WHERE op.typ = 'kontrolny'
ORDER BY op.id_operatu;
```

Kontrola pokrycia szablonów (zapytanie 1c, DuckDB CLI z katalogu głównego): po wycięciu szablonów kwot zostaje
1 opis z liczbą przy „zł/tys/mln/PLN” i jest to oferta z ujemną ceną (`Obniżka z -286 do -273 tys.`).

```sql
WITH r AS (SELECT regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(opis,
   'Cena: [0-9  ,.]+ zł\.', '', 'g'), 'Cena [0-9 ,]+ tys\.', '', 'g'), 'Cena do negocjacji: [0-9  ,]+', '', 'g'),
   '[0-9  ,]+ zł/m²', '', 'g'), 'Rata od [0-9  ,]+ zł', '', 'g'), 'Obniżka z [0-9 ,]+ do [0-9 ,]+ tys\.', '', 'g') AS reszta
  FROM 'data/radar/radar_oferty.parquet')
SELECT count(*) AS z_kwota_poza_szablonami FROM r WHERE regexp_matches(reszta, '[0-9]\s*(zł|tys|mln|PLN)');
```

Metryki: `api/api/ai/valuation_model/evals/metryki.py` (MAPE = średnia |wycena − cena| / cena; mediana błędu ze
znakiem < 0 oznacza zaniżanie).
