# Raport kwartalny dla banku: wycena portfela Domilo, 2026 Q3

Okres raportu: 2026-07-01 – 2026-09-30. Stan wycen: przebieg zadania nocnego z 2026-11-15 18:43 (czas warszawski), model `v4_llm_cechy`. Raport utworzono 2026-11-15 18:48 (czas warszawski).
Dane: eksport 2026-09-30 23:59 Europe/Warsaw (`domilo.duckdb`); wyceny: tabela `wyceny_historia`.

## Wnioski

1. Na 300 operatach kontrolnych z okresu 01.07.2026–30.09.2026 model wycenił 297 lokali i pomylił się średnio o 5,28% (warunek banku: najwyżej 8%), więc warunek jest spełniony.
2. Wartość z operatu mieściła się w przedziale wyceny (P10–P90) w 78,8% przypadków (norma 77–83%), więc warunek jest spełniony.
3. Model nie wycenił 571 z 7 200 lokali portfela (7,9%) i odpowiedział „nie wiem” z podaniem powodu. Te lokale wymagają wyceny rzeczoznawcy (tabela 5).
4. Wartość portfela według modelu to 5 486,1 mln zł dla 6 629 lokali. Lokale bez wyceny modelu miały w ostatnich operatach rocznych łącznie 627,8 mln zł.
5. LTV nie da się policzyć: w danych nie ma kwoty zadłużenia portfela (brak w danych).

## Tabele

### 1. Sprawdzian na operatach kontrolnych (warunki banku z zalozenia.yaml)

Błąd = (wycena P50 − wartość operatu) / wartość operatu, liczony na lokalach przyjętych przez model. Odmowa to
odpowiedź „nie wiem”, bez liczby.

| Operaty | Bez wyceny w historii | Odmowy | Przyjęte | MAPE | MdAPE | Mediana błędu ze znakiem | Pokrycie P10–P90 | MAPE ≤ 8% | Pokrycie 77–83% |
|---|---|---|---|---|---|---|---|---|---|
| 300 | 0 | 3 | 297 | 5,28% | 4,48% | -2,60% | 78,8% | spełniony | spełniony |

### 2. Operaty kontrolne według miasta

| Miasto | Operaty | Odmowy | MAPE | Pokrycie | Mediana błędu |
|---|---|---|---|---|---|
| Gdańsk | 19 | 0 | 5,37% | 73,7% | -4,28% |
| Kraków | 51 | 0 | 5,32% | 76,5% | -2,75% |
| Poznań | 42 | 0 | 4,64% | 85,7% | -1,50% |
| Warszawa | 138 | 2 | 5,49% | 78,7% | -2,74% |
| Wrocław | 36 | 0 | 4,78% | 83,3% | -2,60% |
| Łódź | 14 | 1 | 6,28% | 61,5% | -3,64% |

### 3. Wartość portfela

Suma P10 i suma P90 to sumy granic przedziałów pojedynczych lokali, a nie przedział 80% dla całego portfela (błędy
wycen lokali są ze sobą powiązane). Lokale z odmową nie mają wyceny modelu. Dla porównania podajemy ich ostatni
operat roczny.

| Lokale (PMS) | Wycenione przez model | Suma P50 | Suma P10 | Suma P90 | Odmowy | Ostatni operat roczny lokali z odmową |
|---|---|---|---|---|---|---|
| 7200 | 6629 | 5 486,1 mln zł | 5 061,7 mln zł | 6 078,3 mln zł | 571 | 627,8 mln zł |

### 4. LTV

Brak w danych: LTV = zadłużenie zabezpieczone portfelem / wartość portfela, a w `data/` nie ma kwoty kredytu ani
zadłużenia. Do policzenia LTV potrzebna jest kwota od użytkownika (wpis w `valuation_bc/zalozenia.yaml` ze źródłem).

### 5. Odmowy („nie wiem”) z powodami

Rodzaje powodów (lokal z kilkoma powodami liczy się w każdym):

| Rodzaj powodu | Lokale |
|---|---|
| miasto spoza treningu albo z małą liczbą transakcji | 0 |
| dzielnica z małą liczbą transakcji | 410 |
| metraż poza zakresem treningu | 70 |
| brak roku budowy | 0 |
| rok budowy poza zakresem treningu | 0 |
| nietypowy typ lokalu (pokoje × metraż) | 133 |
| lokal daleko od transakcji treningowych (kNN) | 20 |
| inny (np. nietypowy według Isolation Forest) | 42 |

Odmowy wśród lokali z operatem kontrolnym:

| Lokal | Budynek | Miasto | Powód |
|---|---|---|---|
| B05-0205 | Domilo Gocław | Warszawa | Nietypowy typ lokalu: 2-pokojowy o metrażu 81,5 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B30-0034 | Domilo Bałuty | Łódź | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,7 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B31-0060 | Domilo Włochy Okęcie | Warszawa | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |

Wszystkie lokale portfela z odmową:

| Lokal | Budynek | Miasto | Dzielnica | Metraż m² | Powód |
|---|---|---|---|---|---|
| B01-0143 | Domilo Wola Park | Warszawa | Wola | 46,1 | Nietypowy typ lokalu: 4-pokojowy o metrażu 46,1 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5) |
| B01-0163 | Domilo Wola Park | Warszawa | Wola | 42,4 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B02-0018 | Domilo Mokotów Residence | Warszawa | Mokotów | 115,0 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,50 (próg 2,41), najbardziej odstają: metraż (3,0 odch. std. od średniej treningu), liczba pokoi (2,9 odch. std. od średniej treningu) |
| B02-0028 | Domilo Mokotów Residence | Warszawa | Mokotów | 115,0 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,44 (próg 2,41), najbardziej odstają: metraż (3,0 odch. std. od średniej treningu), liczba pokoi (2,9 odch. std. od średniej treningu) |
| B02-0064 | Domilo Mokotów Residence | Warszawa | Mokotów | 17,3 | Metraż 17,3 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,3 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B02-0185 | Domilo Mokotów Residence | Warszawa | Mokotów | 72,7 | Nietypowy typ lokalu: 2-pokojowy o metrażu 72,7 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B03-0042 | Domilo Ursus Ogrody | Warszawa | Ursus | 43,1 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,1 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B03-0116 | Domilo Ursus Ogrody | Warszawa | Ursus | 68,2 | Nietypowy typ lokalu: 2-pokojowy o metrażu 68,2 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B03-0180 | Domilo Ursus Ogrody | Warszawa | Ursus | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B04-0004 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 118,0 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,615 (próg 0,596) |
| B04-0013 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 106,0 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,597 (próg 0,596) |
| B04-0015 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 118,0 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,602 (próg 0,596) |
| B04-0020 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 118,0 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,602 (próg 0,596) |
| B04-0054 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 88,9 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,604 (próg 0,596) |
| B04-0062 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 118,0 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,601 (próg 0,596) |
| B04-0067 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 108,6 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,598 (próg 0,596) |
| B04-0088 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 107,1 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,597 (próg 0,596) |
| B04-0103 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 115,5 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,613 (próg 0,596) |
| B04-0114 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 92,2 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,605 (próg 0,596) |
| B04-0116 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 118,0 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,613 (próg 0,596) |
| B04-0119 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 114,5 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,600 (próg 0,596) |
| B04-0121 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 134,7 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0122 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 132,7 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,611 (próg 0,596) |
| B04-0123 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 142,7 | Metraż 142,7 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 142,7 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0124 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 127,5 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,619 (próg 0,596) |
| B04-0125 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 121,1 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,617 (próg 0,596) |
| B04-0126 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 159,3 | Metraż 159,3 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 159,3 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,42 (próg 2,41), najbardziej odstają: metraż (4,8 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0127 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 161,0 | Metraż 161,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 161,0 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,50 (próg 2,41), najbardziej odstają: metraż (4,9 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,612 (próg 0,596) |
| B04-0128 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 156,9 | Metraż 156,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 156,9 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0129 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 150,3 | Metraż 150,3 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 150,3 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0130 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 152,0 | Metraż 152,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 152,0 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0131 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 133,3 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0132 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 160,2 | Metraż 160,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 160,2 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,44 (próg 2,41), najbardziej odstają: metraż (4,9 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0133 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 138,1 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,613 (próg 0,596) |
| B04-0134 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 137,9 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0135 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 165,5 | Metraż 165,5 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 165,5 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,57 (próg 2,41), najbardziej odstają: metraż (5,1 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0136 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 157,6 | Metraż 157,6 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 157,6 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0137 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 151,0 | Metraż 151,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 151,0 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0138 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 159,0 | Metraż 159,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 159,0 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,42 (próg 2,41), najbardziej odstają: metraż (4,8 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0139 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 165,2 | Metraż 165,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 165,2 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,61 (próg 2,41), najbardziej odstają: metraż (5,1 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,612 (próg 0,596) |
| B04-0140 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 167,9 | Metraż 167,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 167,9 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,63 (próg 2,41), najbardziej odstają: metraż (5,2 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0141 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 155,1 | Metraż 155,1 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 155,1 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,612 (próg 0,596) |
| B04-0142 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 153,9 | Metraż 153,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 153,9 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0143 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 146,0 | Metraż 146,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 146,0 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0144 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 145,3 | Metraż 145,3 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 145,3 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0145 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 140,1 | Metraż 140,1 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 140,1 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0146 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 158,4 | Metraż 158,4 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 158,4 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5); Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,43 (próg 2,41), najbardziej odstają: metraż (4,8 odch. std. od średniej treningu), gęstość zaludnienia dzielnicy (4,5 odch. std. od średniej treningu); Nietypowa kombinacja cech (Isolation Forest): wynik 0,612 (próg 0,596) |
| B04-0147 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 137,9 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0148 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 138,2 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0149 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 135,5 | Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B04-0150 | Domilo Powiśle Prestige | Warszawa | Śródmieście | 141,8 | Metraż 141,8 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 141,8 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5); Nietypowa kombinacja cech (Isolation Forest): wynik 0,623 (próg 0,596) |
| B05-0069 | Domilo Gocław | Warszawa | Praga-Południe | 42,9 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,9 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B05-0125 | Domilo Gocław | Warszawa | Praga-Południe | 77,3 | Nietypowy typ lokalu: 2-pokojowy o metrażu 77,3 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B05-0205 | Domilo Gocław | Warszawa | Praga-Południe | 81,5 | Nietypowy typ lokalu: 2-pokojowy o metrażu 81,5 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B05-0211 | Domilo Gocław | Warszawa | Praga-Południe | 19,3 | Metraż 19,3 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,3 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B05-0245 | Domilo Gocław | Warszawa | Praga-Południe | 19,9 | Metraż 19,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,9 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B06-0003 | Domilo Bródno Park | Warszawa | Targówek | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B06-0070 | Domilo Bródno Park | Warszawa | Targówek | 42,8 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,8 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B07-0002 | Domilo Bemowo Lotnisko | Warszawa | Bemowo | 43,5 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,5 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B07-0016 | Domilo Bemowo Lotnisko | Warszawa | Bemowo | 17,4 | Metraż 17,4 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B07-0021 | Domilo Bemowo Lotnisko | Warszawa | Bemowo | 43,7 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,7 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B07-0068 | Domilo Bemowo Lotnisko | Warszawa | Bemowo | 112,7 | Nietypowy typ lokalu: 3-pokojowy o metrażu 112,7 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B07-0116 | Domilo Bemowo Lotnisko | Warszawa | Bemowo | 17,7 | Metraż 17,7 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,7 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B07-0212 | Domilo Bemowo Lotnisko | Warszawa | Bemowo | 102,2 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,49 (próg 2,41), najbardziej odstają: metraż (2,4 odch. std. od średniej treningu), piętro (2,3 odch. std. od średniej treningu) |
| B07-0224 | Domilo Bemowo Lotnisko | Warszawa | Bemowo | 103,1 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,54 (próg 2,41), najbardziej odstają: metraż (2,5 odch. std. od średniej treningu), piętro (2,3 odch. std. od średniej treningu) |
| B08-0179 | Domilo Tarchomin | Warszawa | Białołęka | 43,0 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B09-0024 | Domilo Odolany | Warszawa | Wola | 19,6 | Metraż 19,6 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,6 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B09-0135 | Domilo Odolany | Warszawa | Wola | 43,3 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,3 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B09-0159 | Domilo Odolany | Warszawa | Wola | 78,3 | Nietypowy typ lokalu: 2-pokojowy o metrażu 78,3 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B10-0045 | Domilo Krowodrza | Kraków | Krowodrza | 19,6 | Metraż 19,6 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,6 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B11-0027 | Domilo Kabaty Las | Warszawa | Ursynów | 43,2 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B11-0044 | Domilo Kabaty Las | Warszawa | Ursynów | 79,2 | Nietypowy typ lokalu: 2-pokojowy o metrażu 79,2 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B11-0082 | Domilo Kabaty Las | Warszawa | Ursynów | 19,6 | Metraż 19,6 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,6 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B11-0087 | Domilo Kabaty Las | Warszawa | Ursynów | 43,9 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,9 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B11-0092 | Domilo Kabaty Las | Warszawa | Ursynów | 43,3 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,3 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B11-0147 | Domilo Kabaty Las | Warszawa | Ursynów | 30,4 | Nietypowy typ lokalu: 3-pokojowy o metrażu 30,4 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B12-0020 | Domilo Kamienica Ząbkowska | Warszawa | Praga-Północ | 101,7 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,61 (próg 2,41), najbardziej odstają: metro do 700 m (3,9 odch. std. od średniej treningu), metraż (2,4 odch. std. od średniej treningu) |
| B15-0090 | Domilo Bronowice | Kraków | Bronowice | 42,4 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B16-0033 | Domilo Czyżyny Park | Kraków | Czyżyny | 19,4 | Metraż 19,4 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B16-0152 | Domilo Czyżyny Park | Kraków | Czyżyny | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B17-0004 | Domilo Ruczaj | Kraków | Dębniki | 18,8 | Metraż 18,8 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 18,8 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B17-0014 | Domilo Ruczaj | Kraków | Dębniki | 18,7 | Metraż 18,7 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 18,7 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B17-0039 | Domilo Ruczaj | Kraków | Dębniki | 55,5 | Nietypowy typ lokalu: 1-pokojowy o metrażu 55,5 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B17-0094 | Domilo Ruczaj | Kraków | Dębniki | 42,4 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B17-0123 | Domilo Ruczaj | Kraków | Dębniki | 42,8 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,8 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B17-0155 | Domilo Ruczaj | Kraków | Dębniki | 43,9 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,9 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B18-0016 | Domilo Krzyki | Wrocław | Krzyki | 43,2 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B18-0049 | Domilo Krzyki | Wrocław | Krzyki | 30,1 | Nietypowy typ lokalu: 3-pokojowy o metrażu 30,1 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B18-0182 | Domilo Krzyki | Wrocław | Krzyki | 43,3 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,3 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B19-0133 | Domilo Nowy Dwór | Wrocław | Nowy Dwór | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B20-0144 | Domilo Psie Pole | Wrocław | Psie Pole | 43,5 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,5 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B21-0040 | Domilo Granary Prestige | Gdańsk | Śródmieście | 104,3 | Nietypowy typ lokalu: 3-pokojowy o metrażu 104,3 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B21-0138 | Domilo Granary Prestige | Gdańsk | Śródmieście | 159,0 | Metraż 159,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 159,0 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0140 | Domilo Granary Prestige | Gdańsk | Śródmieście | 166,8 | Metraż 166,8 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 166,8 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5) |
| B21-0141 | Domilo Granary Prestige | Gdańsk | Śródmieście | 148,9 | Metraż 148,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 148,9 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0142 | Domilo Granary Prestige | Gdańsk | Śródmieście | 148,3 | Metraż 148,3 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 148,3 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5) |
| B21-0143 | Domilo Granary Prestige | Gdańsk | Śródmieście | 166,1 | Metraż 166,1 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 166,1 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0146 | Domilo Granary Prestige | Gdańsk | Śródmieście | 142,1 | Metraż 142,1 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 142,1 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0147 | Domilo Granary Prestige | Gdańsk | Śródmieście | 148,9 | Metraż 148,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 148,9 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0148 | Domilo Granary Prestige | Gdańsk | Śródmieście | 163,4 | Metraż 163,4 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 163,4 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5) |
| B21-0150 | Domilo Granary Prestige | Gdańsk | Śródmieście | 152,7 | Metraż 152,7 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 152,7 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0152 | Domilo Granary Prestige | Gdańsk | Śródmieście | 158,9 | Metraż 158,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 158,9 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0153 | Domilo Granary Prestige | Gdańsk | Śródmieście | 156,2 | Metraż 156,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 156,2 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5) |
| B21-0155 | Domilo Granary Prestige | Gdańsk | Śródmieście | 161,6 | Metraż 161,6 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 161,6 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0156 | Domilo Granary Prestige | Gdańsk | Śródmieście | 143,9 | Metraż 143,9 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 4-pokojowy o metrażu 143,9 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5) |
| B21-0157 | Domilo Granary Prestige | Gdańsk | Śródmieście | 164,0 | Metraż 164,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 164,0 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B21-0158 | Domilo Granary Prestige | Gdańsk | Śródmieście | 142,2 | Metraż 142,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 5-pokojowy o metrażu 142,2 m², w treningu 5-pokojowe mają 85,2–140,0 m² (p0,5–p99,5) |
| B22-0083 | Domilo Ołbin | Wrocław | Ołbin | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B23-0017 | Domilo Rataje | Poznań | Rataje | 80,9 | Nietypowy typ lokalu: 2-pokojowy o metrażu 80,9 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B23-0035 | Domilo Rataje | Poznań | Rataje | 43,4 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B23-0060 | Domilo Rataje | Poznań | Rataje | 42,4 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B23-0170 | Domilo Rataje | Poznań | Rataje | 19,2 | Metraż 19,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B24-0020 | Domilo Jeżyce | Poznań | Jeżyce | 78,4 | Nietypowy typ lokalu: 2-pokojowy o metrażu 78,4 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B24-0136 | Domilo Jeżyce | Poznań | Jeżyce | 17,7 | Metraż 17,7 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 2-pokojowy o metrażu 17,7 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B24-0144 | Domilo Jeżyce | Poznań | Jeżyce | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B24-0167 | Domilo Jeżyce | Poznań | Jeżyce | 18,5 | Metraż 18,5 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 18,5 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B25-0002 | Domilo Grunwald | Poznań | Grunwald | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B25-0022 | Domilo Grunwald | Poznań | Grunwald | 42,6 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,6 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B25-0052 | Domilo Grunwald | Poznań | Grunwald | 43,6 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,6 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B25-0163 | Domilo Grunwald | Poznań | Grunwald | 30,5 | Nietypowy typ lokalu: 3-pokojowy o metrażu 30,5 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B26-0017 | Domilo Wilanów Zielony | Warszawa | Wilanów | 84,2 | Nietypowy typ lokalu: 2-pokojowy o metrażu 84,2 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B26-0061 | Domilo Wilanów Zielony | Warszawa | Wilanów | 115,0 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,49 (próg 2,41), najbardziej odstają: metraż (3,0 odch. std. od średniej treningu), liczba pokoi (2,9 odch. std. od średniej treningu) |
| B26-0150 | Domilo Wilanów Zielony | Warszawa | Wilanów | 97,4 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,48 (próg 2,41), najbardziej odstają: wskaźnik dochodu dzielnicy (2,6 odch. std. od średniej treningu), metraż (2,2 odch. std. od średniej treningu) |
| B26-0193 | Domilo Wilanów Zielony | Warszawa | Wilanów | 72,2 | Nietypowy typ lokalu: 2-pokojowy o metrażu 72,2 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B26-0196 | Domilo Wilanów Zielony | Warszawa | Wilanów | 85,5 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,60 (próg 2,41), najbardziej odstają: wskaźnik dochodu dzielnicy (2,6 odch. std. od średniej treningu), piętro (2,0 odch. std. od średniej treningu) |
| B26-0207 | Domilo Wilanów Zielony | Warszawa | Wilanów | 82,7 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,43 (próg 2,41), najbardziej odstają: wskaźnik dochodu dzielnicy (2,6 odch. std. od średniej treningu), piętro (2,0 odch. std. od średniej treningu) |
| B26-0209 | Domilo Wilanów Zielony | Warszawa | Wilanów | 42,7 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,7 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B26-0210 | Domilo Wilanów Zielony | Warszawa | Wilanów | 94,9 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,99 (próg 2,41), najbardziej odstają: liczba pokoi (2,9 odch. std. od średniej treningu), wskaźnik dochodu dzielnicy (2,6 odch. std. od średniej treningu) |
| B27-0032 | Domilo Naramowice | Poznań | Naramowice | 82,4 | Nietypowy typ lokalu: 2-pokojowy o metrażu 82,4 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B28-0026 | Domilo Wrzeszcz | Gdańsk | Wrzeszcz Dolny | 18,2 | Metraż 18,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 18,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B28-0131 | Domilo Wrzeszcz | Gdańsk | Wrzeszcz Dolny | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B28-0132 | Domilo Wrzeszcz | Gdańsk | Wrzeszcz Dolny | 19,0 | Metraż 19,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 2-pokojowy o metrażu 19,0 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B29-0006 | Domilo Widzew | Łódź | Widzew | 19,1 | Metraż 19,1 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,1 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B29-0092 | Domilo Widzew | Łódź | Widzew | 78,0 | Nietypowy typ lokalu: 2-pokojowy o metrażu 78,0 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B30-0028 | Domilo Bałuty | Łódź | Bałuty-Centrum | 43,1 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,1 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B30-0034 | Domilo Bałuty | Łódź | Bałuty-Centrum | 42,7 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,7 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B30-0058 | Domilo Bałuty | Łódź | Bałuty-Centrum | 18,3 | Metraż 18,3 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 18,3 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B30-0082 | Domilo Bałuty | Łódź | Bałuty-Centrum | 19,1 | Metraż 19,1 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,1 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B30-0125 | Domilo Bałuty | Łódź | Bałuty-Centrum | 17,4 | Metraż 17,4 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B31-0060 | Domilo Włochy Okęcie | Warszawa | Włochy | 43,4 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B31-0098 | Domilo Włochy Okęcie | Warszawa | Włochy | 30,1 | Nietypowy typ lokalu: 3-pokojowy o metrażu 30,1 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B31-0128 | Domilo Włochy Okęcie | Warszawa | Włochy | 18,6 | Metraż 18,6 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 18,6 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B31-0199 | Domilo Włochy Okęcie | Warszawa | Włochy | 115,0 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,43 (próg 2,41), najbardziej odstają: metraż (3,0 odch. std. od średniej treningu), liczba pokoi (2,9 odch. std. od średniej treningu) |
| B31-0220 | Domilo Włochy Okęcie | Warszawa | Włochy | 115,0 | Lokal daleko od transakcji treningowych: średnia odległość do 10 najbliższych 2,53 (próg 2,41), najbardziej odstają: metraż (3,0 odch. std. od średniej treningu), liczba pokoi (2,9 odch. std. od średniej treningu) |
| B32-0061 | Domilo Bielany Las | Warszawa | Bielany | 42,7 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,7 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B32-0186 | Domilo Bielany Las | Warszawa | Bielany | 59,3 | Nietypowy typ lokalu: 1-pokojowy o metrażu 59,3 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B32-0187 | Domilo Bielany Las | Warszawa | Bielany | 17,0 | Metraż 17,0 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 17,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B33-0013 | Domilo Azory | Kraków | Prądnik Biały | 43,2 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B33-0170 | Domilo Azory | Kraków | Prądnik Biały | 30,0 | Nietypowy typ lokalu: 3-pokojowy o metrażu 30,0 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B34-0017 | Domilo Jagodno | Wrocław | Jagodno | 77,3 | Nietypowy typ lokalu: 2-pokojowy o metrażu 77,3 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B34-0021 | Domilo Jagodno | Wrocław | Jagodno | 42,9 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,9 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B34-0093 | Domilo Jagodno | Wrocław | Jagodno | 45,1 | Nietypowy typ lokalu: 4-pokojowy o metrażu 45,1 m², w treningu 4-pokojowe mają 49,4–140,0 m² (p0,5–p99,5) |
| B35-0001 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 137,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0002 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 109,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0003 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 58,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0004 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 109,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80); Nietypowy typ lokalu: 3-pokojowy o metrażu 109,5 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B35-0005 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 66,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0006 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 90,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0007 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 117,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0008 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 65,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0009 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 66,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0010 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 70,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0011 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 134,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0012 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 98,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0013 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 93,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0014 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 83,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0015 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 117,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0016 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 56,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0017 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 87,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0018 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 90,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0019 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 56,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0020 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 67,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0021 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 90,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0022 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 63,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0023 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 48,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0024 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 80,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0025 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 76,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0026 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 72,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0027 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 70,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0028 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 69,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0029 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 105,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0030 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 67,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0031 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 64,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0032 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 67,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0033 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 59,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0034 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 92,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0035 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 85,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0036 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 102,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0037 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 116,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0038 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 79,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0039 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 102,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0040 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 55,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0041 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 66,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0042 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 49,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0043 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 99,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0044 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 99,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0045 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 93,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0046 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 63,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0047 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 96,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0048 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 76,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0049 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 93,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0050 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 69,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0051 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 77,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0052 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 74,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0053 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 55,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0054 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 56,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0055 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 84,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0056 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 57,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0057 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 59,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0058 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 119,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0059 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 94,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0060 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 48,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0061 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 77,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0062 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 65,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0063 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 73,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0064 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 60,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0065 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 63,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0066 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 115,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0067 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 51,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0068 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 72,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0069 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 54,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0070 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 66,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0071 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 135,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0072 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 114,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0073 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 101,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0074 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 67,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0075 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 60,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0076 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 48,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0077 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 102,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0078 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 63,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0079 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 75,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0080 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 88,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0081 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 65,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0082 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 90,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0083 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 48,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0084 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 69,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0085 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 60,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0086 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 69,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0087 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 73,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0088 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 92,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0089 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 55,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0090 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 140,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0091 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 81,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0092 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 56,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0093 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 64,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0094 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 92,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0095 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 78,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0096 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 48,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0097 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 59,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0098 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 82,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0099 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 95,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0100 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 109,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80); Nietypowy typ lokalu: 3-pokojowy o metrażu 109,5 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B35-0101 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 54,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0102 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 123,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0103 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 109,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0104 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 80,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0105 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 110,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0106 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 85,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0107 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 133,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0108 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 110,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0109 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 73,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0110 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 111,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0111 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 53,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0112 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 73,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0113 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 91,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0114 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 50,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0115 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 102,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0116 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 64,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0117 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 91,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0118 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 48,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0119 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 65,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0120 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 117,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0121 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 92,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0122 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 79,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0123 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 109,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0124 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 74,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0125 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 130,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0126 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 116,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0127 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 110,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0128 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 60,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0129 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 91,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0130 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 95,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0131 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 99,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0132 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 57,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0133 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 86,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0134 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 53,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0135 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 72,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0136 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 82,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0137 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 61,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0138 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 73,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0139 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 69,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0140 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 69,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0141 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 75,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0142 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 81,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0143 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 78,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0144 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 58,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0145 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 48,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0146 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 140,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0147 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 75,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0148 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 75,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0149 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 68,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0150 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 83,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0151 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 77,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0152 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 56,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0153 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 66,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0154 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 98,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0155 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 99,1 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0156 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 122,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0157 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 73,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0158 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 140,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0159 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 76,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0160 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 68,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0161 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 67,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0162 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 77,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0163 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 110,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0164 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 98,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0165 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 92,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0166 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 64,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0167 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 117,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0168 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 87,7 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0169 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 53,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0170 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 134,2 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0171 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 61,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0172 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 95,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0173 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 73,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0174 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 60,5 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0175 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 86,9 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0176 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 60,8 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0177 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 113,4 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0178 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 98,3 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0179 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 52,0 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B35-0180 | Domilo Księży Młyn Lofts | Łódź | Księży Młyn | 92,6 | Dzielnica Księży Młyn (Łódź): 28 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B36-0012 | Domilo Morena | Gdańsk | Piecki-Migowo | 67,3 | Nietypowy typ lokalu: 2-pokojowy o metrażu 67,3 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B36-0117 | Domilo Morena | Gdańsk | Piecki-Migowo | 106,5 | Nietypowy typ lokalu: 3-pokojowy o metrażu 106,5 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B37-0016 | Kępa Park | Wrocław | Kępa Mieszczańska | 19,2 | Metraż 19,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B37-0033 | Kępa Park | Wrocław | Kępa Mieszczańska | 43,0 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B37-0037 | Kępa Park | Wrocław | Kępa Mieszczańska | 19,2 | Metraż 19,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B37-0207 | Kępa Park | Wrocław | Kępa Mieszczańska | 18,5 | Metraż 18,5 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 18,5 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B37-0244 | Kępa Park | Wrocław | Kępa Mieszczańska | 19,8 | Metraż 19,8 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,8 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B37-0248 | Kępa Park | Wrocław | Kępa Mieszczańska | 43,0 | Nietypowy typ lokalu: 1-pokojowy o metrażu 43,0 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B37-0274 | Kępa Park | Wrocław | Kępa Mieszczańska | 42,4 | Nietypowy typ lokalu: 1-pokojowy o metrażu 42,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B38-0001 | Stocznia Park | Gdańsk | Młode Miasto | 77,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0002 | Stocznia Park | Gdańsk | Młode Miasto | 58,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0003 | Stocznia Park | Gdańsk | Młode Miasto | 49,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0004 | Stocznia Park | Gdańsk | Młode Miasto | 45,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0005 | Stocznia Park | Gdańsk | Młode Miasto | 65,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0006 | Stocznia Park | Gdańsk | Młode Miasto | 53,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0007 | Stocznia Park | Gdańsk | Młode Miasto | 26,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0008 | Stocznia Park | Gdańsk | Młode Miasto | 65,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0009 | Stocznia Park | Gdańsk | Młode Miasto | 59,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0010 | Stocznia Park | Gdańsk | Młode Miasto | 43,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0011 | Stocznia Park | Gdańsk | Młode Miasto | 71,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0012 | Stocznia Park | Gdańsk | Młode Miasto | 36,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0013 | Stocznia Park | Gdańsk | Młode Miasto | 26,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0014 | Stocznia Park | Gdańsk | Młode Miasto | 37,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0015 | Stocznia Park | Gdańsk | Młode Miasto | 89,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0016 | Stocznia Park | Gdańsk | Młode Miasto | 34,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0017 | Stocznia Park | Gdańsk | Młode Miasto | 74,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0018 | Stocznia Park | Gdańsk | Młode Miasto | 55,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0019 | Stocznia Park | Gdańsk | Młode Miasto | 40,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0020 | Stocznia Park | Gdańsk | Młode Miasto | 86,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0021 | Stocznia Park | Gdańsk | Młode Miasto | 46,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0022 | Stocznia Park | Gdańsk | Młode Miasto | 67,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0023 | Stocznia Park | Gdańsk | Młode Miasto | 38,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0024 | Stocznia Park | Gdańsk | Młode Miasto | 23,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0025 | Stocznia Park | Gdańsk | Młode Miasto | 39,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0026 | Stocznia Park | Gdańsk | Młode Miasto | 25,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0027 | Stocznia Park | Gdańsk | Młode Miasto | 58,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0028 | Stocznia Park | Gdańsk | Młode Miasto | 36,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0029 | Stocznia Park | Gdańsk | Młode Miasto | 71,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0030 | Stocznia Park | Gdańsk | Młode Miasto | 38,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0031 | Stocznia Park | Gdańsk | Młode Miasto | 48,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0032 | Stocznia Park | Gdańsk | Młode Miasto | 44,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0033 | Stocznia Park | Gdańsk | Młode Miasto | 52,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0034 | Stocznia Park | Gdańsk | Młode Miasto | 33,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0035 | Stocznia Park | Gdańsk | Młode Miasto | 58,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0036 | Stocznia Park | Gdańsk | Młode Miasto | 96,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0037 | Stocznia Park | Gdańsk | Młode Miasto | 67,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0038 | Stocznia Park | Gdańsk | Młode Miasto | 83,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0039 | Stocznia Park | Gdańsk | Młode Miasto | 23,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0040 | Stocznia Park | Gdańsk | Młode Miasto | 29,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0041 | Stocznia Park | Gdańsk | Młode Miasto | 35,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0042 | Stocznia Park | Gdańsk | Młode Miasto | 52,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0043 | Stocznia Park | Gdańsk | Młode Miasto | 70,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0044 | Stocznia Park | Gdańsk | Młode Miasto | 50,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0045 | Stocznia Park | Gdańsk | Młode Miasto | 41,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0046 | Stocznia Park | Gdańsk | Młode Miasto | 36,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0047 | Stocznia Park | Gdańsk | Młode Miasto | 34,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0048 | Stocznia Park | Gdańsk | Młode Miasto | 21,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0049 | Stocznia Park | Gdańsk | Młode Miasto | 38,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0050 | Stocznia Park | Gdańsk | Młode Miasto | 41,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0051 | Stocznia Park | Gdańsk | Młode Miasto | 46,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0052 | Stocznia Park | Gdańsk | Młode Miasto | 84,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0053 | Stocznia Park | Gdańsk | Młode Miasto | 69,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0054 | Stocznia Park | Gdańsk | Młode Miasto | 57,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0055 | Stocznia Park | Gdańsk | Młode Miasto | 39,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0056 | Stocznia Park | Gdańsk | Młode Miasto | 58,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0057 | Stocznia Park | Gdańsk | Młode Miasto | 23,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0058 | Stocznia Park | Gdańsk | Młode Miasto | 44,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0059 | Stocznia Park | Gdańsk | Młode Miasto | 82,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0060 | Stocznia Park | Gdańsk | Młode Miasto | 25,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0061 | Stocznia Park | Gdańsk | Młode Miasto | 63,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0062 | Stocznia Park | Gdańsk | Młode Miasto | 35,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0063 | Stocznia Park | Gdańsk | Młode Miasto | 38,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0064 | Stocznia Park | Gdańsk | Młode Miasto | 59,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0065 | Stocznia Park | Gdańsk | Młode Miasto | 48,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0066 | Stocznia Park | Gdańsk | Młode Miasto | 34,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0067 | Stocznia Park | Gdańsk | Młode Miasto | 58,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0068 | Stocznia Park | Gdańsk | Młode Miasto | 58,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0069 | Stocznia Park | Gdańsk | Młode Miasto | 37,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0070 | Stocznia Park | Gdańsk | Młode Miasto | 102,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0071 | Stocznia Park | Gdańsk | Młode Miasto | 43,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0072 | Stocznia Park | Gdańsk | Młode Miasto | 31,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0073 | Stocznia Park | Gdańsk | Młode Miasto | 22,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0074 | Stocznia Park | Gdańsk | Młode Miasto | 48,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0075 | Stocznia Park | Gdańsk | Młode Miasto | 87,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0076 | Stocznia Park | Gdańsk | Młode Miasto | 85,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0077 | Stocznia Park | Gdańsk | Młode Miasto | 46,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0078 | Stocznia Park | Gdańsk | Młode Miasto | 55,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0079 | Stocznia Park | Gdańsk | Młode Miasto | 35,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0080 | Stocznia Park | Gdańsk | Młode Miasto | 32,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0081 | Stocznia Park | Gdańsk | Młode Miasto | 32,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0082 | Stocznia Park | Gdańsk | Młode Miasto | 49,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0083 | Stocznia Park | Gdańsk | Młode Miasto | 92,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0084 | Stocznia Park | Gdańsk | Młode Miasto | 33,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0085 | Stocznia Park | Gdańsk | Młode Miasto | 26,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0086 | Stocznia Park | Gdańsk | Młode Miasto | 30,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80); Nietypowy typ lokalu: 3-pokojowy o metrażu 30,0 m², w treningu 3-pokojowe mają 30,6–102,8 m² (p0,5–p99,5) |
| B38-0087 | Stocznia Park | Gdańsk | Młode Miasto | 52,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0088 | Stocznia Park | Gdańsk | Młode Miasto | 39,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0089 | Stocznia Park | Gdańsk | Młode Miasto | 82,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0090 | Stocznia Park | Gdańsk | Młode Miasto | 59,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0091 | Stocznia Park | Gdańsk | Młode Miasto | 36,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0092 | Stocznia Park | Gdańsk | Młode Miasto | 68,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0093 | Stocznia Park | Gdańsk | Młode Miasto | 39,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0094 | Stocznia Park | Gdańsk | Młode Miasto | 32,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0095 | Stocznia Park | Gdańsk | Młode Miasto | 37,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0096 | Stocznia Park | Gdańsk | Młode Miasto | 49,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0097 | Stocznia Park | Gdańsk | Młode Miasto | 57,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0098 | Stocznia Park | Gdańsk | Młode Miasto | 52,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0099 | Stocznia Park | Gdańsk | Młode Miasto | 33,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0100 | Stocznia Park | Gdańsk | Młode Miasto | 47,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0101 | Stocznia Park | Gdańsk | Młode Miasto | 43,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0102 | Stocznia Park | Gdańsk | Młode Miasto | 39,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0103 | Stocznia Park | Gdańsk | Młode Miasto | 43,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80); Nietypowy typ lokalu: 1-pokojowy o metrażu 43,4 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B38-0104 | Stocznia Park | Gdańsk | Młode Miasto | 41,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0105 | Stocznia Park | Gdańsk | Młode Miasto | 29,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0106 | Stocznia Park | Gdańsk | Młode Miasto | 44,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0107 | Stocznia Park | Gdańsk | Młode Miasto | 47,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0108 | Stocznia Park | Gdańsk | Młode Miasto | 44,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0109 | Stocznia Park | Gdańsk | Młode Miasto | 56,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0110 | Stocznia Park | Gdańsk | Młode Miasto | 45,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0111 | Stocznia Park | Gdańsk | Młode Miasto | 57,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0112 | Stocznia Park | Gdańsk | Młode Miasto | 47,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0113 | Stocznia Park | Gdańsk | Młode Miasto | 33,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0114 | Stocznia Park | Gdańsk | Młode Miasto | 24,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0115 | Stocznia Park | Gdańsk | Młode Miasto | 61,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0116 | Stocznia Park | Gdańsk | Młode Miasto | 42,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0117 | Stocznia Park | Gdańsk | Młode Miasto | 47,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0118 | Stocznia Park | Gdańsk | Młode Miasto | 40,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0119 | Stocznia Park | Gdańsk | Młode Miasto | 84,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0120 | Stocznia Park | Gdańsk | Młode Miasto | 48,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0121 | Stocznia Park | Gdańsk | Młode Miasto | 60,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0122 | Stocznia Park | Gdańsk | Młode Miasto | 19,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80); Metraż 19,2 m² poza zakresem treningu 20,0–140,0 m² (p0,5–p99,5); Nietypowy typ lokalu: 1-pokojowy o metrażu 19,2 m², w treningu 1-pokojowe mają 20,0–42,3 m² (p0,5–p99,5) |
| B38-0123 | Stocznia Park | Gdańsk | Młode Miasto | 81,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0124 | Stocznia Park | Gdańsk | Młode Miasto | 67,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0125 | Stocznia Park | Gdańsk | Młode Miasto | 57,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0126 | Stocznia Park | Gdańsk | Młode Miasto | 77,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0127 | Stocznia Park | Gdańsk | Młode Miasto | 64,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0128 | Stocznia Park | Gdańsk | Młode Miasto | 94,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0129 | Stocznia Park | Gdańsk | Młode Miasto | 58,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0130 | Stocznia Park | Gdańsk | Młode Miasto | 24,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0131 | Stocznia Park | Gdańsk | Młode Miasto | 41,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0132 | Stocznia Park | Gdańsk | Młode Miasto | 50,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0133 | Stocznia Park | Gdańsk | Młode Miasto | 45,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0134 | Stocznia Park | Gdańsk | Młode Miasto | 37,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0135 | Stocznia Park | Gdańsk | Młode Miasto | 23,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0136 | Stocznia Park | Gdańsk | Młode Miasto | 33,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0137 | Stocznia Park | Gdańsk | Młode Miasto | 25,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0138 | Stocznia Park | Gdańsk | Młode Miasto | 52,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0139 | Stocznia Park | Gdańsk | Młode Miasto | 34,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0140 | Stocznia Park | Gdańsk | Młode Miasto | 33,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0141 | Stocznia Park | Gdańsk | Młode Miasto | 66,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0142 | Stocznia Park | Gdańsk | Młode Miasto | 31,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0143 | Stocznia Park | Gdańsk | Młode Miasto | 43,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0144 | Stocznia Park | Gdańsk | Młode Miasto | 29,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0145 | Stocznia Park | Gdańsk | Młode Miasto | 57,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0146 | Stocznia Park | Gdańsk | Młode Miasto | 40,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0147 | Stocznia Park | Gdańsk | Młode Miasto | 74,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0148 | Stocznia Park | Gdańsk | Młode Miasto | 77,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0149 | Stocznia Park | Gdańsk | Młode Miasto | 25,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0150 | Stocznia Park | Gdańsk | Młode Miasto | 40,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0151 | Stocznia Park | Gdańsk | Młode Miasto | 40,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0152 | Stocznia Park | Gdańsk | Młode Miasto | 61,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0153 | Stocznia Park | Gdańsk | Młode Miasto | 47,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0154 | Stocznia Park | Gdańsk | Młode Miasto | 28,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0155 | Stocznia Park | Gdańsk | Młode Miasto | 51,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0156 | Stocznia Park | Gdańsk | Młode Miasto | 42,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0157 | Stocznia Park | Gdańsk | Młode Miasto | 41,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0158 | Stocznia Park | Gdańsk | Młode Miasto | 45,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0159 | Stocznia Park | Gdańsk | Młode Miasto | 54,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0160 | Stocznia Park | Gdańsk | Młode Miasto | 64,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0161 | Stocznia Park | Gdańsk | Młode Miasto | 64,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0162 | Stocznia Park | Gdańsk | Młode Miasto | 30,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0163 | Stocznia Park | Gdańsk | Młode Miasto | 66,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0164 | Stocznia Park | Gdańsk | Młode Miasto | 102,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0165 | Stocznia Park | Gdańsk | Młode Miasto | 29,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0166 | Stocznia Park | Gdańsk | Młode Miasto | 39,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0167 | Stocznia Park | Gdańsk | Młode Miasto | 53,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0168 | Stocznia Park | Gdańsk | Młode Miasto | 44,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0169 | Stocznia Park | Gdańsk | Młode Miasto | 67,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0170 | Stocznia Park | Gdańsk | Młode Miasto | 65,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0171 | Stocznia Park | Gdańsk | Młode Miasto | 46,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0172 | Stocznia Park | Gdańsk | Młode Miasto | 37,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0173 | Stocznia Park | Gdańsk | Młode Miasto | 87,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0174 | Stocznia Park | Gdańsk | Młode Miasto | 22,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0175 | Stocznia Park | Gdańsk | Młode Miasto | 61,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0176 | Stocznia Park | Gdańsk | Młode Miasto | 60,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0177 | Stocznia Park | Gdańsk | Młode Miasto | 38,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0178 | Stocznia Park | Gdańsk | Młode Miasto | 75,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0179 | Stocznia Park | Gdańsk | Młode Miasto | 50,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0180 | Stocznia Park | Gdańsk | Młode Miasto | 39,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0181 | Stocznia Park | Gdańsk | Młode Miasto | 75,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0182 | Stocznia Park | Gdańsk | Młode Miasto | 59,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0183 | Stocznia Park | Gdańsk | Młode Miasto | 115,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0184 | Stocznia Park | Gdańsk | Młode Miasto | 115,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0185 | Stocznia Park | Gdańsk | Młode Miasto | 45,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0186 | Stocznia Park | Gdańsk | Młode Miasto | 74,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80); Nietypowy typ lokalu: 2-pokojowy o metrażu 74,0 m², w treningu 2-pokojowe mają 20,7–66,9 m² (p0,5–p99,5) |
| B38-0187 | Stocznia Park | Gdańsk | Młode Miasto | 68,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0188 | Stocznia Park | Gdańsk | Młode Miasto | 85,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0189 | Stocznia Park | Gdańsk | Młode Miasto | 40,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0190 | Stocznia Park | Gdańsk | Młode Miasto | 89,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0191 | Stocznia Park | Gdańsk | Młode Miasto | 30,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0192 | Stocznia Park | Gdańsk | Młode Miasto | 22,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0193 | Stocznia Park | Gdańsk | Młode Miasto | 32,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0194 | Stocznia Park | Gdańsk | Młode Miasto | 29,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0195 | Stocznia Park | Gdańsk | Młode Miasto | 73,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0196 | Stocznia Park | Gdańsk | Młode Miasto | 88,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0197 | Stocznia Park | Gdańsk | Młode Miasto | 56,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0198 | Stocznia Park | Gdańsk | Młode Miasto | 112,7 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0199 | Stocznia Park | Gdańsk | Młode Miasto | 80,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0200 | Stocznia Park | Gdańsk | Młode Miasto | 115,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0201 | Stocznia Park | Gdańsk | Młode Miasto | 27,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0202 | Stocznia Park | Gdańsk | Młode Miasto | 40,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0203 | Stocznia Park | Gdańsk | Młode Miasto | 35,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0204 | Stocznia Park | Gdańsk | Młode Miasto | 39,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0205 | Stocznia Park | Gdańsk | Młode Miasto | 30,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0206 | Stocznia Park | Gdańsk | Młode Miasto | 46,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0207 | Stocznia Park | Gdańsk | Młode Miasto | 39,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0208 | Stocznia Park | Gdańsk | Młode Miasto | 27,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0209 | Stocznia Park | Gdańsk | Młode Miasto | 39,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0210 | Stocznia Park | Gdańsk | Młode Miasto | 77,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0211 | Stocznia Park | Gdańsk | Młode Miasto | 108,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0212 | Stocznia Park | Gdańsk | Młode Miasto | 39,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0213 | Stocznia Park | Gdańsk | Młode Miasto | 41,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0214 | Stocznia Park | Gdańsk | Młode Miasto | 43,1 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0215 | Stocznia Park | Gdańsk | Młode Miasto | 67,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0216 | Stocznia Park | Gdańsk | Młode Miasto | 68,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0217 | Stocznia Park | Gdańsk | Młode Miasto | 35,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0218 | Stocznia Park | Gdańsk | Młode Miasto | 35,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0219 | Stocznia Park | Gdańsk | Młode Miasto | 32,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0220 | Stocznia Park | Gdańsk | Młode Miasto | 56,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0221 | Stocznia Park | Gdańsk | Młode Miasto | 52,4 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0222 | Stocznia Park | Gdańsk | Młode Miasto | 34,5 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0223 | Stocznia Park | Gdańsk | Młode Miasto | 48,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0224 | Stocznia Park | Gdańsk | Młode Miasto | 115,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0225 | Stocznia Park | Gdańsk | Młode Miasto | 43,0 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0226 | Stocznia Park | Gdańsk | Młode Miasto | 71,6 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0227 | Stocznia Park | Gdańsk | Młode Miasto | 40,9 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0228 | Stocznia Park | Gdańsk | Młode Miasto | 29,3 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0229 | Stocznia Park | Gdańsk | Młode Miasto | 40,2 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |
| B38-0230 | Stocznia Park | Gdańsk | Młode Miasto | 105,8 | Dzielnica Młode Miasto (Gdańsk): 11 transakcji w zbiorze treningowym (wymagane co najmniej 80) |

## SQL i kod

Raport tworzy krok `raport-kwartalny` funkcji Inngest `wyceny-nocne` (`api/api/inngest_app.py`) przez
`api.contexts_boundaries.valuation_bc.nocne.przebieg_raportu` i `raport_bank.raport`. Ręcznie, z katalogu `api/`:
`poetry run python -m api.contexts_boundaries.valuation_bc.nocne --nadpisz-raport`.

Najnowsza wycena każdego lokalu (`api/api/adapters/wyceny_historia.py`):

```sql
SELECT * FROM wyceny_historia
WHERE rodzaj = 'lokal'
QUALIFY row_number() OVER (PARTITION BY rodzaj, id_obiektu ORDER BY czas_przebiegu DESC) = 1;
```

Operaty kontrolne z kwartału (`$od` = 2026-07-01, `$do_wylacznie` = 2026-10-01):

```sql
SELECT o.id_operatu, o.id_lokalu, o.data_wyceny, o.wartosc_pln AS wartosc_operatu, b.miasto, b.nazwa AS budynek
FROM operaty o JOIN pms_lokale l USING (id_lokalu) JOIN pms_budynki b USING (id_budynku)
WHERE o.typ = 'kontrolny' AND o.data_wyceny >= $od AND o.data_wyceny < $do_wylacznie
ORDER BY o.id_lokalu
```

Portfel i ostatni operat roczny:

```sql
SELECT l.id_lokalu, b.nazwa AS budynek, b.miasto, b.dzielnica, l.metraz, r.wartosc_pln AS operat_roczny,
       r.data_wyceny AS data_operatu_rocznego
FROM pms_lokale l
JOIN pms_budynki b USING (id_budynku)
LEFT JOIN (
    SELECT id_lokalu, wartosc_pln, data_wyceny FROM operaty WHERE typ = 'roczny'
    QUALIFY row_number() OVER (PARTITION BY id_lokalu ORDER BY data_wyceny DESC) = 1
) r USING (id_lokalu)
ORDER BY l.id_lokalu
```

Metryki: `metryki_operatow` (MAPE = średnia |P50 / operat − 1| na przyjętych, pokrycie = odsetek operatów w
[P10; P90]), `portfel` (sumy P50, P10, P90 lokali przyjętych), `rodzaje_powodow` (prefiksy powodów detektora OOD
`versions/v3_przedzialy/ood.py`). Warunki banku: `bank_mape_max_proc`, `bank_pokrycie_min_proc`,
`bank_pokrycie_max_proc` z `valuation_bc/zalozenia.yaml`.
