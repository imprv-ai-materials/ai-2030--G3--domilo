# B1. Przedział wyceny 80% (P10–P90): modele kwantylowe LightGBM i kalibracja CQR

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw) przez `pypyr baza`.
Policzono 2026-11-15. Wszystkie liczby pochodzą z
[`przedzialy_v2.py`](../api/api/ai/valuation_model/evals/przedzialy_v2.py) (sekcja [SQL i kod](#sql-i-kod)) i są
zapisane w `api/api/ai/valuation_model/versions/v2_lgbm_geo_cqr/metryki.json` oraz w runie MLflow `v2_lgbm_geo_cqr`
(eksperyment `wycena`, run `a3b8c67e99d741c8a7e4458d18b41825`).
Wymóg banku: przedział 80% musi obejmować od 77% do 83% cen. Pokrycie = odsetek cen transakcyjnych w [P10; P90],
szerokość = (P90 − P10) / P50.

## Wnioski

Same modele kwantylowe dają za wąski przedział: na transakcjach z 2026 obejmuje 71,3% cen, poniżej progu banku.
Po kalibracji CQR na transakcjach z II półrocza 2025 pokrycie rośnie do 77,6% przy medianie szerokości 23,9% wyceny
(przed kalibracją 20,8%), czyli łącznie mieści się w normie 77–83%, ale tylko 0,6 pp nad dolną granicą. Przedział
myli się głównie w górę (17,6% cen nad P90, 4,8% pod P10), bo model w 2026 zaniża ceny, więc normy nie spełniają
mieszkania od 600 tys. zł, apartamentowce (53,7%), kamienice, domy wielorodzinne i Poznań: w normie jest 11 z 20
segmentów, a przy prostym stałym przedziale −8,0% / +15,4% wokół wyceny 9 z 20. Wariant CQR z osobną korektą dołu
i góry trafił w 17 z 20 segmentów (79,8% łącznie), ale wybraliśmy metodę przed otwarciem testu, więc ten wariant
trzeba potwierdzić na nowych danych (np. 300 operatów kontrolnych). Dla Katowic przedział nie ostrzega: 31 z 40
operatów due diligence leży poniżej P10, więc bezpiecznik dla nieznanego miasta jest nadal potrzebny.

## Tabele

Zbiory (podział czasowy RCN, `podzial.sql`): trening = akty 2023-01 – 2025-06, walidacja = 2025-07 – 2025-12
(zbiór kalibracyjny), test = 2026-01 – 2026-06 (otwarty dla przedziału jeden raz, 2026-11-15). Pokrycie, ogony i
szerokość w %. „Szerokość” = mediana (P90 − P10) / P50.

Porównywane przedziały (wszystkie z P50 = wycena v2_lgbm_geo):

| Przedział | Jak powstaje | Rola |
|---|---|---|
| kwantylowe, przed kalibracją | P10 i P90 z dwóch modeli LightGBM `objective='quantile'` (alpha 0,1 i 0,9) | stan „przed” |
| **CQR** | granice kwantylowe przesunięte o jedną korektę z walidacji (symetrycznie, w ln ceny) | **metoda główna, wybrana przed otwarciem testu** |
| CQR asymetryczny | osobna korekta dla P10 i dla P90 (po 10% w każdym ogonie na walidacji) | wariant liczony obok, bez wybierania na teście |
| stały ±% (odniesienie) | P10 = P50 · 0,9201, P90 = P50 · 1,1539: kwantyle błędu v2_lgbm_geo na walidacji | baseline: najprostsza reguła |

### 1. Pokrycie ogółem

| Zbiór | Przedział | Transakcje | **Pokrycie** | Norma 77–83 | Pod P10 | Nad P90 | Mediana szerokości | Średnia szerokości |
|---|---|---:|---:|---|---:|---:|---:|---:|
| walidacja (kalibracja) | kwantylowe, przed kalibracją | 7 686 | 73,9 | **nie** | 8,1 | 17,9 | 20,8 | 22,2 |
| walidacja (kalibracja) | **CQR** | 7 686 | 80,0 | tak | 6,1 | 13,8 | 23,9 | 25,3 |
| walidacja (kalibracja) | CQR asymetryczny | 7 686 | 80,2 | tak | 9,8 | 10,0 | 23,4 | 24,8 |
| walidacja (kalibracja) | stały ±% (odniesienie) | 7 686 | 80,0 | tak | 10,0 | 10,0 | 23,4 | 23,4 |
| **test** | kwantylowe, przed kalibracją | 7 487 | **71,3** | **nie** | 6,1 | 22,6 | 20,8 | 22,4 |
| **test** | **CQR** | 7 487 | **77,6** | tak | 4,8 | 17,6 | 23,9 | 25,5 |
| **test** | CQR asymetryczny | 7 487 | **79,8** | tak | 7,3 | 12,8 | 23,4 | 25,0 |
| **test** | stały ±% (odniesienie) | 7 487 | **79,1** | tak | 7,6 | 13,3 | 23,4 | 23,4 |

Na walidacji pokrycie po kalibracji wynosi 80% z konstrukcji: tam liczymy korektę. Miarą jest test. Margines CQR na
teście (77,6% przy progu 77%) jest mały wobec losowości: błąd standardowy pokrycia przy n = 7 487 to
√(0,8 · 0,2 / 7 487) = 0,46 pp.

### 2. Parametry przedziału

| Parametr | Wartość | Skąd |
|---|---:|---|
| drzewa modelu P10 / P90 | 964 / 344 | wczesne zatrzymanie (strata kwantylowa) na treningu 2025-01 – 2025-06 |
| korekta CQR (ln) | 0,0153 | ⌈(n + 1) · 0,8⌉-ty najmniejszy wynik zgodności na walidacji, n = 7 686 |
| w złotych | P10 · 0,9848, P90 · 1,0154 | exp(∓0,0153) |
| korekty CQR asymetrycznego (ln): dół / góra | −0,0129 / 0,0332 | każda na poziomie 0,9 z osobnych wyników |
| stały przedział (ln): dół / góra | −0,0833 / 0,1431 | kwantyle 10% i 90% błędu ln(cena / P50) na walidacji |

Korekta CQR jest dodatnia, więc kalibracja poszerza przedział (o ok. 1,5% z każdej strony). Wariant asymetryczny
podnosi P10 o ok. 1,3% (exp(0,0129)) i P90 o ok. 3,4% (exp(0,0332)), czyli przesuwa przedział w górę: na
walidacji ceny częściej wychodzą ponad P90 niż poniżej P10.

### 3. Test według segmentu ceny transakcyjnej (jak tabela 1 w [b1_bledy.md](b1_bledy.md))

| Segment ceny | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| < 300 tys. | 798 | 80,8 | **82,5** | tak | 15,4 | 2,1 | 80,5 | 61,9 | 35,5 | 38,7 | 23,4 |
| 300–600 tys. | 3 516 | 75,3 | **80,6** | tak | 4,6 | 14,8 | 81,7 | 78,2 | 22,8 | 25,9 | 23,4 |
| 600 tys. – 1 mln | 2 031 | 64,9 | **73,8** | **nie** | 3,0 | 23,3 | 77,4 | 83,3 | 17,0 | 20,1 | 23,4 |
| ≥ 1 mln | 1 142 | 63,5 | **72,1** | **nie** | 1,3 | 26,6 | 77,9 | 86,3 | 16,9 | 19,9 | 23,4 |
| **wszystkie** | 7 487 | 71,3 | **77,6** | tak | 4,8 | 17,6 | 79,8 | 79,1 | 20,8 | 23,9 | 23,4 |

Podział według prawdziwej ceny przesuwa ogony: tanio sprzedane lokale lądują pod P10, drogo sprzedane nad P90 (ten
sam efekt co w b1_bledy.md, tabela 1). W chwili wyceny znamy tylko P50, więc ważniejsza jest tabela 4.

### 4. Test według segmentu wyceny P50 (to, co widać w chwili wyceny)

| Segment wyceny (P50) | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| < 300 tys. | 899 | 81,9 | **84,1** | **nie** | 5,9 | 10,0 | 84,5 | 63,4 | 35,9 | 39,0 | 23,4 |
| 300–600 tys. | 3 691 | 71,6 | **77,4** | tak | 5,7 | 16,9 | 78,9 | 77,2 | 22,2 | 25,3 | 23,4 |
| 600 tys. – 1 mln | 1 877 | 68,1 | **76,2** | **nie** | 3,9 | 19,9 | 79,5 | 85,8 | 16,7 | 19,7 | 23,4 |
| ≥ 1 mln | 1 020 | 66,8 | **75,5** | **nie** | 2,2 | 22,4 | 79,4 | 87,3 | 16,9 | 20,0 | 23,4 |
| **wszystkie** | 7 487 | 71,3 | **77,6** | tak | 4,8 | 17,6 | 79,8 | 79,1 | 20,8 | 23,9 | 23,4 |

Przedział CQR dopasowuje szerokość do lokalu: dla wycen poniżej 300 tys. zł ma 39,0%, a od 600 tys. zł 19,7–20,0%. Stały
przedział ma wszędzie 23,4%, więc tanie lokale obejmuje za rzadko (63,4%), a drogie za często (87,3%).

### 5. Test według miasta

| Miasto | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Gdańsk | 750 | 72,1 | **78,1** | tak | 5,2 | 16,7 | 81,9 | 77,2 | 22,3 | 25,3 | 23,4 |
| Kraków | 1 252 | 70,6 | **77,5** | tak | 4,4 | 18,1 | 78,9 | 81,2 | 20,3 | 23,4 | 23,4 |
| Poznań | 754 | 69,1 | **76,0** | **nie** | 4,8 | 19,2 | 78,5 | 75,2 | 23,9 | 27,0 | 23,4 |
| Warszawa | 2 978 | 71,2 | **78,0** | tak | 4,3 | 17,7 | 80,9 | 82,5 | 19,8 | 22,9 | 23,4 |
| Wrocław | 1 122 | 72,0 | **77,5** | tak | 5,9 | 16,7 | 78,6 | 77,9 | 20,1 | 23,2 | 23,4 |
| Łódź | 631 | 73,2 | **78,0** | tak | 5,9 | 16,2 | 77,7 | 67,4 | 29,4 | 32,5 | 23,4 |
| **wszystkie** | 7 487 | 71,3 | **77,6** | tak | 4,8 | 17,6 | 79,8 | 79,1 | 20,8 | 23,9 | 23,4 |

### 6. Test według typu budynku (`rcn_transakcje.typ_budynku`; model tej kolumny nie dostaje)

| Typ budynku | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| apartamentowiec | 298 | 46,0 | **53,7** | **nie** | 1,3 | 45,0 | 59,7 | 62,4 | 21,8 | 24,8 | 23,4 |
| blok | 6 182 | 73,1 | **79,3** | tak | 4,8 | 15,9 | 81,3 | 79,8 | 21,0 | 24,1 | 23,4 |
| dom_wielorodzinny | 301 | 67,4 | **76,4** | **nie** | 5,6 | 17,9 | 78,7 | 77,7 | 22,6 | 25,7 | 23,4 |
| kamienica | 706 | 67,3 | **73,8** | **nie** | 6,1 | 20,1 | 75,8 | 80,2 | 18,2 | 21,3 | 23,4 |
| **wszystkie** | 7 487 | 71,3 | **77,6** | tak | 4,8 | 17,6 | 79,8 | 79,1 | 20,8 | 23,9 | 23,4 |

Apartamentowce: 45,0% cen leży nad P90. To ten sam problem co w b1_bledy.md (tabela 4: zaniżenie o ok. 10%), a
kalibracja go nie naprawi, bo model nie wie, że lokal jest w apartamentowcu. Żaden z czterech przedziałów nie
przekracza tu 62,4%.

### 7. Test według metrażu

| Metraż | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| < 30 m² | 2 817 | 74,5 | **78,7** | tak | 6,3 | 15,1 | 80,2 | 71,3 | 25,9 | 28,9 | 23,4 |
| ≥ 30 m² | 4 670 | 69,3 | **77,0** | tak | 3,9 | 19,1 | 79,6 | 83,7 | 18,4 | 21,5 | 23,4 |
| **wszystkie** | 7 487 | 71,3 | **77,6** | tak | 4,8 | 17,6 | 79,8 | 79,1 | 20,8 | 23,9 | 23,4 |

| Miasto (lokale < 30 m²) | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Gdańsk | 275 | 76,4 | **79,6** | tak | 6,9 | 13,5 | 80,7 | 72,0 | 27,9 | 31,1 | 23,4 |
| Kraków | 452 | 72,8 | **77,7** | tak | 6,2 | 16,2 | 78,5 | 71,5 | 24,9 | 28,0 | 23,4 |
| Poznań | 293 | 73,4 | **77,5** | tak | 6,1 | 16,4 | 79,9 | 67,6 | 30,1 | 33,3 | 23,4 |
| Warszawa | 1 117 | 73,3 | **78,4** | tak | 5,6 | 16,0 | 80,5 | 76,2 | 23,1 | 26,3 | 23,4 |
| Wrocław | 444 | 76,4 | **79,1** | tak | 8,3 | 12,6 | 80,0 | 70,0 | 25,9 | 29,0 | 23,4 |
| Łódź | 236 | 79,7 | **81,4** | tak | 5,5 | 13,1 | 82,2 | 54,2 | 41,2 | 44,4 | 23,4 |
| **wszystkie** | 2 817 | 74,5 | **78,7** | tak | 6,3 | 15,1 | 80,2 | 71,3 | 25,9 | 28,9 | 23,4 |

Małe lokale, najsłabsze w wycenie punktowej (b1_bledy.md, tabela 5), mają szerszy przedział (28,9% wobec 21,5%) i
pokrycie w normie w każdym mieście. Stały przedział ma dla nich za mało (71,3%; Łódź 54,2%).

### 8. Test według miesiąca aktu (czy pokrycie spada z czasem)

| Miesiąc aktu | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-01 | 1 213 | 70,6 | **76,7** | **nie** | 5,4 | 18,0 | 80,5 | 79,0 | 20,4 | 23,6 | 23,4 |
| 2026-02 | 1 134 | 71,9 | **80,0** | tak | 3,9 | 16,1 | 81,7 | 80,9 | 20,7 | 23,8 | 23,4 |
| 2026-03 | 1 356 | 72,3 | **78,9** | tak | 4,4 | 16,7 | 80,8 | 79,0 | 21,0 | 24,1 | 23,4 |
| 2026-04 | 1 383 | 70,1 | **76,1** | **nie** | 5,1 | 18,7 | 78,4 | 76,5 | 21,2 | 24,3 | 23,4 |
| 2026-05 | 1 349 | 70,8 | **77,2** | tak | 5,1 | 17,7 | 78,9 | 79,6 | 20,7 | 23,7 | 23,4 |
| 2026-06 | 1 052 | 72,2 | **77,2** | tak | 4,9 | 17,9 | 78,6 | 79,9 | 20,7 | 23,8 | 23,4 |
| **wszystkie** | 7 487 | 71,3 | **77,6** | tak | 4,8 | 17,6 | 79,8 | 79,1 | 20,8 | 23,9 | 23,4 |

W kolejnych miesiącach 2026 nie widać wyraźnego spadku. Spadek pokrycia nastąpił między walidacją (80,0%, nad P90
13,8%) a testem (77,6%, nad P90 17,6%). Pasuje to do rosnącego zaniżenia wyceny: mediana błędu v2_lgbm_geo wynosi
−3,0% na walidacji i −4,5% na teście (`versions/v2_lgbm_geo/metryki.json`).

### 9. Ile segmentów spełnia normę banku (test, tabele 3–7 bez wierszy „wszystkie”, 20 segmentów)

| Przedział | Pokrycie ogółem | Segmenty w normie 77–83% |
|---|---:|---:|
| kwantylowe, przed kalibracją | 71,3 | 2 z 20 |
| stały ±% (odniesienie) | 79,1 | 9 z 20 |
| **CQR (główna)** | **77,6** | **11 z 20** |
| CQR asymetryczny (wariant, nie wybrany na teście) | 79,8 | 17 z 20 |

Segmenty: 4 segmenty ceny, 4 segmenty wyceny, 6 miast, 4 typy budynku, 2 grupy metrażu.

### 10. Katowice: przedział dla miasta spoza treningu (oferty z b1_bledy.md, tabele 7–8)

| Oferty 2026-06 – 2026-09 | Oferty | Mediana szerokości CQR | P90 szerokości CQR | Maks. szerokość CQR |
|---|---:|---:|---:|---:|
| 6 miast z treningu | 13 591 | 23,9 | 36,4 | 101,7 |
| Katowice (spoza treningu) | 1 240 | 29,7 | 44,2 | 63,2 |

| Operaty due diligence (Katowice) | Operat w [P10; P90] | Operat poniżej P10 | Operat powyżej P90 | Mediana szerokości | Mediana P10 / operat − 1 |
|---|---:|---:|---:|---:|---:|
| 40 | 9 | 31 | 0 | 41,8 | +9,8 |

Dla Katowic przedział jest tylko trochę szerszy niż w znanych miastach, a nawet jego dolna granica jest w medianie
o 9,8% wyżej niż wartość z operatu. Przedział mówi o niepewności wśród lokali podobnych do treningowych. Nie zastąpi
bezpiecznika dla nieznanego miasta (b1_bledy.md, sekcja 9, propozycja 1).

<details>
<summary>Walidacja (zbiór kalibracyjny) według segmentów</summary>

Łącznie pokrycie CQR na walidacji wynosi 80,0% z konstrukcji. Segmenty pokazują, gdzie przedział był nierówny już
przed testem.

| Segment ceny | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| < 300 tys. | 810 | 75,2 | **78,4** | tak | 20,4 | 1,2 | 74,1 | 55,9 | 35,1 | 38,3 | 23,4 |
| 300–600 tys. | 3 731 | 76,6 | **81,7** | tak | 5,6 | 12,7 | 81,2 | 79,0 | 22,7 | 25,7 | 23,4 |
| 600 tys. – 1 mln | 2 020 | 69,6 | **78,0** | tak | 4,1 | 17,9 | 79,2 | 86,0 | 16,9 | 20,0 | 23,4 |
| ≥ 1 mln | 1 125 | 71,9 | **79,5** | tak | 1,2 | 19,4 | 82,8 | 90,1 | 17,1 | 20,2 | 23,4 |
| **wszystkie** | 7 686 | 73,9 | **80,0** | tak | 6,1 | 13,8 | 80,2 | 80,0 | 20,8 | 23,9 | 23,4 |

| Segment wyceny (P50) | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| < 300 tys. | 880 | 78,6 | **81,1** | tak | 9,1 | 9,8 | 80,1 | 61,1 | 35,5 | 38,7 | 23,4 |
| 300–600 tys. | 3 806 | 74,1 | **79,5** | tak | 6,7 | 13,8 | 79,4 | 78,2 | 22,3 | 25,4 | 23,4 |
| 600 tys. – 1 mln | 1 940 | 71,0 | **79,2** | tak | 5,8 | 14,9 | 79,6 | 86,7 | 16,8 | 19,9 | 23,4 |
| ≥ 1 mln | 1 060 | 74,8 | **82,5** | tak | 2,2 | 15,4 | 84,1 | 90,2 | 17,1 | 20,1 | 23,4 |
| **wszystkie** | 7 686 | 73,9 | **80,0** | tak | 6,1 | 13,8 | 80,2 | 80,0 | 20,8 | 23,9 | 23,4 |

| Miasto | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Gdańsk | 745 | 74,9 | **81,2** | tak | 5,9 | 12,9 | 80,7 | 79,2 | 21,8 | 24,9 | 23,4 |
| Kraków | 1 253 | 74,0 | **80,0** | tak | 5,8 | 14,1 | 81,0 | 80,8 | 20,7 | 23,8 | 23,4 |
| Poznań | 798 | 69,3 | **75,3** | **nie** | 6,8 | 17,9 | 75,9 | 74,3 | 23,1 | 26,3 | 23,4 |
| Warszawa | 3 092 | 75,5 | **82,1** | tak | 4,7 | 13,2 | 82,1 | 83,9 | 19,5 | 22,5 | 23,4 |
| Wrocław | 1 192 | 71,8 | **77,8** | tak | 8,3 | 13,9 | 78,4 | 79,6 | 20,6 | 23,7 | 23,4 |
| Łódź | 606 | 74,6 | **78,5** | tak | 9,2 | 12,2 | 77,2 | 68,2 | 28,9 | 32,1 | 23,4 |
| **wszystkie** | 7 686 | 73,9 | **80,0** | tak | 6,1 | 13,8 | 80,2 | 80,0 | 20,8 | 23,9 | 23,4 |

| Typ budynku | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| apartamentowiec | 341 | 46,0 | **58,4** | **nie** | 2,3 | 39,3 | 63,3 | 65,4 | 21,3 | 24,3 | 23,4 |
| blok | 6 347 | 75,8 | **81,3** | tak | 6,4 | 12,2 | 81,1 | 80,6 | 21,0 | 24,1 | 23,4 |
| dom_wielorodzinny | 280 | 72,5 | **82,1** | tak | 4,3 | 13,6 | 83,6 | 83,6 | 21,4 | 24,5 | 23,4 |
| kamienica | 718 | 71,0 | **78,0** | tak | 5,7 | 16,3 | 78,4 | 80,5 | 18,7 | 21,8 | 23,4 |
| **wszystkie** | 7 686 | 73,9 | **80,0** | tak | 6,1 | 13,8 | 80,2 | 80,0 | 20,8 | 23,9 | 23,4 |

| Metraż | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| < 30 m² | 2 894 | 76,4 | **81,2** | tak | 7,4 | 11,4 | 80,0 | 72,5 | 25,9 | 28,9 | 23,4 |
| ≥ 30 m² | 4 792 | 72,4 | **79,3** | tak | 5,4 | 15,3 | 80,3 | 84,6 | 18,3 | 21,4 | 23,4 |
| **wszystkie** | 7 686 | 73,9 | **80,0** | tak | 6,1 | 13,8 | 80,2 | 80,0 | 20,8 | 23,9 | 23,4 |

| Miesiąc aktu | Transakcje | Pokrycie przed kalibracją | **Pokrycie CQR** | Norma 77–83 | Pod P10 (CQR) | Nad P90 (CQR) | Pokrycie CQR asym. | Pokrycie stały ±% | Szerokość przed | Szerokość CQR | Szerokość stały |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-07 | 1 300 | 74,4 | **80,6** | tak | 7,9 | 11,5 | 78,9 | 79,8 | 20,8 | 23,9 | 23,4 |
| 2025-08 | 1 176 | 75,3 | **81,2** | tak | 5,9 | 12,9 | 79,8 | 79,6 | 20,6 | 23,7 | 23,4 |
| 2025-09 | 1 283 | 73,9 | **79,5** | tak | 5,2 | 15,3 | 81,4 | 80,5 | 20,8 | 23,9 | 23,4 |
| 2025-10 | 1 412 | 72,1 | **78,3** | tak | 7,2 | 14,5 | 80,0 | 79,5 | 20,9 | 24,0 | 23,4 |
| 2025-11 | 1 244 | 73,3 | **79,7** | tak | 5,4 | 14,9 | 81,0 | 80,2 | 21,0 | 24,1 | 23,4 |
| 2025-12 | 1 271 | 74,9 | **81,1** | tak | 5,0 | 13,9 | 79,9 | 80,6 | 20,6 | 23,7 | 23,4 |
| **wszystkie** | 7 686 | 73,9 | **80,0** | tak | 6,1 | 13,8 | 80,2 | 80,0 | 20,8 | 23,9 | 23,4 |

</details>

## Decyzje metodyczne

| Decyzja | Wybór | Uzasadnienie |
|---|---|---|
| MAPIE czy własna implementacja | **własna** (`versions/v2_lgbm_geo_cqr/model.py`, ok. 20 linii rdzenia) | MAPIE nie ma w zależnościach projektu (`import mapie` → `ModuleNotFoundError`). Nasze modele uczą się na ln(ceny), mają własną obsługę kategorii i cech dodatkowych, a P50 bierzemy z gotowego modelu punktowego. MAPIE wymagałoby opakowania ich w estymator zgodny ze scikit-learn i dodania nowej zależności. Rdzeń CQR to jeden kwantyl, więc własny kod jest krótszy niż adapter, w pełni widoczny dla rewizji i sprawdzony testami (`api/tests/test_wycena_przedzial.py`, w tym symulacja: pokrycie 80% ± 1 pp na danych wymienialnych). |
| Skala korekty | ln(ceny) | Modele uczą się na ln(ceny). Korekta w ln jest względna: ten sam % dla lokalu za 300 tys. i za 1,5 mln zł. Korekta w złotych byłaby za duża dla tanich lokali i za mała dla drogich (błąd w zł rośnie z ceną, b1_bledy.md, tabela 6). |
| Poziom korekty | ⌈(n + 1) · 0,8⌉-ty najmniejszy wynik | Standardowa poprawka skończonej próby w CQR (Romano, Patterson, Candès 2019). |
| Czysty zbiór kalibracyjny | liczba drzew modeli kwantylowych z treningu 2025-H1 (7 710 transakcji), nie z walidacji | Gwarancja CQR wymaga, by zbiór kalibracyjny nie wpływał na modele. Najpierw uczenie na 2023-01 – 2024-12 z wczesnym zatrzymaniem na 2025-H1, potem ponowne uczenie na całym treningu z wybraną liczbą drzew. Model punktowy v2_lgbm_geo (P50) użył walidacji do wyboru liczby drzew (261). To jedna liczba i dotyczy P50, a nie granic przedziału. |
| P50 | wycena zapisanego v2_lgbm_geo, bez ponownego uczenia | P50 = ta sama wycena co w b4 i b1_bledy.md. Granice porządkujemy: P10 = min(dolna, P50), P90 = max(górna, P50). To może tylko poszerzyć przedział. |
| Metoda główna | CQR symetryczny, ustalony przed otwarciem testu | Wariant asymetryczny i stały przedział policzyliśmy w tym samym przebiegu, ale wybór na podstawie testu byłby dopasowaniem do testu. |
| Hiperparametry modeli kwantylowych | jak v2_lgbm_geo (`PARAMETRY` z v2_lightgbm), tylko `objective='quantile'`, `alpha` | Bez strojenia. Te same 19 cech: 6 bazowych (`KOLUMNY_CECH`) + 13 otoczenia i sąsiedztwa (`CECHY_DOMYSLNE`). |

## SQL i kod

Odtworzenie (z katalogu głównego repozytorium):

```bash
pypyr baza                                                                    # jeśli nie ma domilo.duckdb
cd api && poetry run python -m api.ai.valuation_model.evals.przedzialy_v2     # uczenie + walidacja + Katowice
# Test otwarto raz (2026-11-15) poleceniem z --otworz-test; skrypt odmawia ponownego otwarcia,
# bo versions/v2_lgbm_geo_cqr/metryki.json ma już wynik testu.
cd .. && pypyr test tests="api/tests/test_wycena_przedzial.py api/tests/test_wycena_modele.py"
```

Wyniki są deterministyczne (`deterministic=True`, `random_state=42`). Pełny wynik skryptu to tabele Markdown,
z których pochodzą tabele 1–10.

### Dane i podział

Transakcje z cechami jak w b4 (`wczytaj_transakcje_z_cechami`: `podzial.sql` + `geo.sql` + `sasiedztwo.sql`)
oraz typ budynku:

```sql
-- api/api/ai/features/wycena/podzial.sql (rdzeń)
CASE
    WHEN t.data_aktu >= TIMESTAMP '2023-01-01' AND t.data_aktu < TIMESTAMP '2025-07-01' THEN 'trening'
    WHEN t.data_aktu >= TIMESTAMP '2025-07-01' AND t.data_aktu < TIMESTAMP '2026-01-01' THEN 'walidacja'
    WHEN t.data_aktu >= TIMESTAMP '2026-01-01' AND t.data_aktu < TIMESTAMP '2026-07-01' THEN 'test'
END AS zbior
-- ... WHERE t.data_publikacji_rejestru < TIMESTAMP '2026-10-01'

SELECT id_transakcji, typ_budynku FROM rcn_transakcje;   -- tylko do segmentów, model jej nie dostaje
```

```python
tr, wal = df[df.zbior == "trening"], df[df.zbior == "walidacja"]
tr_ucz = tr[tr.data_aktu < "2025-01-01"]          # 30 812 transakcji
tr_odl = tr[tr.data_aktu >= "2025-01-01"]         # 7 710: wybór liczby drzew modeli kwantylowych
```

### Model (`api/api/ai/valuation_model/versions/v2_lgbm_geo_cqr/model.py`)

```python
def kwantyl_konformalny(wyniki, poziom):          # ⌈(n+1)·poziom⌉-ty najmniejszy
    w = np.sort(wyniki); k = ceil((len(w) + 1) * poziom)
    return inf if k > len(w) else w[k - 1]

def korekta_cqr(dolna, gorna, y, poziom=0.8):     # wszystko w ln(ceny)
    return kwantyl_konformalny(np.maximum(dolna - y, y - gorna), poziom)

def korekta_cqr_asymetryczna(dolna, gorna, y, poziom=0.8):
    return kwantyl_konformalny(dolna - y, 0.9), kwantyl_konformalny(y - gorna, 0.9)

class ModelPrzedzialuCQR(ModelWyceny):
    # modele kwantylowe: ModelLightGBMGeo z cechami modelu punktowego i parametrami
    #   {**punktowy.parametry, "objective": "quantile", "alpha": 0.1 | 0.9}
    def fit(X, y, X_odl, y_odl):  # wczesne zatrzymanie na X_odl -> drzewa; potem fit na X ∪ X_odl z tą liczbą drzew
    def kalibruj(X_kal, y_kal):   # korekta_ = korekta_cqr(ln q10(X_kal), ln q90(X_kal), ln y_kal)
    def predict_interval(X, metoda="cqr"):
        dolna, gorna = ln q10(X) - korekta_, ln q90(X) + korekta_
        p50 = punktowy.predict(X)
        return p10 = min(exp(dolna), p50), p50, p90 = max(exp(gorna), p50)
```

Przebieg (`przedzialy_v2.py`):

```python
punktowy = ModelWyceny.wczytaj("versions/v2_lgbm_geo/model.joblib")
model = ModelPrzedzialuCQR(punktowy).fit(tr_ucz, tr_ucz.cena_pln, tr_odl, tr_odl.cena_pln)
model.kalibruj(wal, wal.cena_pln)
# odniesienie: stały przedział z kwantyli błędu ln(y / P50) na walidacji (ten sam kwantyl konformalny, po ogonie)
r = np.log(wal.cena_pln / punktowy.predict(wal))
dol, gora = -kwantyl_konformalny(-r, 0.9), kwantyl_konformalny(r, 0.9)      # P10 = P50·e^dol, P90 = P50·e^gora
# metryki w grupach:
pokrycie = 100 * mean((y >= p10) & (y <= p90)); pod_P10 = 100 * mean(y < p10); nad_P90 = 100 * mean(y > p90)
szerokosc = 100 * median((p90 - p10) / p50)
# segmenty jak w b1_bledy.md:
segment_ceny   = pd.cut(cena_pln, [0, 300_000, 600_000, 1_000_000, inf], right=False)
segment_wyceny = pd.cut(p50,      [0, 300_000, 600_000, 1_000_000, inf], right=False)
metraz_grupa   = np.where(metraz < 30, "< 30 m²", "≥ 30 m²");  miesiac_aktu = data_aktu.dt.strftime("%Y-%m")
```

### Tabela 9: liczenie segmentów w normie

Z wyniku skryptu (tabele test: segment ceny, segment wyceny, miasto, typ budynku, metraż; bez wiersza „wszystkie”):

```python
for kolumna in ("pokrycie_przed", "pokrycie_CQR", "pokrycie_CQR_asym", "pokrycie_staly"):
    w_normie = sum(77 <= pokrycie <= 83 for segment in segmenty if segment != "wszystkie")
# wynik: przed 2, CQR 11, CQR asym. 17, stały 9 (z 20)
```

### Tabela 10: Katowice

Oferty i operaty jak w b1_bledy.md (`SQL_OFERTY` z `analiza_bledow_v2.py`; cechy na dzień wyceny przez `geo.sql` i
`sasiedztwo_punktow.sql`):

```sql
SELECT r.id_oferty AS id_transakcji, r.miasto, r.dzielnica, r.lat, r.lon, r.metraz, r.pokoje, r.pietro,
       r.rok_budowy, r.rynek, r.typ_budynku, r.cena_ofertowa, r.id_pakietu,
       coalesce(o.data_wyceny, r.data_publikacji)::DATE AS dzien_wyceny,
       o.id_operatu, o.wartosc_pln AS wartosc_operatu
FROM radar_oferty r
LEFT JOIN operaty o ON o.id_oferty = r.id_oferty AND o.typ = 'due_diligence'
WHERE r.data_publikacji >= TIMESTAMP '2026-06-01' AND r.data_publikacji < TIMESTAMP '2026-10-01';
```

```python
p = model.predict_interval(oferty)                       # CQR
szerokosc = 100 * (p.p90 - p.p10) / p.p50                # grupy: Katowice vs 6 miast z treningu
dd = oferty[oferty.id_operatu.notna()]                   # 40 operatów due diligence
w_przedziale = (dd.wartosc_operatu >= dd.p10) & (dd.wartosc_operatu <= dd.p90)
```
