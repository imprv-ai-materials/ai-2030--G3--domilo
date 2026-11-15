# Cechy lokalu z opisu ogłoszenia (LLM, prompt `cechy_lokalu_v1`): stabilność odpowiedzi

Model `gpt-6-luna` (OpenAI), reasoning effort `none`, temperatura 0 (API ją przyjęło, cache zapisuje `temperatura: 0`).
Próba: 200 losowych opisów z `radar_oferty` (ziarno 42). Każdy opis wysłano 5 razy z pominięciem cache.
Uruchomienie z 2026-11-15.

## Wnioski

1. Dla 189 z 200 opisów (94,5%) wszystkie 5 odpowiedzi były identyczne co do znaku, a żadne z 1 000 wywołań nie
   skończyło się błędem. Temperatura 0 nie gwarantuje jednak powtarzalności: co 18–19 opis model raz odpowiada
   tak, raz inaczej.
2. Cechy podane w opisie wprost (balkon, ekspozycja, widok) były w 100% stabilne. Wahania dotyczą tylko pól,
   które wymagają oceny: `pewnosc` (10 opisów), `standard_1_5` (6 opisów) i `stan_budynku` (1 opis).
3. Wahania standardu mają jedną przyczynę: zdanie „Mieszkanie zadbane: panele, glazura w łazience, zabudowa kuchenna
   sprzed kilku lat”, którego prompt v1 nie przypisuje do żadnego poziomu skali. W próbie 6 z 11 opisów z tym
   zdaniem dostało raz `3`, raz `null`. Zdanie występuje w 10 110 ze 176 859 ofert, więc łatkę warto dodać w v2.
4. Pole `pewnosc` jest najmniej stabilne. Model obniża ją m.in. za sprzeczności dotyczące windy („Budynek bez windy”
   i „Winda w budynku” w jednym opisie, 2 961 ofert), choć windy nie ma w schemacie. Zanim `pewnosc` stanie się
   filtrem w wycenie, trzeba ją w v2 zawęzić do pól schematu.
5. Badaliśmy tylko powtarzalność, a nie trafność: stabilna odpowiedź może być stabilnie błędna. Zanim cechy
   trafią do modelu wyceny, trzeba je porównać z prostą regułą słownikową (baseline) na ręcznie sprawdzonej próbce.

## Tabele

### Odsetek opisów z identyczną odpowiedzią we wszystkich 5 przebiegach

| zakres | identyczne | opisów | odsetek |
|---|---:|---:|---:|
| cała odpowiedź (wszystkie pola) | 189 | 200 | 0,945 |
| surowy tekst JSON z API | 189 | 200 | 0,945 |
| balkon | 200 | 200 | 1,000 |
| ekspozycja | 200 | 200 | 1,000 |
| widok | 200 | 200 | 1,000 |
| stan_budynku | 199 | 200 | 0,995 |
| standard_1_5 | 194 | 200 | 0,970 |
| pewnosc | 190 | 200 | 0,950 |

Błędne wywołania: 0 z 1 000. Tokeny łącznie (5 × 200 wywołań): wejście 1 665 535, wyjście 59 093.
Kosztu w zł nie podaję, bo cennika nie ma w danych.

### Liczba różnych odpowiedzi na opis

| różnych odpowiedzi w 5 przebiegach | opisów |
|---:|---:|
| 1 | 189 |
| 2 | 10 |
| 3 | 1 |

### Opisy niestabilne: warianty odpowiedzi (pola, które się różniły)

| id_oferty | standard_1_5 | stan_budynku | pewnosc | przebiegów | przyczyna w opisie |
|---|---|---|---|---:|---|
| O006134 | 5 | brak_info | wysoka | 3 | „Nowoczesny apartamentowiec (2019)” — nowy czy brak oceny? |
| O006134 | 5 | nowy | wysoka | 2 | |
| O022962 | null | brak_info | wysoka | 3 | „Mieszkanie zadbane: panele…” |
| O022962 | 3 | brak_info | srednia | 2 | |
| O027266 | 4 | zadbany | srednia | 3 | tylko `pewnosc` |
| O027266 | 4 | zadbany | wysoka | 2 | |
| O068488 | 3 | zadbany | srednia | 3 | „Mieszkanie zadbane: panele…” |
| O068488 | null | zadbany | wysoka | 2 | |
| O077212 | null | brak_info | wysoka | 3 | sprzeczność: „Budynek bez windy” + „Winda w budynku” |
| O077212 | null | brak_info | niska | 2 | |
| O096371 | 3 | brak_info | niska | 4 | sprzeczność: „Budynek bez windy” + „Winda w budynku” |
| O096371 | 3 | brak_info | wysoka | 1 | |
| O100540 | null | zadbany | wysoka | 3 | „Mieszkanie zadbane: panele…” |
| O100540 | 3 | zadbany | srednia | 2 | |
| O117524 | null | brak_info | wysoka | 4 | „Mieszkanie zadbane: panele…” |
| O117524 | 3 | brak_info | srednia | 1 | |
| O138011 | 4 | zadbany | wysoka | 4 | tylko `pewnosc` |
| O138011 | 4 | zadbany | srednia | 1 | |
| O147102 | 3 | brak_info | srednia | 2 | „Mieszkanie zadbane: panele…” |
| O147102 | null | brak_info | wysoka | 2 | |
| O147102 | 3 | brak_info | wysoka | 1 | |
| O170121 | null | brak_info | wysoka | 4 | „Mieszkanie zadbane: panele…” |
| O170121 | 3 | brak_info | srednia | 1 | |

Przyczyny dla O006134, O022962, O068488, O077212, O096371 i O100540 sprawdziłem na treści opisu (zapytanie 4).
Dla pozostałych przypisałem je według frazy z zapytania 3.

### Stabilność standardu a zdanie spoza skali promptu

| opis zawiera „Mieszkanie zadbane: panele” | opisów | niestabilny standard | niestabilna odpowiedź |
|---|---:|---:|---:|
| nie | 189 | 0 | 5 |
| tak | 11 | 6 | 6 |

### Częstość wzorców w całym `radar_oferty`

| ofert | „Mieszkanie zadbane: panele” | sprzeczna informacja o windzie | „Nowoczesny apartamentowiec” |
|---:|---:|---:|---:|
| 176 859 | 10 110 | 2 961 | 2 479 |

## SQL i kod

Pliki:
- schemat: `api/api/ai/llm/schemas/cechy_lokalu.py` (`CechyLokalu`, `extra="forbid"`, bez pól na kwoty);
- prompt: `api/api/ai/llm/prompts/cechy_lokalu_v1.yaml`, wczytywany przez `api/api/ai/llm/prompty.py`;
- klient: `api/api/adapters/llm_client.py` (`KlientLLM.zapytaj`). Cache: `api/api/ai/llm/cache/<sha256(wersja + "\n" + opis)>.json`;
- eksperyment: `api/api/ai/llm/evals/stabilnosc_cechy_lokalu.py`, surowe odpowiedzi:
  `api/api/ai/llm/evals/wyniki/stabilnosc_cechy_lokalu_v1.parquet` (kolumny: przebieg, id_oferty, dane, surowy_tekst,
  tokeny_wejscia, tokeny_wyjscia, blad);
- testy: `api/tests/test_llm_cechy_lokalu.py`.

Uruchomienie (klucz trafia tylko do zmiennej środowiskowej, klient nie czyta `.env`):

```bash
set -a && . ./.env && set +a
cd api && poetry run python -m api.ai.llm.evals.stabilnosc_cechy_lokalu
```

Losowanie próby (`losuj_opisy`): oferty posortowane po `id_oferty`, potem
`numpy.random.default_rng(42).choice(176859, size=200, replace=False)`:

```sql
SELECT id_oferty, opis FROM radar_oferty ORDER BY id_oferty
```

Przebieg 1 zapisuje odpowiedzi do cache, przebiegi 2–5 nie. Wszystkie pięć pomija odczyt cache
(`czytaj_cache=False`), bo inaczej przebiegi 2–5 byłyby kopią pierwszego. Zgodność liczy `zgodnosc_przebiegow`:
opis jest „identyczny”, gdy wszystkie 5 odpowiedzi (cały słownik albo jedno pole) jest równych. Błąd wywołania
liczy się jako różna odpowiedź.

Zapytania do tabel z analizy (DuckDB CLI, z katalogu głównego; `W` = plik wyników):

```sql
-- 1. Warianty odpowiedzi dla opisów niestabilnych
CREATE TEMP TABLE w AS SELECT przebieg, id_oferty, dane::JSON AS d FROM 'api/api/ai/llm/evals/wyniki/stabilnosc_cechy_lokalu_v1.parquet';
SELECT id_oferty, d->>'standard_1_5' std, d->>'stan_budynku' bud, d->>'pewnosc' pew, count(*) n_przebiegow
FROM w WHERE id_oferty IN (SELECT id_oferty FROM w GROUP BY 1 HAVING count(DISTINCT d::VARCHAR) > 1)
GROUP BY ALL ORDER BY 1, 5 DESC;

-- 2. Liczba różnych odpowiedzi na opis
SELECT warianty, count(*) opisow FROM (SELECT id_oferty, count(DISTINCT d::VARCHAR) warianty FROM w GROUP BY 1)
GROUP BY 1 ORDER BY 1;

-- 3. Stabilność standardu a zdanie „Mieszkanie zadbane: panele” (coalesce, bo count(DISTINCT) pomija NULL)
WITH w AS (SELECT id_oferty, count(DISTINCT dane) warianty,
                  count(DISTINCT coalesce(dane::JSON->>'standard_1_5', 'null')) warianty_std
           FROM 'api/api/ai/llm/evals/wyniki/stabilnosc_cechy_lokalu_v1.parquet' GROUP BY 1)
SELECT (o.opis LIKE '%Mieszkanie zadbane: panele%') AS fraza_zadbane_panele, count(*) opisow,
       count(*) FILTER (WHERE warianty_std > 1) niestabilny_standard,
       count(*) FILTER (WHERE warianty > 1) niestabilna_odpowiedz
FROM w JOIN 'data/radar/radar_oferty.parquet' o USING (id_oferty) GROUP BY 1 ORDER BY 1;

-- 4. Treść opisów niestabilnych
SELECT id_oferty, opis FROM 'data/radar/radar_oferty.parquet'
WHERE id_oferty IN ('O022962','O068488','O100540','O006134','O077212','O096371');

-- 5. Częstość wzorców w całym radar_oferty
SELECT count(*) AS ofert,
  count(*) FILTER (WHERE opis LIKE '%Mieszkanie zadbane: panele%') AS zadbane_panele,
  count(*) FILTER (WHERE opis LIKE '%Budynek bez windy%' AND (opis LIKE '%Winda w budynku%'
                   OR opis LIKE '%Budynek z windą%' OR opis LIKE '%W budynku jest winda%')) AS sprzeczna_winda,
  count(*) FILTER (WHERE opis LIKE '%Nowoczesny apartamentowiec%') AS nowoczesny_apartamentowiec
FROM 'data/radar/radar_oferty.parquet';
```

Tokeny i błędy wypisuje sam skrypt (suma `tokeny_wejscia`, `tokeny_wyjscia`, liczba niepustych `blad`).
