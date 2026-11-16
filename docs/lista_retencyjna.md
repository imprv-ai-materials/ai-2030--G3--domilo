# Cotygodniowa lista retencyjna (zadanie `lista-retencyjna`)

Stan: 2026-11-16. Kod: [`retention_bc/lista_retencyjna.py`](../api/api/contexts_boundaries/retention_bc/lista_retencyjna.py),
tabela: [`adapters/lista_retencyjna.py`](../api/api/adapters/lista_retencyjna.py), funkcja Inngest w
[`inngest_app.py`](../api/api/inngest_app.py), testy: `api/tests/test_lista_retencyjna.py`.

## Wnioski

1. **W każdy poniedziałek o 07:00 zadanie bierze umowy, które kończą się za 60–66 dni,** liczy dla nich ryzyko
   odejścia, spodziewany czas najmu, efekt oferty (uplift) i zalecaną akcję, losuje grupę kampanii i zapisuje
   wszystko w tabeli `lista_retencyjna`. Kolejne poniedziałki obejmują każdy dzień końca umowy dokładnie raz.
2. **Dwa przebiegi dla 2026-11-16 na tych samych danych dały identyczną listę:** 132 umowy, te same grupy
   (26 w kontroli, 106 w polityce) i te same wartości w każdym wierszu. Różni się tylko identyfikator przebiegu.
   Grupy są też zgodne z wyrażeniem z pre-rejestracji kampanii Q4.
3. **Ta lista nie wysyła w tym tygodniu żadnej oferty.** Tylko jedna umowa ma akcję „rabat” i trafiła do kontroli.
   113 umów ma akcję „bez rabatu” (44 z nich, bo model nie zna jeszcze ich cech), a 18 ma akcję „nie budzić”.
4. **Akcję wyznacza reguła z GET /risk (EV > 0), a nie reguła z planu kampanii Q4 (górne 20% upliftu).** Zanim
   lista posłuży do kampanii, trzeba zdecydować, którą regułą wybieramy oferty (pytanie 2).

## Wyniki

### Jak działa zadanie

| Krok (Inngest `ctx.step.run`) | Co robi |
|---|---|
| `parametry` | dzień listy: ze zdarzenia `domilo/lista.retencyjna` (`data.data_listy`) albo dziś w Europe/Warsaw; stan danych = dzień listy, najpóźniej 2026-09-30 (dzień eksportu) |
| `umowy-w-oknie` | bieżący okres aktywnego najmu B2C / B2B (`okresy_umow.sql`), `data_do` od dnia listy + 60 do dnia listy + 66 |
| `ryzyko-i-czas` | część `ryzyko` z `churn_model/current.yaml` (`v2_przezycie_cox`): `ryzyko` = P(koniec najmu w bieżącym okresie) od dnia stanu, mediana czasu do odejścia, RMST60. To samo co GET /risk (test `test_ryzyko_wsadowe_to_samo_co_endpoint_risk`) |
| `uplift-i-akcja` | część `uplift` (`v3_uplift_tlearner`): P(przedłuży z ofertą / bez), uplift, EV i akcja według reguły `oferta_najmu.py` (cechy na dzień decyzji = min(`data_do` − 60 dni, dzień stanu); cechy poza zakresem treningu → „bez rabatu”) |
| `grupy-kampanii` | kampania: `kampania_RRRRqN` według miesiąca końca umowy minus 2 miesiące (końce 2026-12 – 2027-02 → `kampania_2026q4`) albo `data.kampania`. `reszta_hasha` = md5(`id_umowy:kampania`) jako liczba little-endian mod 100, czyli `md5_number(id_umowy \|\| ':' \|\| kampania) % 100` w DuckDB. Reszta < 20 → `kontrola`, inaczej `polityka` |
| `zapis-listy` | tabela `lista_retencyjna`, klucz (`data_listy`, `id_umowy`); zapis zastępuje cały dzień listy. `wyslac_oferte` = `polityka` i akcja `rabat` (sprawdza to też CHECK tabeli) |

Wersje modeli wczytuje `churn_model/base.wczytaj_obecny()`. Sprawdza ona, że plik modelu zawiera klasę i wersję
wpisane w `current.yaml`. Pusty `current.yaml` przerywa zadanie, bo nie zgadujemy wersji.

### Dwa przebiegi z 2026-11-16 (okno końca umów 2027-01-15 – 2027-01-21, stan danych 2026-09-30)

| Krok | Przebieg 1 (`reczny-20261116T014329402402`) | Przebieg 2 (`reczny-20261116T014333371418`) |
|---|---|---|
| umowy w oknie | 132 (B2C 113, B2B 19), z wypowiedzeniem 0 | 132 (B2C 113, B2B 19), z wypowiedzeniem 0 |
| ryzyko i czas | v2_przezycie_cox, średnie ryzyko 0,305188 | v2_przezycie_cox, średnie ryzyko 0,305188 |
| uplift i akcja | bez rabatu 113, nie budzić 18, rabat 1; poza zakresem v3: 44 | to samo |
| grupy | kampania_2026q4: kontrola 26, polityka 106 | to samo |
| zapis | 132 wiersze, ofert do wysłania 0 | 132 wiersze, ofert do wysłania 0 |

| Porównanie (SQL niżej) | Wynik |
|---|---:|
| wiersze: przebieg 1 / przebieg 2 / tabela po 2. przebiegu | 132 / 132 / 132 |
| umowy z inną kampanią, resztą hasha, grupą albo `wyslac_oferte` (przebieg 1 vs 2) | **0** z 132 |
| całe wiersze bez `id_przebiegu`: tylko w przebiegu 1 / tylko w przebiegu 2 | **0 / 0** |
| tabela po 2. przebiegu: grupa inna niż w przebiegu 1 | **0** |
| grupa albo reszta niezgodna z `md5_number(id_umowy \|\| ':' \|\| kampania) % 100 < 20` | **0** |

### Lista z 2026-11-16

| Grupa | Akcja | Umowy | Ofert do wysłania |
|---|---|---:|---:|
| kontrola | bez rabatu | 20 | 0 |
| kontrola | nie budzić | 5 | 0 |
| kontrola | rabat | 1 | 0 |
| polityka | bez rabatu | 93 | 0 |
| polityka | nie budzić | 13 | 0 |

| Linia | Kontrola | Polityka |
|---|---:|---:|
| B2C | 20 | 93 |
| B2B | 6 | 13 |

Kontrola to 26 ze 132 umów (19,7%). Średnie ryzyko wynosi 0,305, mediana RMST60 27,61 miesiąca, a 13 umów ma
medianę czasu do odejścia powyżej 60 miesięcy. Jedyna umowa z akcją „rabat” to U0026169 (B2B, uplift +21,3 p.p.,
EV 70 zł, reszta hasha 19, czyli kontrola). W kampanii Q3 oferta nie zmieniła przedłużeń B2B
([kampania_2026q3.md](kampania_2026q3.md)), co jest kolejnym powodem, by tę regułę potwierdzić.

Pięć umów o najwyższym ryzyku:

| id_umowy | Linia | Koniec | Ryzyko | Mediana (mies.) | RMST60 | Uplift | EV (zł) | Akcja | Reszta | Grupa |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---|
| U0032393 | B2B | 2027-01-20 | 0,750 | 3,67 | 7,71 | +0,088 | −258 | bez rabatu | 12 | kontrola |
| U0032154 | B2B | 2027-01-19 | 0,741 | 3,63 | 7,85 | −0,031 | −582 | bez rabatu | 50 | polityka |
| U0032250 | B2B | 2027-01-18 | 0,725 | 3,60 | 8,13 | −0,055 | −737 | bez rabatu | 19 | kontrola |
| U0032486 | B2B | 2027-01-17 | 0,719 | 3,57 | 8,25 | −0,134 | −1 047 | bez rabatu | 21 | polityka |
| U0032518 | B2B | 2027-01-19 | 0,715 | 3,63 | 8,39 | −0,116 | −1 023 | bez rabatu | 74 | polityka |

### Ograniczenia

- **Dane kończą się 2026-09-30,** więc dla list po tej dacie cechy, ryzyko i uplift liczymy na stan z tego dnia,
  a nie na dzień decyzji. Dlatego 44 ze 132 umów ma cechy poza zakresem danych uczących v3 (na przykład najem
  krótszy niż najkrótszy w treningu) i dostaje akcję „bez rabatu”. Na bieżących danych dniem decyzji byłby
  dzień listy.
- **Wpis v3 w `current.yaml` jest warunkowy.** Ewaluacja zalecała nie wpisywać v3, bo nie ma przewagi nad regułą
  „górne 35% `score_polityki`” ([uplift.md](../api/api/ai/churn_model/evals/uplift.md)).
- **Funkcję Inngest sprawdzono testem konfiguracji** (harmonogram i zdarzenie). Same przebiegi uruchomiono przez
  `pypyr lista_retencyjna`, czyli te same kroki co w Inngest, bez serwera Inngest.

## SQL i kod

Uruchomienie dwóch przebiegów (z katalogu głównego, baza z `pypyr baza`):

```bash
poetry run pypyr lista_retencyjna data=2026-11-16   # przebieg 1
poetry run pypyr lista_retencyjna data=2026-11-16   # przebieg 2
poetry run pytest -q api/tests/test_lista_retencyjna.py
```

Inngest: zdarzenie `domilo/lista.retencyjna` z `{"data_listy": "2026-11-16"}` (opcjonalnie `"kampania": "..."`),
harmonogram `TZ=Europe/Warsaw 0 7 * * 1`.

Porównanie przebiegów. Każdy przebieg zostawia kopię zapisanych wierszy w
`lista_retencyjna/2026-11-16/<id_przebiegu>/lista.parquet`, a `p1` i `p2` to te pliki:

```sql
-- grupy: przebieg 1 vs przebieg 2 (0 różnic z 132)
SELECT count(*) FILTER (WHERE a.id_umowy IS NULL OR b.id_umowy IS NULL
                         OR a.kampania <> b.kampania OR a.reszta_hasha <> b.reszta_hasha
                         OR a.grupa <> b.grupa OR a.wyslac_oferte <> b.wyslac_oferte) AS roznice,
       count(*) AS umowy
FROM 'p1' AS a FULL JOIN 'p2' AS b USING (id_umowy);

-- całe wiersze bez id_przebiegu (0 i 0)
SELECT (SELECT count(*) FROM (SELECT * EXCLUDE (id_przebiegu) FROM 'p1'
                              EXCEPT ALL SELECT * EXCLUDE (id_przebiegu) FROM 'p2')),
       (SELECT count(*) FROM (SELECT * EXCLUDE (id_przebiegu) FROM 'p2'
                              EXCEPT ALL SELECT * EXCLUDE (id_przebiegu) FROM 'p1'));

-- tabela po 2. przebiegu a grupy z 1. przebiegu (0)
SELECT count(*) FILTER (WHERE t.grupa IS DISTINCT FROM a.grupa)
FROM 'p1' AS a
FULL JOIN (SELECT * FROM lista_retencyjna WHERE data_listy = DATE '2026-11-16') AS t USING (id_umowy);

-- grupa = wyrażenie z pre-rejestracji (docs/kampania_2026q4_plan.md) (0)
SELECT count(*) FILTER (WHERE (md5_number(id_umowy || ':' || kampania) % 100 < 20) <> (grupa = 'kontrola')
                           OR (md5_number(id_umowy || ':' || kampania) % 100)::INTEGER <> reszta_hasha)
FROM lista_retencyjna WHERE data_listy = DATE '2026-11-16';

-- tabele wyników
SELECT grupa, akcja, count(*), sum(wyslac_oferte::INT) FROM lista_retencyjna
WHERE data_listy = DATE '2026-11-16' GROUP BY ALL ORDER BY ALL;
SELECT linia, grupa, count(*) FROM lista_retencyjna WHERE data_listy = DATE '2026-11-16' GROUP BY ALL ORDER BY ALL;
SELECT min(dni_do_konca), max(dni_do_konca), min(data_do), max(data_do),
       count(*) FILTER (WHERE len(poza_zakresem_modelu) > 0), round(avg(ryzyko), 4), round(median(rmst60_mies), 2),
       count(*) FILTER (WHERE mediana_do_odejscia_mies IS NULL)
FROM lista_retencyjna WHERE data_listy = DATE '2026-11-16';
SELECT id_umowy, linia, data_do, round(ryzyko, 3), mediana_do_odejscia_mies, rmst60_mies, round(uplift, 3),
       round(ev_pln), akcja, reszta_hasha, grupa
FROM lista_retencyjna WHERE data_listy = DATE '2026-11-16' ORDER BY ryzyko DESC LIMIT 5;
```

Losowanie grupy (Python, `lista_retencyjna.py`):

```python
def reszta_hasha(id_umowy: str, kampania: str) -> int:
    skrot = hashlib.md5(f"{id_umowy}:{kampania}".encode("utf-8")).digest()
    return int.from_bytes(skrot, "little") % 100  # = md5_number(...) % 100 w DuckDB


def grupa_kampanii(id_umowy: str, kampania: str, udzial_kontroli: float = 0.20) -> str:
    return "kontrola" if reszta_hasha(id_umowy, kampania) < round(100 * udzial_kontroli) else "polityka"
```
