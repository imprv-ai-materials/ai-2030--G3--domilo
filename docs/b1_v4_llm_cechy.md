# B1. v4_llm_cechy: cechy lokalu z opisu (LLM) w modelu wyceny

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw); cechy z LLM `gpt-6-luna`
(reasoning effort `none`, temperatura 0). Policzono 2026-11-15 skryptami `ekstrakcja_llm.py` (ekstrakcja) i
`ewaluacja_v4.py` (model i tabele). Numery tabel odpowiadają sekcjom z wydruku `ewaluacja_v4.py`.
Podział jak w `docs/b1_dane.md`: trening 2023-01 – 2025-06, walidacja 2025-07 – 2025-12, test 2026-01 – 2026-06
według `data_aktu`, target `rcn_transakcje.cena_pln`. Operaty kontrolne: `operaty.wartosc_pln`, typ `kontrolny`.

**Reguła wyboru ustalona przed uczeniem v4:** v4 trafia do `current.yaml`, jeśli MAPE jej P50 (bez odmów) na 300
operatach kontrolnych jest niższe niż MAPE obecnej wersji (`v1_liniowa`) na tych samych 300 lokalach.

## Wnioski

1. Cechy odczytane przez LLM z opisu (standard wykończenia, ekspozycja, widok, balkon, stan budynku) poprawiają
   wycenę lokali Domilo. Na 300 operatach kontrolnych błąd v4 wynosi 5,4% wobec 7,1% obecnej v1 i 5,9% v3 bez
   tych cech. Zgodnie z regułą v4 jest teraz wersją w `current.yaml`. Mieści się w warunkach banku
   (MAPE ≤ 8%, pokrycie przedziału 79,0% w normie 77–83%).
2. Zysk pojawia się tylko tam, gdzie jest opis. Na 2 882 testowych transakcjach z dopasowanym ogłoszeniem
   MAPE spada z 8,97% (v2) do 8,26%, a na transakcjach bez ogłoszenia praktycznie się nie zmienia (8,28% → 8,33%).
   Gdy wyłączymy odczyty LLM dla lokali Domilo, błąd na operatach rośnie z 5,40% do 6,02%. Poprawa pochodzi więc
   z opisów, a nie z innego uczenia modelu.
3. Odczyt standardu ze zdjęć nie pomaga: prawie zawsze daje „3” (80–87% lokali) i pogarsza wycenę o 0,7–0,9
   punktu procentowego. Nie używamy go.
4. Ekstrakcja kosztuje na 1 000 opisów około 1,66 mln tokenów wejścia (z tego 1,51 mln OpenAI odczytuje ze swojego
   cache promptu) i 59–60 tys. tokenów wyjścia. Na 1 000 lokali ze zdjęciami (po 4 zdjęcia) wychodzi 3,42 mln
   tokenów wejścia (1,30 mln z cache) i 61 tys. wyjścia, a czas to około 1,5 minuty przy 16 wątkach. Kwoty w złotych
   nie podaję: cennika `gpt-6-luna` nie ma w danych (pytanie 1).
5. Ryzyko: opisy Domilo piszą o lokalach inaczej niż ogłoszenia sprzedaży. Nie mają standardu 1–2 ani widoku, a lokale
   bez balkonu dostają „brak_info” zamiast „nie”. Wynik na operatach jest dobry, ale opiera się na cechach o innym
   rozkładzie niż w treningu (tabela 2).

## Tabele

### Zbiory: liczby z danych a liczby z polecenia

| Zbiór | W poleceniu | W danych (użyte) | Dlaczego inaczej |
|---|---:|---:|---|
| testowe dopasowania | 3 000 | 2 882 | 3 000 transakcji z aktem od 2026-01 ma dopasowaną ofertę, ale 118 opublikowano w RCN po dniu eksportu; podział (`podzial.sql`) ich nie obejmuje |
| testowe oferty ze zdjęciami | 1 200 | 1 200 odczytanych, 1 146 ocenianych | 1 148 z nich jest w teście (reszta to te same 118 publikacji po eksporcie); 2 oferty bez odczytu standardu ze zdjęć |
| lokale Domilo ze zdjęciami | 300 | 300 (298 z odczytem standardu) | to dokładnie lokale z operatem kontrolnym |
| dopasowane transakcje (opisy) | 20 500 | 20 500 | — |
| lokale Domilo (opisy) | 7 200 | 7 200 | — |

Zapytanie kontrolne: [`SQL` → „Zbiory”](#sql-i-kod).

### Ekstrakcja: tokeny i czas (tabela 7 i wydruk `ekstrakcja_llm.py`)

Opisy przed wysłaniem do LLM są bez zdań z kwotą (`bez_kwot`): ceny, ceny za m², raty, obniżki i czynszu najmu
(zmienionych opisów: 19 499 z 20 500 ofert i 5 811 z 7 200 lokali Domilo; po czyszczeniu w żadnym nie została kwota).

| Zbiór | Prompt | Rekordy | Błędy | Tokeny wejścia | W tym z cache OpenAI | Tokeny wyjścia | Czas (16 wątków) |
|---|---|---:|---:|---:|---:|---:|---:|
| opisy ofert (dopasowania) | cechy_lokalu_v1 | 20 500 | 0 | 34 081 894 | 31 032 458 | 1 212 132 | 1 788,7 s |
| opisy Domilo | cechy_lokalu_v1 | 7 200 | 0 | 11 708 374 | 10 900 800 | 435 048 | 609,1 s |
| zdjęcia ofert (okres testu) | cechy_lokalu_zdjecia_v1 | 1 200 | 0 | 4 103 796 | 1 564 479 | 73 086 | 123,0 s |
| zdjęcia Domilo | cechy_lokalu_zdjecia_v1 | 300 | 0 | 1 025 906 | 392 100 | 18 277 | 31,1 s |

Na 1 000 rekordów:

| Ekstrakcja | Tokeny wejścia | W tym z cache OpenAI | Wejście bez cache | Tokeny wyjścia | Czas (16 wątków) |
|---|---:|---:|---:|---:|---:|
| 1 000 opisów ogłoszeń | 1 662 531 | 1 514 000 | 148 531 | 59 128 | 87,3 s |
| 1 000 opisów Domilo | 1 626 163 | 1 514 000 | 112 163 | 60 423 | 84,6 s |
| 1 000 lokali ze zdjęciami (ogłoszenia, 4 zdjęcia) | 3 419 830 | 1 303 732 | 2 116 098 | 60 905 | 102,5 s |
| 1 000 lokali ze zdjęciami (Domilo, 4 zdjęcia) | 3 419 687 | 1 307 000 | 2 112 687 | 60 923 | 103,7 s |

Koszt w zł = (wejście bez cache × cena wejścia + wejście z cache × cena wejścia z cache + wyjście × cena wyjścia)
/ 1 000 000. Cennika nie ma w danych, więc wyniku w zł nie podaję. Instrukcja promptu (około 1,5 tys. tokenów) jest
wspólna dla wszystkich zapytań, dlatego OpenAI czyta ją z cache. Przy zdjęciach większość wejścia to obrazy
(`detail: high`).

### 1. Pokrycie cech LLM

| Zbiór | Lokale | Z odczytem opisu | Standard z opisu (nie null) | Standard ze zdjęć |
|---|---:|---:|---:|---:|
| trening: dopasowania | 14 361 | 14 361 | 10 997 | 0 |
| test: dopasowania | 2 882 | 2 882 | 2 166 | 1 146 |
| test: dopasowania ze zdjęciami | 1 146 | 1 146 | 861 | 1 146 |
| operaty kontrolne (lokale Domilo) | 300 | 300 | 222 | 298 |

W treningu cechy LLM ma 14 361 z 38 522 transakcji, czyli te z dopasowanym ogłoszeniem. Pozostałe dostają brak
(NaN), a LightGBM prowadzi je osobną gałęzią.

### 2. Rozkład odczytów LLM (% lokali z odczytem)

| Cecha | Wartość | Trening: dopasowania | Test: dopasowania | Test: ze zdjęciami | Operaty kontrolne |
|---|---|---:|---:|---:|---:|
| standard (opis) | 1 | 11,8 | 10,4 | 10,3 | 0,0 |
| | 2 | 12,9 | 13,8 | 14,0 | 0,0 |
| | 3 | 26,7 | 24,9 | 23,9 | 36,7 |
| | 4 | 18,2 | 18,7 | 19,3 | 35,7 |
| | 5 | 7,0 | 7,4 | 7,7 | 1,7 |
| | null | 23,4 | 24,8 | 24,9 | 26,0 |
| standard (zdjęcia) | 1 | — | 1,9 | 1,9 | 0,0 |
| | 2 | — | 3,8 | 3,8 | 0,3 |
| | 3 | — | 80,0 | 80,0 | 87,2 |
| | 4 | — | 14,2 | 14,2 | 12,4 |
| balkon | tak | 54,2 | 54,6 | 52,7 | 67,0 |
| | nie | 24,8 | 24,0 | 23,6 | 0,0 |
| | brak_info | 21,1 | 21,4 | 23,6 | 33,0 |
| ekspozycja | brak_info | 44,3 | 44,9 | 46,4 | 0,0 |
| | (8 kierunków, każdy) | 6,7–7,2 | 6,2–7,4 | 5,4–7,9 | 9,7–15,0 |
| widok | brak_info | 65,2 | 65,5 | 67,1 | 100,0 |
| | podworze / ulica / park / woda | 16,0 / 15,6 / 2,2 / 0,9 | 14,9 / 16,6 / 2,2 / 0,9 | 15,0 / 14,9 / 2,1 / 0,9 | 0 / 0 / 0 / 0 |
| stan budynku | brak_info | 63,5 | 64,6 | 64,3 | 98,7 |
| | zadbany / nowy | 30,8 / 5,7 | 31,0 / 4,4 | 32,0 / 3,7 | 0,0 / 1,3 |

Dla wszystkich 7 200 lokali Domilo (wydruk 2b): ekspozycja z LLM zgadza się z `pms_lokale.ekspozycja`
w 100%. Balkon „tak” odpowiada balkonowi albo tarasowi z PMS (4 739 lokali). Lokale bez balkonu (1 958) i z ogródkiem
(503) mają „brak_info”, bo opis nic o tym nie mówi. Standard z opisu nie przekłada się jednoznacznie na
`pakiet_wykonczenia`:

| Pakiet (PMS) | Standard null | 3 | 4 | 5 | Razem |
|---|---:|---:|---:|---:|---:|
| A | 474 | 256 | 1 958 | 22 | 2 710 |
| B | 1 158 | 2 123 | 238 | 24 | 3 543 |
| C | 207 | 275 | 251 | 214 | 947 |

### 3. Standard z opisu a standard ze zdjęć

| Zbiór | Ze zdjęciami | Standard w obu | Zgodne | Różnica ≤ 1 | Zdjęcia wyżej | Zdjęcia niżej | Średnia: opis | Średnia: zdjęcia |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| test: dopasowania ze zdjęciami | 1 146 | 861 | 41,9% | 89,9% | 26,8% | 31,2% | 3,00 | 3,06 |
| operaty kontrolne | 298 | 221 | 59,7% | 100% | 0,0% | 40,3% | 3,53 | 3,13 |

Standard ze zdjęć Domilo nie zależy od pakietu wykończenia: A to 85 × „3” i 23 × „4”, B 152 × „3”, 4 × „4” i
1 × „2”, C 23 × „3” i 10 × „4”. Odczyt ze zdjęć niewiele mówi o różnicach w standardzie. 95% odczytów ze zdjęć ofert
ma pewność „średnią” (1 141 z 1 200).

### 4. Metryki: v4 a v2/v3 na tych samych lokalach

MAPE, MdAPE, mediana błędu ze znakiem, MAE, pokrycie przedziału 80% i jego mediana szerokości liczone na przyjętych.
„bez odmów” = P50 i przedział bez detektora. Wiersze „+ standard ze zdjęć” podstawiają standard ze zdjęć tam, gdzie
jest. Ablacja = v4 z cechami LLM ustawionymi na brak.

| Model | Zbiór | n | Odmowy | MAPE | MdAPE | Mediana błędu | MAE | Pokrycie 80% | Szerokość |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v0_mediana_dzielnicy (baseline) | **test: dopasowania** | 2 882 | 0,0% | 13,89% | 11,48% | −6,67% | 86 028 zł | — | — |
| v1_liniowa | test: dopasowania | 2 882 | 0,0% | 10,65% | 8,61% | −6,48% | 65 581 zł | — | — |
| **v2_lgbm_geo** (= P50 v3) | test: dopasowania | 2 882 | 0,0% | 8,97% | 6,63% | −4,60% | 52 334 zł | — | — |
| v3_przedzialy bez odmów | test: dopasowania | 2 882 | 0,0% | 8,97% | 6,63% | −4,60% | 52 334 zł | 77,0% | 24,0% |
| v3_przedzialy | test: dopasowania | 2 882 | 5,7% | 8,97% | 6,56% | −4,59% | 51 043 zł | 77,5% | 23,8% |
| **v4_llm_cechy bez odmów** | test: dopasowania | 2 882 | 0,0% | **8,26%** | 5,99% | −3,98% | 47 364 zł | 76,4% | 21,5% |
| v4_llm_cechy | test: dopasowania | 2 882 | 5,7% | 8,33% | 6,00% | −3,97% | 46 555 zł | 76,5% | 21,4% |
| v2_lgbm_geo | test: dopasowania ze zdjęciami | 1 146 | 0,0% | 8,63% | 6,66% | −4,43% | 51 684 zł | — | — |
| v4_llm_cechy bez odmów | test: dopasowania ze zdjęciami | 1 146 | 0,0% | 7,89% | 6,06% | −4,13% | 46 778 zł | 76,6% | 21,5% |
| v4 + standard ze zdjęć, bez odmów | test: dopasowania ze zdjęciami | 1 146 | 0,0% | 8,56% | 6,62% | −4,33% | 52 072 zł | 72,0% | 21,4% |
| v4, cechy LLM = brak (ablacja) | test: dopasowania ze zdjęciami | 1 146 | 0,0% | 8,61% | 6,64% | −4,65% | 52 055 zł | 77,5% | 24,8% |
| v2_lgbm_geo | test: bez dopasowania | 4 605 | 0,0% | 8,28% | 6,40% | −4,41% | 49 418 zł | — | — |
| v3_przedzialy | test: bez dopasowania | 4 605 | 5,6% | 8,21% | 6,33% | −4,38% | 47 751 zł | 78,2% | 23,7% |
| v4_llm_cechy bez odmów | test: bez dopasowania | 4 605 | 0,0% | 8,33% | 6,49% | −4,53% | 49 981 zł | 78,6% | 24,7% |
| v4_llm_cechy | test: bez dopasowania | 4 605 | 5,6% | 8,25% | 6,41% | −4,50% | 48 309 zł | 78,8% | 24,6% |
| v0_mediana_dzielnicy (baseline) | test: wszystkie | 7 487 | 0,0% | 13,40% | 11,28% | −6,43% | 83 401 zł | — | — |
| v1_liniowa | test: wszystkie | 7 487 | 0,0% | 10,17% | 8,30% | −6,35% | 63 252 zł | — | — |
| v2_lgbm_geo | test: wszystkie | 7 487 | 0,0% | 8,55% | 6,49% | −4,46% | 50 540 zł | — | — |
| v3_przedzialy | test: wszystkie | 7 487 | 5,6% | 8,50% | 6,41% | −4,44% | 49 018 zł | 77,9% | 23,7% |
| v4_llm_cechy bez odmów | test: wszystkie | 7 487 | 0,0% | 8,30% | 6,28% | −4,28% | 48 974 zł | 77,8% | 23,6% |
| v4_llm_cechy | test: wszystkie | 7 487 | 5,6% | 8,28% | 6,24% | −4,27% | 47 634 zł | 77,9% | 23,5% |
| v0_mediana_dzielnicy (baseline) | **operaty kontrolne** | 300 | 0,0% | 13,39% | 13,29% | −13,29% | 115 192 zł | — | — |
| v1_liniowa (current przed v4) | operaty kontrolne | 300 | 0,0% | 7,14% | 6,29% | −5,37% | 63 542 zł | — | — |
| v2_lgbm_geo (= P50 v3) | operaty kontrolne | 300 | 0,0% | 5,90% | 4,99% | −3,15% | 51 994 zł | — | — |
| v3_przedzialy | operaty kontrolne | 300 | 1,0% | 5,89% | 5,00% | −3,16% | 51 935 zł | 82,2% | 21,8% |
| **v4_llm_cechy bez odmów** | operaty kontrolne | 300 | 0,0% | **5,40%** | 4,50% | −2,77% | 47 843 zł | 79,0% | 17,9% |
| v4_llm_cechy | operaty kontrolne | 300 | 1,0% | 5,39% | 4,48% | −2,79% | 47 815 zł | 78,8% | 17,9% |
| v4 + standard ze zdjęć, bez odmów | operaty kontrolne | 300 | 0,0% | 6,33% | 5,59% | −4,93% | 56 353 zł | 74,7% | 18,5% |
| v4, cechy LLM = brak (ablacja) | operaty kontrolne | 300 | 0,0% | 6,02% | 4,96% | −3,20% | 53 542 zł | 83,0% | 23,0% |

Na testowych dopasowaniach pokrycie przedziału v4 wynosi 76,4%, czyli trochę poniżej normy 77%. Węższy przedział
(21,5% wobec 24,0%) nie skompensował się tam w całości. Na całym teście (77,8%) i na operatach (79,0%) pokrycie
mieści się w normie.

### 5. Różnice MAPE: bootstrap par (te same lokale, 2 000 prób, P50 bez odmów)

| Zbiór | Model | Względem | Różnica MAPE | 95% CI |
|---|---|---|---:|---|
| test: dopasowania | v4 | v2_lgbm_geo | −0,71 pp | −0,81 … −0,60 |
| test: wszystkie | v4 | v2_lgbm_geo | −0,24 pp | −0,29 … −0,20 |
| operaty kontrolne | v4 | v2_lgbm_geo | −0,50 pp | −0,75 … −0,23 |
| operaty kontrolne | v4 | v1_liniowa | −1,74 pp | −2,22 … −1,29 |
| operaty kontrolne | v4 | v4, cechy LLM = brak | −0,62 pp | −0,87 … −0,37 |
| operaty kontrolne | v4 + standard ze zdjęć | v4 | +0,93 pp | +0,65 … +1,22 |
| test: dopasowania ze zdjęciami | v4 + standard ze zdjęć | v4 | +0,67 pp | +0,50 … +0,86 |

### 6. Ważność cech v4 (P50, gain)

| Cecha | Udział | Cecha | Udział |
|---|---:|---|---:|
| metraz | 72,78% | llm_standard | 0,22% |
| dzielnica | 14,35% | odl_centrum_m | 0,18% |
| sasiedzi_mediana_ceny_m2 | 7,46% | odl_park_m | 0,15% |
| rok_budowy | 4,01% | llm_ekspozycja, llm_balkon, llm_stan_budynku | po 0,01% |
| pietro | 0,31% | llm_widok | 0,00% |
| odl_stacja_m | 0,30% | pozostałe | ≤ 0,07% |

Gain jest mały, bo cechy LLM ma tylko 37% transakcji treningowych (14 361 z 38 522), a gain sumuje się po wszystkich
podziałach. Wpływ cech pokazuje ablacja z tabeli 5 (−0,62 pp na operatach), a nie ten ranking (por.
`docs/b1_przeciek_opisu.md`, tabela 4c).

### Składniki v4

v4: P50 z 266 drzewami, P10/P90 z 1 320 / 323 drzewami, korekta CQR 0,0156 (v3: 0,0153). Detektor jest ten sam co
w v3 (`versions/v3_przedzialy/ood.joblib`, ten sam obiekt, bez ponownego uczenia). Odmowy: test 5,6%,
operaty 1,0%.

## SQL i kod

Pliki:
- `api/api/ai/features/wycena/ceny_w_opisie.py`: `bez_kwot` (zdania z kwotą usuwane przed LLM);
- `api/api/ai/features/wycena/cechy_llm.py`: `wyciagnij` (równolegle, przez `KlientLLM` z cache) i `cechy_do_modelu`;
- `api/api/ai/features/wycena/ekstrakcja_llm.py`: zbiory i ekstrakcja, wyniki w
  `api/api/ai/features/wycena/cechy_llm/{opisy_ofert,opisy_domilo,zdjecia_ofert,zdjecia_domilo}.parquet`;
- `api/api/ai/llm/prompts/cechy_lokalu_v1.yaml` (opisy), `cechy_lokalu_zdjecia_v1.yaml` (zdjęcia), ten sam schemat
  `api/api/ai/llm/schemas/cechy_lokalu.py`;
- `api/api/adapters/llm_client.py`: zdjęcia jako data URL (`detail: high`), tokeny z cache OpenAI, klucz cache
  = sha256(wersja promptu + tekst + skróty sha256 zdjęć);
- `api/api/ai/valuation_model/versions/v4_llm_cechy/model.py`: `ModelWycenyV4` (v3 + cechy LLM, gotowy detektor);
- `api/api/ai/valuation_model/evals/ewaluacja_v4.py`: uczenie, tabele 1–8, `versions/v4_llm_cechy/model.joblib`
  i `metryki.json`;
- testy: `api/tests/test_llm_cechy_lokalu.py`, `test_wycena_cechy_llm.py`, `test_wycena_v4.py`.

Uruchomienie (z katalogu głównego):

```bash
set -a && . ./.env && set +a
cd api && poetry run python -m api.ai.features.wycena.ekstrakcja_llm      # ekstrakcja (drugie uruchomienie czyta cache)
poetry run python -m api.ai.valuation_model.evals.ewaluacja_v4            # bez klucza: czyta tylko pliki parquet
```

Zbiory do ekstrakcji (`ekstrakcja_llm.py`):

```sql
-- opisy ofert (20 500)
SELECT o.id_oferty AS id, o.opis AS tekst FROM radar_dopasowania d JOIN radar_oferty o USING (id_oferty)
ORDER BY o.id_oferty;
-- opisy Domilo (7 200)
SELECT id_lokalu AS id, opis_marketingowy AS tekst FROM lokale_domilo_opisy ORDER BY id_lokalu;
-- zdjęcia ofert z okresu testu (1 200)
SELECT m.id_oferty AS id, list(m.pomieszczenie ORDER BY m.sciezka) AS pomieszczenia,
       list(m.sciezka ORDER BY m.sciezka) AS sciezki
FROM metadane m JOIN radar_dopasowania d USING (id_oferty) JOIN rcn_transakcje t USING (id_transakcji)
WHERE t.data_aktu >= TIMESTAMP '2026-01-01'
GROUP BY m.id_oferty ORDER BY m.id_oferty;
-- zdjęcia Domilo (300)
SELECT id_lokalu AS id, list(pomieszczenie ORDER BY sciezka) AS pomieszczenia, list(sciezka ORDER BY sciezka) AS sciezki
FROM metadane WHERE id_lokalu IS NOT NULL GROUP BY id_lokalu ORDER BY id_lokalu;
```

Zbiory (liczby z tabeli „Zbiory”; `p` = `podzial.sql`, `zd` = oferty ze zdjęciami, `zl` = lokale ze zdjęciami):

```sql
WITH p AS (/* podzial.sql */),
zd AS (SELECT id_oferty, count(*) n FROM metadane WHERE id_oferty IS NOT NULL GROUP BY 1),
zl AS (SELECT id_lokalu, count(*) n FROM metadane WHERE id_lokalu IS NOT NULL GROUP BY 1)
SELECT
 (SELECT count(*) FROM radar_dopasowania d JOIN p USING (id_transakcji) WHERE zbior = 'test') AS dop_test,           -- 2 882
 (SELECT count(*) FROM radar_dopasowania d JOIN rcn_transakcje t USING (id_transakcji)
   WHERE t.data_aktu >= '2026-01-01') AS dop_akt_2026_bez_filtra_publikacji,                                       -- 3 000
 (SELECT count(*) FROM zd JOIN radar_dopasowania d USING (id_oferty) JOIN p USING (id_transakcji)
   WHERE zbior = 'test') AS oferty_zdj_test,                                                                        -- 1 148
 (SELECT count(*) FROM zl JOIN operaty o USING (id_lokalu) WHERE o.typ = 'kontrolny') AS lokale_zdj_kontrolne;      -- 300
```

Cechy dla modelu (`ewaluacja_v4.wczytaj_dane`): transakcje z `wczytaj_transakcje_z_cechami` (geo i sąsiedztwo jak v3)
+ `radar_dopasowania` (id_oferty) + `opisy_ofert.parquet` po `id_oferty`. Lokale Domilo: `wczytaj_lokale_domilo`
(`ood_v3.py`: cechy budynku z `pms_budynki`, sąsiedzi znani 2026-10-01) + `opisy_domilo.parquet` po `id_lokalu`
+ operaty:

```sql
SELECT id_lokalu, id_operatu, data_wyceny, wartosc_pln FROM operaty WHERE typ = 'kontrolny';
```

PMS a LLM (tabela pod nr 2, wydruk 2b; `ewaluacja_v4.porownanie_z_pms`): odczyty z `opisy_domilo.parquet` i
`zdjecia_domilo.parquet` złączone po `id_lokalu` z

```sql
SELECT id_lokalu AS id, pakiet_wykonczenia, ekspozycja AS ekspozycja_pms, balkon AS balkon_pms FROM pms_lokale;
```

i zestawione tabelą krzyżową (`pd.crosstab`, null = brak odczytu standardu).

Bootstrap par (`bootstrap_roznicy_mape`): 2 000 losowań lokali ze zwracaniem (ziarno 42), MAPE(a) − MAPE(b) na tej
samej próbie, przedział = kwantyle 2,5% i 97,5%.
