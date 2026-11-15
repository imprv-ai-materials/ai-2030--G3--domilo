# B1. Dane do wyceny lokali: transakcje RCN, oferty, dopasowania, operaty i podział czasowy

Źródło: `domilo.duckdb` zbudowana z `data/` (eksport 2026-09-30 23:59 Europe/Warsaw) przez `pypyr baza`.
Policzono 2026-11-15. Wszystkie liczby pochodzą z zapytań w sekcji [SQL i kod](#sql-i-kod)
(nazwa zapytania podana przy każdej tabeli).

Kontekst: wycena ma zastąpić roczne operaty dla banku (warunki banku: MAPE ≤ 8% na operatach kontrolnych, przedział
80% z pokryciem 77–83%, odpowiedź „nie wiem” dla przypadków niepewnych). Zmienna celu to **cena transakcyjna**
z `rcn_transakcje` (`cena_pln`, `cena_m2`), nie cena ofertowa.

## Wnioski

Do nauki modelu mamy 54 000 transakcji z 6 miast Domilo (akty 2023-01-01 – 2026-06-30, od 1 054 do 1 428
miesięcznie), a typowe mieszkanie kosztowało 511 tys. zł, czyli 14 054 zł/m² (od 8 611 zł/m² w Łodzi do
16 035 zł/m² w Warszawie). Ceny rosną: w okresie testowym mediana ceny m² jest w każdym mieście o 6,0–8,4% wyższa niż
w treningu, czyli prawie o cały dopuszczalny błąd 8%, więc model musi uwzględniać czas transakcji. Rejestr publikuje
transakcję 60–120 dni po akcie (mediana 90 dni, bez względu na miasto i cenę), więc wycena na dany dzień może
korzystać tylko z transakcji już opublikowanych i nie widzi ostatnich dwóch miesięcy. Podział czasowy daje 38 522
transakcje w treningu, 7 686 w walidacji i 7 487 w teście (bez 305 transakcji z czerwca 2026 opublikowanych dopiero
po dniu eksportu). Bank sprawdzi model na 300 operatach kontrolnych z września 2026: dotyczą one naszych lokali,
a nie transakcji, i powstały 2–3 miesiące po końcu zbioru testowego.

## Tabele

### 1. Co oznacza jeden wiersz

| Tabela | 1 wiersz = | Klucz | Wiersze | Okres | Uwagi |
|---|---|---|---:|---|---|
| `rcn_transakcje` | jedna transakcja sprzedaży lokalu z rejestru cen (akt notarialny) | `id_transakcji` (unikalny) | 54 000 | `data_aktu` 2023-01-01 – 2026-06-30 | **target**: `cena_pln`, `cena_m2`; data aktu bez godziny; brak pustych cen i metraży |
| `radar_oferty` | jedno ogłoszenie sprzedaży na jednym portalu | `id_oferty` (unikalny) | 176 859 | `data_publikacji` 2023-01-01 – 2026-10-03 | ten sam lokal bywa na kilku portalach: 21 445 lokali ma 42 938 ogłoszeń |
| `radar_dopasowania` | para oferta ↔ transakcja (to samo mieszkanie) z pewnością dopasowania | para `id_transakcji` + `id_oferty`, każdy unikalny (1:1) | 20 500 | — | `pewnosc` 0,8–1,0; 38,0% transakcji ma dopasowaną ofertę |
| `operaty` | jedna wycena rzeczoznawcy dla jednego lokalu Domilo albo jednej oferty | `id_operatu` (unikalny) | 21 420 | `data_wyceny` 2023-12-15 – 2026-09-28 | 3 typy: roczny, kontrolny, due diligence (tabela 1e) |

#### 1a. `rcn_transakcje`: kontrola klucza i ceny (zapytania `1a_rcn_klucz`, `1b_rcn_duplikaty`)

| Wiersze | Różne `id_transakcji` | Pierwszy akt | Ostatni akt | `data_aktu` z godziną | `cena_m2` ≠ `cena_pln / metraz` o > 0,5 zł | Rynek wtórny | Rynek pierwotny | Puste cena / metraż |
|---:|---:|---|---|---:|---:|---:|---:|---:|
| 54 000 | 54 000 | 2023-01-01 | 2026-06-30 | 0 | 0 | 50 951 | 3 049 | 0 |

`cena_m2` to `cena_pln / metraz` zaokrąglona do złotówki. W 68 wierszach iloraz kończy się na ,5 i zaokrąglono go
w dół, a nie w górę. Ten sam lokal (współrzędne, metraż, piętro, pokoje) pojawia się dwa razy w 22 przypadkach
(44 transakcje), zawsze z różną datą aktu. To prawdopodobnie odsprzedaż, a nie duplikat.

#### 1b. `radar_oferty`: ogłoszenia według portali (zapytania `1c_oferty_klucz`, `1d_oferty_portale`)

| Portal | Ogłoszenia | W pakiecie dewelopera | Rynek pierwotny | Katowice | Cena ≤ 0 | Opublikowane po dniu eksportu |
|---|---:|---:|---:|---:|---:|---:|
| **razem** | 176 859 | 1 726 | 9 360 | 1 240 | 1 | 16 |
| lokum24 | 81 013 | 0 | 3 532 | 503 | 1 | 2 |
| domteraz | 60 519 | 0 | 2 643 | 397 | 0 | 7 |
| sprzedajemy_mieszkania | 33 601 | 0 | 1 459 | 160 | 0 | 7 |
| deweloper | 1 726 | 1 726 | 1 726 | 180 | 0 | 0 |

| Ogłoszenia | Różne lokale | Lokale w > 1 ogłoszeniu | Ich ogłoszenia | W tym każde ogłoszenie na innym portalu |
|---:|---:|---:|---:|---:|
| 176 859 | 155 366 | 21 445 | 42 938 | 21 361 |

Oferty to cena **ofertowa**, nie transakcyjna. Zawierają też miasto spoza Domilo (Katowice, 1 240 ogłoszeń; w RCN
Katowic nie ma) i jedną ofertę z ujemną ceną. Przy liczeniu cech z ofert trzeba usunąć duplikaty między portalami
i brać tylko oferty opublikowane przed dniem wyceny.

#### 1c. `radar_dopasowania`: jakość par oferta ↔ transakcja (zapytanie `1e_dopasowania`)

| Pary | Różne transakcje | Różne oferty | Pewność min–max | % transakcji z ofertą | Niezgodne miasto / dzielnica / metraż / piętro | Oferta po akcie | Mediana dni od oferty do aktu | Mediana cena transakcji ÷ ofertowa | p5 | p95 |
|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 20 500 | 20 500 | 20 500 | 0,8–1,0 | 38,0 | 0 | 0 | 79 | 0,941 | 0,867 | 1,023 |

Dopasowanie jest jeden do jednego i spójne: każda para ma to samo miasto, dzielnicę, metraż i piętro, a oferta
zawsze poprzedza akt. Typowa transakcja zamyka się na 94,1% ceny ofertowej. Dlatego cena ofertowa nie może być
targetem, bo zawyżałaby wycenę.

#### 1d. `operaty`: typy wycen (zapytania `1f_operaty`, `1g_operaty_roczne`, `1h_operaty_powiazania`)

| Typ | Operaty | Z `id_lokalu` | Różne lokale | Z `id_oferty` | Od | Do | Wykonawcy | Mediana wartości (zł) |
|---|---:|---:|---:|---:|---|---|---:|---:|
| roczny | 21 080 | 21 080 | 7 200 | 0 | 2023-12-15 | 2025-12-12 | 3 | 736 000 |
| kontrolny | 300 | 300 | 300 | 0 | 2026-09-01 | 2026-09-28 | 3 | 799 000 |
| due_diligence | 40 | 0 | 0 | 40 | 2026-09-01 | 2026-09-28 | 4 | 362 500 |

| Miesiąc operatów rocznych | Operaty | Lokale |
|---|---:|---:|
| 2023-12 | 6 680 | 6 680 |
| 2024-12 | 7 200 | 7 200 |
| 2025-12 | 7 200 | 7 200 |

| Typ | Lokal istnieje w PMS | Oferta istnieje w Radarze | Oferta z pakietu dewelopera | Oferta z transakcją RCN | Lokal ma też operat roczny |
|---|---:|---:|---:|---:|---:|
| kontrolny | 300 | 0 | 0 | 0 | 300 |
| due_diligence | 0 | 40 | 40 | 0 | 0 |

Operat roczny: co roku w grudniu wycena każdego lokalu Domilo (7 200 lokali w 2024 i 2025, 6 680 w 2023). Operat
kontrolny: 300 lokali Domilo wycenionych we wrześniu 2026, na nich bank liczy MAPE. RCN nie ma identyfikatora
lokalu, więc operatu kontrolnego nie połączymy z transakcją. Model uczony na transakcjach rynkowych wycenia tu lokal
Domilo na podstawie jego cech z PMS.
Due diligence: 40 ofert z pakietów deweloperów (kandydaci do zakupu), bez transakcji RCN.

### 2. Rozkład cen transakcyjnych w miastach

#### 2a. Cała historia RCN, akty 2023-01-01 – 2026-06-30 (zapytanie `2a_ceny_miasta`)

Ceny zaokrąglone do 1 000 zł, ceny m² do 1 zł; p5 / p95 = 5. i 95. percentyl.

| Miasto | Transakcje | Cena: mediana | Cena: p5 | Cena: p95 | Cena m²: mediana | Cena m²: p5 | Cena m²: p95 | Metraż: mediana |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **razem** | 54 000 | 511 000 | 242 000 | 1 383 000 | 14 054 | 8 120 | 21 191 | 36,1 |
| Warszawa | 21 509 | 582 000 | 292 000 | 1 533 000 | 16 035 | 10 024 | 22 589 | 36,4 |
| Kraków | 9 147 | 519 000 | 269 000 | 1 386 000 | 14 583 | 9 236 | 20 516 | 35,8 |
| Wrocław | 8 144 | 493 000 | 259 000 | 1 319 000 | 13 833 | 9 045 | 18 723 | 36,1 |
| Poznań | 5 500 | 416 000 | 226 000 | 1 115 000 | 11 550 | 8 140 | 15 873 | 35,6 |
| Gdańsk | 5 381 | 491 000 | 256 000 | 1 299 000 | 13 510 | 9 341 | 18 889 | 36,0 |
| Łódź | 4 319 | 324 000 | 163 000 | 837 000 | 8 611 | 5 943 | 12 303 | 36,4 |

#### 2b. Mediana ceny m² w zbiorach podziału (zapytanie `2b_cena_m2_miasta_zbiory`)

| Miasto | Trening 2023-01 – 2025-06 | Walidacja 2025-07 – 2025-12 | Test 2026-01 – 2026-06 | Test vs trening |
|---|---:|---:|---:|---:|
| Warszawa | 15 789 | 16 568 | 16 735 | +6,0% |
| Kraków | 14 370 | 14 946 | 15 292 | +6,4% |
| Wrocław | 13 608 | 14 105 | 14 527 | +6,7% |
| Gdańsk | 13 246 | 14 091 | 14 354 | +8,4% |
| Poznań | 11 373 | 12 086 | 12 125 | +6,6% |
| Łódź | 8 485 | 8 725 | 9 027 | +6,4% |

#### 2c. Ceny nietypowe względem dzielnicy (zapytanie `2c_ceny_nietypowe`)

Opisowo: mediana ceny m² dzielnicy z całego okresu (do modelu takiej mediany nie wolno liczyć z przyszłości).

| Cena m² względem mediany dzielnicy | Transakcje | W tym cena dokładnie 60 000 zł | Min cena m² | Max cena m² |
|---|---:|---:|---:|---:|
| < 0,5 × | 149 | 45 | 1 054 | 8 314 |
| 0,5–2 × | 53 813 | 0 | 3 662 | 37 846 |
| > 2 × | 38 | 0 | 14 828 | 70 917 |

187 transakcji (0,3%) ma cenę m² poniżej połowy albo powyżej dwukrotności mediany dzielnicy. 45 z nich ma cenę
dokładnie 60 000 zł, czyli najniższą cenę w rejestrze, niezależnie od metrażu. To wygląda na transakcje nierynkowe
(np. sprzedaż w rodzinie, wykup). Podział ich nie usuwa: o filtrze zdecydujemy przy budowie modelu.

### 3. Liczba transakcji na miesiąc (zapytania `3_transakcje_miesiac`, `3b_transakcje_miesiac_podsumowanie`)

Miesiąc = miesiąc `data_aktu`. Ostatnia kolumna: transakcje opublikowane w rejestrze po dniu eksportu (od 2026-10-01).

| Miesiąc aktu | Razem | Warszawa | Kraków | Wrocław | Poznań | Gdańsk | Łódź | Opublikowane po eksporcie |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023-01 | 1 181 | 499 | 182 | 195 | 116 | 101 | 88 | 0 |
| 2023-02 | 1 112 | 434 | 203 | 170 | 110 | 112 | 83 | 0 |
| 2023-03 | 1 370 | 548 | 215 | 205 | 144 | 140 | 118 | 0 |
| 2023-04 | 1 260 | 489 | 233 | 203 | 128 | 116 | 91 | 0 |
| 2023-05 | 1 391 | 581 | 201 | 195 | 152 | 148 | 114 | 0 |
| 2023-06 | 1 284 | 501 | 216 | 177 | 141 | 144 | 105 | 0 |
| 2023-07 | 1 217 | 499 | 209 | 176 | 126 | 117 | 90 | 0 |
| 2023-08 | 1 274 | 508 | 223 | 183 | 117 | 144 | 99 | 0 |
| 2023-09 | 1 271 | 542 | 215 | 161 | 128 | 129 | 96 | 0 |
| 2023-10 | 1 428 | 571 | 239 | 233 | 140 | 137 | 108 | 0 |
| 2023-11 | 1 394 | 554 | 235 | 197 | 142 | 143 | 123 | 0 |
| 2023-12 | 1 183 | 477 | 197 | 183 | 117 | 118 | 91 | 0 |
| 2024-01 | 1 262 | 476 | 232 | 205 | 125 | 115 | 109 | 0 |
| 2024-02 | 1 161 | 456 | 206 | 164 | 111 | 128 | 96 | 0 |
| 2024-03 | 1 304 | 502 | 240 | 204 | 116 | 132 | 110 | 0 |
| 2024-04 | 1 400 | 557 | 231 | 213 | 153 | 139 | 107 | 0 |
| 2024-05 | 1 428 | 582 | 233 | 234 | 135 | 132 | 112 | 0 |
| 2024-06 | 1 182 | 437 | 213 | 177 | 146 | 139 | 70 | 0 |
| 2024-07 | 1 283 | 525 | 222 | 185 | 133 | 122 | 96 | 0 |
| 2024-08 | 1 249 | 498 | 209 | 217 | 119 | 117 | 89 | 0 |
| 2024-09 | 1 283 | 527 | 212 | 181 | 119 | 138 | 106 | 0 |
| 2024-10 | 1 387 | 562 | 253 | 185 | 138 | 141 | 108 | 0 |
| 2024-11 | 1 319 | 517 | 226 | 202 | 132 | 133 | 109 | 0 |
| 2024-12 | 1 189 | 504 | 196 | 175 | 102 | 114 | 98 | 0 |
| 2025-01 | 1 223 | 471 | 223 | 191 | 123 | 121 | 94 | 0 |
| 2025-02 | 1 054 | 401 | 176 | 167 | 113 | 107 | 90 | 0 |
| 2025-03 | 1 354 | 528 | 210 | 209 | 143 | 137 | 127 | 0 |
| 2025-04 | 1 402 | 545 | 269 | 200 | 145 | 127 | 116 | 0 |
| 2025-05 | 1 423 | 540 | 263 | 206 | 163 | 128 | 123 | 0 |
| 2025-06 | 1 254 | 489 | 218 | 191 | 139 | 131 | 86 | 0 |
| 2025-07 | 1 300 | 510 | 210 | 206 | 122 | 140 | 112 | 0 |
| 2025-08 | 1 176 | 455 | 186 | 192 | 123 | 132 | 88 | 0 |
| 2025-09 | 1 283 | 523 | 207 | 199 | 131 | 114 | 109 | 0 |
| 2025-10 | 1 412 | 557 | 223 | 221 | 163 | 134 | 114 | 0 |
| 2025-11 | 1 244 | 511 | 204 | 168 | 152 | 117 | 92 | 0 |
| 2025-12 | 1 271 | 536 | 223 | 206 | 107 | 108 | 91 | 0 |
| 2026-01 | 1 213 | 474 | 208 | 204 | 110 | 116 | 101 | 0 |
| 2026-02 | 1 134 | 450 | 203 | 162 | 123 | 107 | 89 | 0 |
| 2026-03 | 1 356 | 547 | 204 | 219 | 149 | 140 | 97 | 0 |
| 2026-04 | 1 383 | 536 | 235 | 225 | 139 | 132 | 116 | 0 |
| 2026-05 | 1 349 | 529 | 226 | 172 | 137 | 149 | 136 | 0 |
| 2026-06 | 1 357 | 561 | 218 | 186 | 128 | 142 | 122 | 305 |

Miesięcznie: minimum 1 054 (2025-02), mediana 1 283, maksimum 1 428 (2023-10 i 2024-05).

### 4. Opóźnienie publikacji w rejestrze: `data_publikacji_rejestru − data_aktu` (dni)

#### 4a. Według roku aktu (zapytanie `4a_opoznienie`)

| Rok aktu | Transakcje | Min | p5 | p25 | Mediana | p75 | p95 | Max | Korelacja z ceną m² |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 | 15 365 | 60 | 63 | 74 | 90 | 106 | 117 | 120 | −0,021 |
| 2024 | 15 447 | 60 | 63 | 75 | 90 | 106 | 117 | 120 | −0,009 |
| 2025 | 15 396 | 60 | 63 | 75 | 90 | 106 | 117 | 120 | 0,004 |
| 2026 | 7 792 | 60 | 63 | 75 | 90 | 106 | 117 | 120 | −0,005 |
| **razem** | 54 000 | 60 | 63 | 75 | 90 | 106 | 117 | 120 | −0,007 |

#### 4b. Rozkład (zapytanie `4b_opoznienie_kubelki`)

| Dni | Transakcje | % |
|---|---:|---:|
| 60–69 | 8 876 | 16,4 |
| 70–79 | 8 854 | 16,4 |
| 80–89 | 8 872 | 16,4 |
| 90–99 | 8 666 | 16,0 |
| 100–109 | 8 878 | 16,4 |
| 110–119 | 9 002 | 16,7 |
| 120 | 852 | 1,6 |

W każdym mieście mediana wynosi 90 dni, p5 62–63, p95 117 (zapytanie `4c_opoznienie_miasta`). Opóźnienie rozkłada
się równomiernie w przedziale 60–120 dni i nie zależy od roku, miasta ani ceny.

#### 4c. Co było znane w dniu eksportu (zapytanie `4d_kompletnosc_w_dniu_eksportu`)

| Miesiąc aktu | Transakcje | Opublikowane do 2026-09-30 | % |
|---|---:|---:|---:|
| 2026-04 | 1 383 | 1 383 | 100,0 |
| 2026-05 | 1 349 | 1 349 | 100,0 |
| 2026-06 | 1 357 | 1 052 | 77,5 |

Skutek dla modelu: cechy rynkowe (np. mediana ceny m² w dzielnicy z ostatnich miesięcy) liczone na dzień wyceny D
mogą używać tylko transakcji z `data_publikacji_rejestru < D`, a nie z `data_aktu < D`. Transakcje z ostatnich
60 dni przed D nie są jeszcze znane, a z okresu 60–120 dni przed D znana jest tylko część.

### 5. Podział czasowy (definicja: [`api/api/ai/features/wycena/podzial.sql`](../api/api/ai/features/wycena/podzial.sql))

Zbiór wyznacza `data_aktu`: trening 2023-01-01 – 2025-06-30, walidacja 2025-07-01 – 2025-12-31, test
2026-01-01 – 2026-06-30. Pomijamy transakcje z `data_publikacji_rejestru` po dniu eksportu, bo 2026-09-30 nie były
jeszcze znane.

#### 5a. Liczności (zapytania `5a_podzial`, `5b_poza_podzialem`)

| Zbiór | Transakcje | Od | Do | Miesiące | Warszawa | Kraków | Wrocław | Poznań | Gdańsk | Łódź | Rynek pierwotny | Z dopasowaną ofertą |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trening | 38 522 | 2023-01-01 | 2025-06-30 | 30 | 15 320 | 6 600 | 5 784 | 3 916 | 3 850 | 3 052 | 2 294 | 14 361 |
| walidacja | 7 686 | 2025-07-01 | 2025-12-31 | 6 | 3 092 | 1 253 | 1 192 | 798 | 745 | 606 | 464 | 3 139 |
| test | 7 487 | 2026-01-01 | 2026-06-30 | 6 | 2 978 | 1 252 | 1 122 | 754 | 750 | 631 | 283 | 2 882 |
| **razem** | 53 695 | 2023-01-01 | 2026-06-30 | 42 | 21 390 | 9 105 | 8 098 | 5 468 | 5 345 | 4 289 | 3 041 | 20 382 |

| Wszystkie transakcje RCN | W podziale | Poza podziałem | W tym opublikowane po dniu eksportu |
|---:|---:|---:|---:|
| 54 000 | 53 695 | 305 | 305 |

#### 5b. Udział rynku pierwotnego w półroczach (zapytanie `5c_rynek_pierwotny_polrocza`, wszystkie transakcje)

| Półrocze | Transakcje | Rynek pierwotny | % |
|---|---:|---:|---:|
| 2023-H1 | 7 598 | 465 | 6,1 |
| 2023-H2 | 7 767 | 443 | 5,7 |
| 2024-H1 | 7 737 | 469 | 6,1 |
| 2024-H2 | 7 710 | 439 | 5,7 |
| 2025-H1 | 7 710 | 478 | 6,2 |
| 2025-H2 | 7 686 | 464 | 6,0 |
| 2026-H1 | 7 792 | 291 | 3,7 |

W teście udział rynku pierwotnego spada z 5,7–6,2% do 3,7%. Zbiór testowy różni się więc od treningowego nie tylko
poziomem cen (tabela 2b), ale też strukturą. Warto liczyć metryki osobno dla rynku pierwotnego i wtórnego.

## SQL i kod

Wszystkie zapytania są w [`api/api/ai/features/wycena/opis_danych_b1.py`](../api/api/ai/features/wycena/opis_danych_b1.py)
(słownik `ZAPYTANIA`) i działają na `domilo.duckdb` przez `api.adapters.duckdb_baza.polacz()` (strefa sesji
Europe/Warsaw). Wszystkie tabele raportu odtworzysz poleceniem:

```bash
pypyr baza                     # jeśli domilo.duckdb nie istnieje albo data/ się zmieniło
cd api && poetry run python -m api.ai.features.wycena.opis_danych_b1            # wszystkie zapytania
cd api && poetry run python -m api.ai.features.wycena.opis_danych_b1 5a_podzial # wybrane
```

Podział czasowy jest w [`podzial.sql`](../api/api/ai/features/wycena/podzial.sql), a w Pythonie wczytuje go
`api.ai.features.wycena.podzial.podzial(con)`. Granice zbiorów sprawdza test `api/tests/test_wycena_podzial.py`
(`pypyr test tests=api/tests/test_wycena_podzial.py`). W zapytaniach niżej `(<podzial.sql>)` oznacza treść tego
pliku wstawioną jako podzapytanie.

### Definicja podziału: `api/api/ai/features/wycena/podzial.sql`

```sql
SELECT
    t.id_transakcji,
    t.data_aktu,
    t.data_publikacji_rejestru,
    CASE
        WHEN t.data_aktu >= TIMESTAMP '2023-01-01' AND t.data_aktu < TIMESTAMP '2025-07-01' THEN 'trening'
        WHEN t.data_aktu >= TIMESTAMP '2025-07-01' AND t.data_aktu < TIMESTAMP '2026-01-01' THEN 'walidacja'
        WHEN t.data_aktu >= TIMESTAMP '2026-01-01' AND t.data_aktu < TIMESTAMP '2026-07-01' THEN 'test'
    END AS zbior
FROM rcn_transakcje AS t
WHERE t.data_aktu >= TIMESTAMP '2023-01-01'
  AND t.data_aktu < TIMESTAMP '2026-07-01'
  AND t.data_publikacji_rejestru < TIMESTAMP '2026-10-01'
```

### Zapytania raportu

`1a_rcn_klucz`:

```sql
SELECT count(*) AS wiersze,
       count(DISTINCT id_transakcji) AS rozne_id,
       min(data_aktu)::DATE AS pierwszy_akt,
       max(data_aktu)::DATE AS ostatni_akt,
       count(*) FILTER (data_aktu <> date_trunc('day', data_aktu)) AS akt_z_godzina,
       count(*) FILTER (abs(cena_m2 - cena_pln / metraz) > 0.5) AS cena_m2_rozna_od_ilorazu_o_ponad_0_5_zl,
       count(*) FILTER (cena_m2 <> round(cena_pln / metraz)) AS cena_m2_inaczej_zaokraglona,
       count(*) FILTER (rynek = 'wtorny') AS rynek_wtorny,
       count(*) FILTER (rynek = 'pierwotny') AS rynek_pierwotny,
       count(*) FILTER (cena_pln IS NULL OR metraz IS NULL) AS braki_ceny_lub_metrazu
FROM rcn_transakcje;
```

`1b_rcn_duplikaty`:

```sql
-- Czy ten sam lokal (współrzędne, metraż, piętro, pokoje) występuje kilka razy
SELECT count(*) AS grupy, sum(n) AS transakcje, max(n) AS max_w_grupie,
       count(*) FILTER (rozne_daty = 1) AS grupy_z_tym_samym_dniem_aktu
FROM (SELECT count(*) AS n, count(DISTINCT data_aktu) AS rozne_daty
      FROM rcn_transakcje GROUP BY lat, lon, metraz, pietro, pokoje HAVING count(*) > 1);
```

`1c_oferty_klucz`:

```sql
WITH grupy AS (  -- ten sam lokal = te same współrzędne, metraż, piętro i rok budowy
    SELECT count(*) AS n, count(DISTINCT portal) AS portale
    FROM radar_oferty GROUP BY lat, lon, metraz, pietro, rok_budowy
)
SELECT (SELECT count(*) FROM radar_oferty) AS wiersze,
       (SELECT count(DISTINCT id_oferty) FROM radar_oferty) AS rozne_id,
       count(*) AS rozne_lokale,
       count(*) FILTER (n > 1) AS lokale_w_wielu_ogloszeniach,
       sum(n) FILTER (n > 1) AS ogloszenia_tych_lokali,
       count(*) FILTER (n > 1 AND portale = n) AS w_tym_kazde_na_innym_portalu
FROM grupy;
```

`1d_oferty_portale`:

```sql
SELECT coalesce(portal, 'RAZEM') AS portal, count(*) AS ogloszenia, count(id_pakietu) AS w_pakiecie_dewelopera,
       count(*) FILTER (rynek = 'pierwotny') AS rynek_pierwotny,
       count(*) FILTER (miasto = 'Katowice') AS katowice,
       count(*) FILTER (cena_ofertowa <= 0) AS cena_niedodatnia,
       count(*) FILTER (data_publikacji >= TIMESTAMP '2026-10-01') AS po_dniu_eksportu
FROM radar_oferty GROUP BY ROLLUP (portal) ORDER BY ogloszenia DESC;
```

`1e_dopasowania`:

```sql
SELECT count(*) AS pary,
       count(DISTINCT id_transakcji) AS rozne_transakcje,
       count(DISTINCT id_oferty) AS rozne_oferty,
       min(d.pewnosc) AS min_pewnosc, max(d.pewnosc) AS max_pewnosc,
       round(100.0 * count(*) / (SELECT count(*) FROM rcn_transakcje), 1) AS proc_transakcji_z_oferta,
       count(*) FILTER (o.miasto <> t.miasto OR o.dzielnica <> t.dzielnica OR o.metraz <> t.metraz
                        OR o.pietro <> t.pietro) AS niezgodne_cechy,
       count(*) FILTER (o.data_publikacji > t.data_aktu) AS oferta_po_akcie,
       median(date_diff('day', o.data_publikacji, t.data_aktu)) AS mediana_dni_oferta_do_aktu,
       round(median(t.cena_pln / o.cena_ofertowa), 3) AS mediana_cena_transakcji_do_ofertowej,
       round(quantile_cont(t.cena_pln / o.cena_ofertowa, 0.05), 3) AS p5_relacji,
       round(quantile_cont(t.cena_pln / o.cena_ofertowa, 0.95), 3) AS p95_relacji
FROM radar_dopasowania d
JOIN rcn_transakcje t USING (id_transakcji)
JOIN radar_oferty o USING (id_oferty);
```

`1f_operaty`:

```sql
SELECT typ, count(*) AS operaty,
       count(id_lokalu) AS z_id_lokalu, count(DISTINCT id_lokalu) AS rozne_lokale,
       count(id_oferty) AS z_id_oferty,
       strftime(min(data_wyceny), '%Y-%m-%d') AS od, strftime(max(data_wyceny), '%Y-%m-%d') AS do,
       count(DISTINCT wykonawca) AS wykonawcy,
       median(wartosc_pln) AS mediana_wartosci
FROM operaty GROUP BY typ ORDER BY operaty DESC;
```

`1g_operaty_roczne`:

```sql
SELECT strftime(data_wyceny, '%Y-%m') AS miesiac, count(*) AS operaty_roczne, count(DISTINCT id_lokalu) AS lokale
FROM operaty WHERE typ = 'roczny' GROUP BY ALL ORDER BY miesiac;
```

`1h_operaty_powiazania`:

```sql
-- Operaty kontrolne -> lokale Domilo; operaty due diligence -> oferty z pakietów deweloperów
SELECT o.typ,
       count(*) FILTER (l.id_lokalu IS NOT NULL) AS lokal_w_pms,
       count(*) FILTER (r.id_oferty IS NOT NULL) AS oferta_w_radarze,
       count(*) FILTER (r.id_pakietu IS NOT NULL) AS oferta_z_pakietu,
       count(*) FILTER (d.id_oferty IS NOT NULL) AS oferta_z_transakcja_rcn,
       count(*) FILTER (o.typ = 'kontrolny' AND EXISTS (
           SELECT 1 FROM operaty x WHERE x.typ = 'roczny' AND x.id_lokalu = o.id_lokalu)) AS lokal_ma_tez_operat_roczny
FROM operaty o
LEFT JOIN pms_lokale l USING (id_lokalu)
LEFT JOIN radar_oferty r USING (id_oferty)
LEFT JOIN radar_dopasowania d USING (id_oferty)
WHERE o.typ <> 'roczny' GROUP BY o.typ ORDER BY o.typ;
```

`2a_ceny_miasta`:

```sql
SELECT coalesce(miasto, 'RAZEM') AS miasto, count(*) AS transakcje,
       round(median(cena_pln), -3) AS cena_mediana,
       round(quantile_cont(cena_pln, 0.05), -3) AS cena_p5,
       round(quantile_cont(cena_pln, 0.95), -3) AS cena_p95,
       round(median(cena_m2)) AS m2_mediana,
       round(quantile_cont(cena_m2, 0.05)) AS m2_p5,
       round(quantile_cont(cena_m2, 0.95)) AS m2_p95,
       round(median(metraz), 1) AS metraz_mediana
FROM rcn_transakcje GROUP BY ROLLUP (miasto) ORDER BY transakcje DESC;
```

`2b_cena_m2_miasta_zbiory`:

```sql
-- Mediana ceny m² w miastach w zbiorach podziału (zmiana poziomu cen w czasie)
SELECT t.miasto,
       round(median(t.cena_m2) FILTER (p.zbior = 'trening')) AS trening,
       round(median(t.cena_m2) FILTER (p.zbior = 'walidacja')) AS walidacja,
       round(median(t.cena_m2) FILTER (p.zbior = 'test')) AS test,
       round(100.0 * (median(t.cena_m2) FILTER (p.zbior = 'test')
                      / median(t.cena_m2) FILTER (p.zbior = 'trening') - 1), 1) AS zmiana_test_vs_trening_proc
FROM rcn_transakcje t JOIN (<podzial.sql>) p USING (id_transakcji)
GROUP BY t.miasto ORDER BY trening DESC;
```

`2c_ceny_nietypowe`:

```sql
-- Transakcje z ceną m² daleko od mediany swojej dzielnicy (mediana z całego okresu, tylko opisowo)
WITH t AS (
    SELECT *, cena_m2 / median(cena_m2) OVER (PARTITION BY miasto, dzielnica) AS wzgl
    FROM rcn_transakcje
)
SELECT CASE WHEN wzgl < 0.5 THEN '< 0,5 × mediany dzielnicy'
            WHEN wzgl <= 2 THEN '0,5–2 × mediany dzielnicy'
            ELSE '> 2 × mediany dzielnicy' END AS przedzial,
       count(*) AS transakcje,
       count(*) FILTER (cena_pln = 60000) AS cena_dokladnie_60_tys,
       min(cena_m2) AS min_cena_m2, max(cena_m2) AS max_cena_m2
FROM t GROUP BY ALL ORDER BY min_cena_m2;
```

`3_transakcje_miesiac`:

```sql
SELECT strftime(data_aktu, '%Y-%m') AS miesiac_aktu,
       count(*) AS razem,
       count(*) FILTER (miasto = 'Warszawa') AS warszawa,
       count(*) FILTER (miasto = 'Kraków') AS krakow,
       count(*) FILTER (miasto = 'Wrocław') AS wroclaw,
       count(*) FILTER (miasto = 'Poznań') AS poznan,
       count(*) FILTER (miasto = 'Gdańsk') AS gdansk,
       count(*) FILTER (miasto = 'Łódź') AS lodz,
       count(*) FILTER (data_publikacji_rejestru >= TIMESTAMP '2026-10-01') AS opublikowane_po_eksporcie
FROM rcn_transakcje GROUP BY ALL ORDER BY miesiac_aktu;
```

`3b_transakcje_miesiac_podsumowanie`:

```sql
SELECT min(n) AS min_mies, median(n) AS mediana_mies, max(n) AS max_mies
FROM (SELECT strftime(data_aktu, '%Y-%m') AS m, count(*) AS n FROM rcn_transakcje GROUP BY ALL);
```

`4a_opoznienie`:

```sql
WITH t AS (SELECT *, date_diff('day', data_aktu, data_publikacji_rejestru) AS dni FROM rcn_transakcje)
SELECT coalesce(CAST(year(data_aktu) AS VARCHAR), 'RAZEM') AS rok_aktu, count(*) AS transakcje,
       min(dni) AS min, quantile_disc(dni, 0.05) AS p5, quantile_disc(dni, 0.25) AS p25, median(dni) AS mediana,
       quantile_disc(dni, 0.75) AS p75, quantile_disc(dni, 0.95) AS p95, max(dni) AS max,
       round(corr(dni, cena_m2), 3) AS korelacja_z_cena_m2
FROM t GROUP BY ROLLUP (year(data_aktu)) ORDER BY rok_aktu;
```

`4b_opoznienie_kubelki`:

```sql
WITH t AS (SELECT date_diff('day', data_aktu, data_publikacji_rejestru) AS dni FROM rcn_transakcje)
SELECT CASE WHEN dni >= 120 THEN '120' ELSE (10 * (dni // 10)) || '–' || (10 * (dni // 10) + 9) END AS dni,
       count(*) AS transakcje, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS proc
FROM t GROUP BY ALL ORDER BY min(dni);
```

`4c_opoznienie_miasta`:

```sql
SELECT miasto, median(date_diff('day', data_aktu, data_publikacji_rejestru)) AS mediana_dni,
       quantile_disc(date_diff('day', data_aktu, data_publikacji_rejestru), 0.05) AS p5,
       quantile_disc(date_diff('day', data_aktu, data_publikacji_rejestru), 0.95) AS p95
FROM rcn_transakcje GROUP BY ALL ORDER BY miasto;
```

`4d_kompletnosc_w_dniu_eksportu`:

```sql
-- Ile transakcji z ostatnich miesięcy było znanych w dniu eksportu (opublikowane do 2026-09-30)
SELECT strftime(data_aktu, '%Y-%m') AS miesiac_aktu, count(*) AS transakcje,
       count(*) FILTER (data_publikacji_rejestru < TIMESTAMP '2026-10-01') AS znane_2026_09_30,
       round(100.0 * count(*) FILTER (data_publikacji_rejestru < TIMESTAMP '2026-10-01') / count(*), 1) AS proc
FROM rcn_transakcje WHERE data_aktu >= TIMESTAMP '2026-04-01' GROUP BY ALL ORDER BY miesiac_aktu;
```

`5a_podzial`:

```sql
WITH p AS (<podzial.sql>)
SELECT coalesce(p.zbior, 'RAZEM') AS zbior, count(*) AS transakcje,
       strftime(min(p.data_aktu), '%Y-%m-%d') AS od, strftime(max(p.data_aktu), '%Y-%m-%d') AS do,
       count(DISTINCT strftime(p.data_aktu, '%Y-%m')) AS miesiace,
       count(*) FILTER (t.miasto = 'Warszawa') AS warszawa,
       count(*) FILTER (t.miasto = 'Kraków') AS krakow,
       count(*) FILTER (t.miasto = 'Wrocław') AS wroclaw,
       count(*) FILTER (t.miasto = 'Poznań') AS poznan,
       count(*) FILTER (t.miasto = 'Gdańsk') AS gdansk,
       count(*) FILTER (t.miasto = 'Łódź') AS lodz,
       count(*) FILTER (t.rynek = 'pierwotny') AS rynek_pierwotny,
       count(d.id_oferty) AS z_dopasowana_oferta
FROM p JOIN rcn_transakcje t USING (id_transakcji) LEFT JOIN radar_dopasowania d USING (id_transakcji)
GROUP BY ROLLUP (p.zbior) ORDER BY grouping(p.zbior), min(p.data_aktu);
```

`5b_poza_podzialem`:

```sql
SELECT count(*) AS wszystkie_transakcje,
       count(p.id_transakcji) AS w_podziale,
       count(*) - count(p.id_transakcji) AS poza_podzialem,
       count(*) FILTER (p.id_transakcji IS NULL AND t.data_publikacji_rejestru >= TIMESTAMP '2026-10-01')
           AS poza_bo_opublikowane_po_eksporcie
FROM rcn_transakcje t LEFT JOIN (<podzial.sql>) p USING (id_transakcji);
```

`5c_rynek_pierwotny_polrocza`:

```sql
-- Udział rynku pierwotnego w półroczach (data_aktu), wszystkie transakcje
SELECT year(data_aktu) || '-H' || CASE WHEN month(data_aktu) <= 6 THEN 1 ELSE 2 END AS polrocze,
       count(*) AS transakcje,
       count(*) FILTER (rynek = 'pierwotny') AS rynek_pierwotny,
       round(100.0 * count(*) FILTER (rynek = 'pierwotny') / count(*), 1) AS proc_pierwotny
FROM rcn_transakcje GROUP BY ALL ORDER BY polrocze;
```
