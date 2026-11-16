# Kampania retencyjna Q4 2026: plan i pre-rejestracja

Status: **plan, kampanii nie uruchomiono.** Plan zarejestrowano 2026-11-16, przed losowaniem i przed wysłaniem
jakiejkolwiek oferty. Zmiany po tej dacie wpisujemy jako nową wersję z datą i powodem (sekcja „Odstępstwa”).
Wcześniejsza wersja tego dokumentu jest wtedy wiążąca dla części, której zmiana nie dotyczy.

## Wnioski

1. **Jeden kwartał to za mało, żeby zmierzyć efekt oferty w segmencie docelowym.** Kwartał to 1 543 kończące się
   umowy, czyli 247 ofert i tylko 62 umowy kontrolne w segmencie. Przy takiej próbie wykrywamy dopiero wzrost
   przedłużeń o 18,3 p.p. albo większy. Efekt z losowego testu 2025 (+11,4 p.p.) wymaga **3 kwartałów** kampanii
   o tym samym projekcie.
2. **Zysk w złotówkach w całym portfelu wymaga 7 kwartałów,** czyli umów kończących się do 2028-08. Oferty dostaje
   tylko 16% umów, a różnica zysku rozkłada się na cały portfel i ginie w zmienności 80% umów, którym oferty nie
   wysyłamy.
3. **Według testu 2025 ta polityka traci pieniądze:** około 866 zł na ofertę, czyli około 214 tys. zł na kwartał
   kampanii. Dlatego po pierwszym kwartale robimy jedną zaplanowaną kontrolę opłacalności. Ma ona 79% szans
   wykryć stratę tej wielkości. Jeśli strata się potwierdzi, rabat 1 800 zł rocznie nie wraca w kolejnych
   kwartałach.
4. **Metryka główna to efekt oferty (uplift) w segmencie docelowym, analiza 2027-10-15 po 3 kwartałach.** Zysk
   w portfelu jest metryką drugorzędną z analizą 2028-10-15. Sam wzrost przedłużeń nie wystarcza, żeby rabat się
   opłacał: musiałby wynieść około 39 p.p.
5. **Oferty dla umów kończących się w grudniu są spóźnione.** 529 z 538 takich umów miało termin oferty (45 dni przed
   końcem) przed 2026-11-16, więc dostaną ofertę później. Dlatego grudzień analizujemy także osobno.

## Pre-rejestracja

### Pytanie i hipoteza

- **Pytanie:** czy oferta (rabat 150 zł miesięcznie w nowej umowie) wysłana do górnych 20% upliftu modelu v3
  zwiększa odsetek przedłużeń w tym segmencie i czy się opłaca?
- **H0:** uplift w segmencie docelowym = 0, czyli % przedłużeń z ofertą = % przedłużeń w kontroli w segmencie.
- **H1:** uplift ≠ 0 (test dwustronny). Oczekujemy wartości dodatniej, około +11,4 p.p. (test 2025).

### Populacja i przydział

| Element | Definicja |
|---|---|
| Populacja | umowy roczne B2C / B2B (`pms_umowy.typ` = `pierwsza` albo `przedłużenie`, także pierwsze umowy B2B na 18 i 24 mies.), `data_do` od 2026-12-01 do 2027-02-28, bez wyprowadzki przed `data_do`, czyli definicja z `migawki_najemcy` (stan na dzień eksportu: 1 543 umowy) |
| Kontrola (20%) | losowanie na poziomie umowy, **przed** wyliczeniem upliftu: `md5_number(id_umowy \|\| ':kampania_2026q4') % 100 < 20` (DuckDB). Przydział jest deterministyczny i każdy może go sprawdzić. Kontrola nie dostaje oferty, niezależnie od upliftu |
| Uplift | `v3_uplift_tlearner` (`churn_model/versions/v3_uplift_tlearner/model.joblib`, md5 `6ab53b6118f5e68721fdcf607ca8ea72`), cechy na dzień migawki (`data_do` − 60 dni), liczony dla **wszystkich** umów, także kontrolnych |
| Segment docelowy | uplift ≥ kwantyl 0,80 upliftu w miesiącu końca umowy, liczony na wszystkich umowach z upliftem, w obu grupach. Umowy poza zakresem danych uczących v3 (`ModelUpliftT.poza_zakresem`) nie mają upliftu i nie należą do segmentu, ale są losowane i liczą się w metryce portfelowej |
| Oferta | umowy segmentu spoza kontroli: rabat 150 zł / mies. w nowej umowie, wysłany `data_do` − 45 dni. **Wyjątek:** umowy z `data_do` − 45 dni < dzień startu (grudzień) dostają ofertę w dniu startu kampanii, proponowany 2026-11-23 (pytanie 1) |
| Pozostałe umowy | bez oferty w obu grupach |

Kontrola segmentu to umowy kontrolne powyżej tego samego progu upliftu. Dzięki temu porównujemy tych samych
najemców z ofertą i bez niej.

### Metryki

| Rola | Metryka | Definicja |
|---|---|---|
| **Główna** | uplift w segmencie docelowym | % przedłużeń (oferta, segment) − % przedłużeń (kontrola, segment); przedłużenie = 1 − `odejdzie` jak w `migawki_najemcy` (kolejny okres albo przeprowadzka do 30 dni po `data_do`). Liczymy efekt wysłania oferty (ITT), nie przyjęcia |
| Drugorzędna | zysk w PLN na koniec umowy w całym portfelu | średnia Y w ramieniu polityki (80%) − średnia Y w kontroli (20%), gdzie Y = R × przedłużenie − D × (przedłużenie z ofertą) − k × (oferta) |
| Decyzyjna (kontrola opłacalności) | zysk na ofertę w segmencie | uplift × R − D × % przedłużeń z ofertą − k, policzony na segmencie (to ta sama wielkość co metryka drugorzędna podzielona przez udział ofert, ale bez szumu z umów bez oferty) |
| Kontrolne | balans i SRM | udział kontroli wobec 20% (test dwumianowy), średni uplift i `score_polityki`, udział B2B, wypowiedzenie przed migawką: oferta vs kontrola w segmencie |

Założenia R = 4 920 zł, D = 1 800 zł, k = 60 zł pochodzą z `retention_bc/zalozenia.yaml` (stan 2026-11-16, podane
przez użytkownika). Do końca eksperymentu ich nie zmieniamy.

### Analiza

- **Test główny:** różnica dwóch proporcji, przedział Walda (wariancje osobno w grupach), dwustronnie, α = 5%.
  Na każdej z niżej podanych dat robimy jeden test, bez podglądania wyników pomiędzy datami.
- **Sprawdzenia** (nie zmieniają wniosku głównego): bootstrap po najemcach (1 000 losowań, ziarno 42); efekt ważony
  miesiącem końca umowy; wynik bez umów grudniowych (spóźniona oferta); B2C i B2B osobno, jako analiza opisowa.
- **Przedziały dla PLN:** bootstrap percentylowy, losowanie umów osobno w grupach (1 000 losowań, ziarno 42), jak
  w [kampania_2026q3.md](kampania_2026q3.md).

### Próg decyzji i daty analizy

| Data | Dane | Co sprawdzamy | Decyzja |
|---|---|---|---|
| **2027-04-15** (kontrola opłacalności) | kampania Q4: końce umów 2026-12-01 – 2027-02-28. Wynik ostatniej umowy znany 2027-03-30 (`data_do` + 30 dni), eksport z 2027-03-31 | tylko zysk na ofertę w segmencie, 95% przedział | **górna granica < 0 zł:** rabat 1 800 zł nie wraca w kolejnych kampaniach, a kampanię kończymy na Q4. W pozostałych przypadkach kampanie Q1 i Q2 2027 idą według tego samego planu. Testu głównego w tym dniu nie wykonujemy |
| **2027-10-15** (analiza główna) | 3 kwartały: końce umów 2026-12-01 – 2027-08-31 (eksport z 2027-09-30); po zatrzymaniu 2027-04-15 tylko Q4 | test główny: uplift w segmencie, p < 0,05 | **uplift > 0 i p < 0,05:** oferta zwiększa przedłużenia w segmencie v3. **Rabat utrzymujemy** tylko wtedy, gdy dolna granica 95% przedziału zysku na ofertę > 0 (na danych z testu 2025 wymagałoby to upliftu około 39,1 p.p.). Gdy górna granica < 0, rabat kończymy. W pozostałych przypadkach nie rozszerzamy rabatu, a decyzję podejmuje właściciel założeń. Jeśli kampanię zatrzymano 2027-04-15, wynik tylko z Q4 raportujemy jako niedostatecznie zbadany (moc 41%), a nie jako „brak efektu” |
| **2028-10-15** (metryka drugorzędna) | 7 kwartałów: końce umów do 2028-08-31, tylko jeśli kampanie trwają w tym samym projekcie | zysk w PLN na koniec umowy w portfelu, 95% przedział | test dwustronny α = 5%. Wcześniej metrykę drugorzędną pokazujemy tylko opisowo, bez wniosku |

### Co zamrażamy na czas eksperymentu

Wersję modelu (md5 powyżej), próg 20% upliftu, 20% kontroli i ziarno losowania (`:kampania_2026q4`; w kolejnych
kwartałach odpowiednio `:kampania_2027q1` i `:kampania_2027q2`), wysokość rabatu, termin oferty (45 dni), definicję
przedłużenia oraz R, D i k. Gdy którykolwiek z tych elementów się zmieni, kwartały przed zmianą i po niej
analizujemy osobno.

### Odstępstwa

(brak, 2026-11-16)

## Wyniki: moc i MDE

### Dane wejściowe (z danych, przed kampanią)

| Wielkość | Wartość | Źródło |
|---|---:|---|
| Umowy w populacji Q4 (`data_do` 2026-12 / 2027-01 / 2027-02) | 1 543 (538 / 551 / 454), w tym B2B 249; 1 504 najemców | `pms_umowy` + `pms_najmy`, SQL 1 |
| Umowy na kwartał w przeszłości (koniec umowy 2025Q1 … 2026Q3) | 1 320, 1 272, 1 605, 1 657, 1 472, 1 270, 1 586 | `retencja_decyzje`, SQL 2 |
| Na kwartał: oferty / kontrola w segmencie | 247 / 62 | 0,8 × 0,2 × 1 543 i 0,2 × 0,2 × 1 543 |
| Na kwartał: ramię polityki / kontrola | 1 234 / 309 | 0,8 × 1 543 i 0,2 × 1 543 |
| % przedłużeń w segmencie (górne 20% upliftu v3): kontrola / oferta | 64,5% (89 / 138) / 75,9% (110 / 145) | test 2025, część testowa 30% (`ev_najemcow.parquet`), SQL 3 |
| Uplift w segmencie (efekt planistyczny) | +11,4 p.p. (95%: +1,4 … +23,3, [porownanie.md](../evals/porownanie.md)) | jak wyżej |
| % przedłużeń bez oferty: poza segmentem / cała kontrola | 57,3% (324 / 565) / 58,7% (413 / 703) | jak wyżej |
| Odchylenie standardowe Y: ramię polityki / kontrola | 2 266 zł / 2 422 zł | rozkład mieszany, kod niżej |
| Oczekiwany zysk na ofertę / na umowę w portfelu | −866 zł / −173 zł | 0,114 × R − D × 0,759 − k; × 0,2 |
| Uplift potrzebny do zysku na ofertę = 0 | 39,1 p.p. | (D × 0,645 + k) / (R − D) |
| Oczekiwany wynik jednego kwartału kampanii | −213 834 zł | 246,9 oferty × −866 zł |

Moce liczymy dla populacji z Q4 (1 543 umowy), a kolejne kwartały przyjmujemy za równie liczne. W latach
2025–2026 kwartały liczyły od 1 270 do 1 657 umów.

### MDE (moc 80%, α = 5% dwustronnie) w zależności od liczby kwartałów

| Kwartały kampanii | Umowy | MDE: uplift w segmencie | MDE: zysk na koniec umowy w portfelu | MDE: zysk na ofertę w segmencie |
|---:|---:|---:|---:|---:|
| 1 | 1 543 | 18,3 p.p. | 426 zł | 873 zł |
| 2 | 3 086 | 13,2 p.p. | 302 zł | 617 zł |
| 3 | 4 629 | 10,8 p.p. | 246 zł | 504 zł |
| 4 | 6 172 | 9,4 p.p. | 213 zł | 436 zł |
| 5 | 7 715 | 8,4 p.p. | 191 zł | 390 zł |
| 6 | 9 258 | 7,7 p.p. | 174 zł | 356 zł |
| 7 | 10 801 | 7,1 p.p. | 161 zł | 330 zł |
| 8 | 12 344 | 6,7 p.p. | 151 zł | 309 zł |
| 12 | 18 516 | 5,5 p.p. | 123 zł | 252 zł |

### Ile kwartałów, żeby wykryć efekt

| Metryka | Efekt planistyczny | Kwartały do MDE ≤ efekt | Moc po 1 / 3 / 7 kwartałach |
|---|---:|---:|---:|
| **Uplift w segmencie** (główna) | +11,4 p.p. | **3** | 41% / 84% / 99% |
| **Zysk na koniec umowy w portfelu** (drugorzędna) | −173 zł | **7** | 21% / 50% / 85% |
| Zysk na ofertę w segmencie (kontrola opłacalności) | −866 zł | 2 (po 1 kwartale moc 79%) | 79% / — / — |

Wrażliwość na wielkość efektu, czyli ile kwartałów potrzeba, gdy prawdziwy efekt jest inny niż w teście 2025:

| Uplift w segmencie | 5 p.p. | 8 p.p. | 11,4 p.p. | 15 p.p. | 20 p.p. |
|---|---:|---:|---:|---:|---:|
| Kwartały | 15 | 6 | 3 | 2 | 1 |

| Zysk na koniec umowy w portfelu | −100 zł | −173 zł | −300 zł |
|---|---:|---:|---:|
| Kwartały | 19 | 7 | 3 |

Przedział efektu z testu 2025 jest szeroki (od +1,4 do +23,3 p.p.). Jeśli prawdziwy efekt leży bliżej dolnej
granicy, 3 kwartały nie wystarczą. Plan tego nie zmienia: analizę główną robimy 2027-10-15 niezależnie od wyniku.

## SQL i kod

Liczby z sekcji „Wyniki” pochodzą z poniższego kodu: tylko odczyt plików Parquet z `data/` oraz wyników
`retention_bc/wyniki/ev_najemcow.parquet` (z `polityka_rabatow.py`). Kod nie łączy się z `domilo.duckdb`
i niczego nie zapisuje. Kod nie jest osobnym plikiem w repozytorium: żeby powtórzyć obliczenia, zapisz blok poniżej
jako `moc_q4.py` poza `data/` i uruchom z katalogu głównego repozytorium (`poetry run python <ścieżka>/moc_q4.py`).

SQL 1: populacja Q4 według miesięcy (oraz ile umów miało termin oferty przed 2026-11-16):

```sql
SELECT date_trunc('month', u.data_do)::DATE AS miesiac_konca, count(*) AS umowy,
       count(*) FILTER (WHERE n.linia = 'B2B') AS b2b,
       count(*) FILTER (WHERE u.data_do::DATE - 45 < DATE '2026-11-16') AS oferta_45d_juz_minela,
       min(u.data_do::DATE - 60) AS migawka_od, max(u.data_do::DATE - 60) AS migawka_do
FROM 'data/pms/pms_umowy.parquet' AS u JOIN 'data/pms/pms_najmy.parquet' AS n USING (id_najmu)
WHERE u.typ IN ('pierwsza', 'przedłużenie')
  AND u.data_do::DATE BETWEEN DATE '2026-12-01' AND DATE '2027-02-28'
  AND (n.data_wyprowadzenia IS NULL OR n.data_wyprowadzenia::DATE >= u.data_do::DATE)
GROUP BY ROLLUP (1) ORDER BY 1;
-- 2026-12: 538 (B2B 101, termin minął 529); 2027-01: 551 (78, 0); 2027-02: 454 (70, 0); razem 1 543 (249, 529)
```

Kod (`moc_q4.py`; SQL 2 i SQL 3 są w środku):

```python
"""MDE kampanii Q4 2026 (tylko odczyt: pliki Parquet z data/ i wyniki retention_bc). Uruchamiać z katalogu głównego."""
import duckdb
import numpy as np
import yaml
from scipy import stats

ALFA, MOC = 0.05, 0.80
Z = stats.norm.ppf(1 - ALFA / 2) + stats.norm.ppf(MOC)  # 1,960 + 0,842
U_KONTROLA, U_SEGMENT = 0.20, 0.20  # projekt: 20% kontroli z całej populacji, oferta dla górnych 20% upliftu
z = {k: v["wartosc"] for k, v in yaml.safe_load(open("api/api/contexts_boundaries/retention_bc/zalozenia.yaml")).items()}
R, D, k = z["koszt_odejscia_R"], z["rabat_roczny_D"], z["koszt_kontaktu_k"]
con = duckdb.connect()
q = lambda s: con.execute(s).fetchall()

# 1. Populacja Q4: umowy roczne B2C/B2B kończące się 2026-12-01 – 2027-02-28 (definicja jak w migawki.sql)
SQL_Q4 = """
SELECT count(*) AS umowy, count(*) FILTER (WHERE n.linia = 'B2B') AS b2b,
       count(DISTINCT n.id_najemcy) AS najemcy
FROM 'data/pms/pms_umowy.parquet' AS u JOIN 'data/pms/pms_najmy.parquet' AS n USING (id_najmu)
WHERE u.typ IN ('pierwsza', 'przedłużenie')
  AND u.data_do::DATE BETWEEN DATE '2026-12-01' AND DATE '2027-02-28'
  AND (n.data_wyprowadzenia IS NULL OR n.data_wyprowadzenia::DATE >= u.data_do::DATE)
"""
N, b2b, najemcy = q(SQL_Q4)[0]
# SQL 2, dla porównania: kwartały historyczne (retencja_decyzje = ta sama populacja od 2024-02)
SQL_KW = """
SELECT year(data_konca) || 'Q' || quarter(data_konca) AS kw, count(*) AS umowy
FROM 'data/portal/retencja_decyzje.parquet' WHERE data_konca >= '2025-01-01' GROUP BY 1 ORDER BY 1
"""
kwartaly = q(SQL_KW)

# SQL 3: wejścia planistyczne z losowego testu 2025 (część testowa 30%, ten sam podział co uplift.md;
#    segment = polityka_gorne_20_upliftu: górne 20% upliftu v3 w zbiorze oceny)
SQL_TEST = """
SELECT polityka_gorne_20_upliftu AS segment, grupa, count(*) AS n, sum(1 - odejdzie) AS przedl
FROM 'api/api/contexts_boundaries/retention_bc/wyniki/ev_najemcow.parquet' GROUP BY ALL ORDER BY ALL
"""
t = {(s, g): (n, p) for s, g, n, p in q(SQL_TEST)}
n_sk, prz_sk = t[(True, "kontrola")]; n_so, prz_so = t[(True, "oferta")]
n_rk, prz_rk = t[(False, "kontrola")]
p_sk, p_so, p_rk = prz_sk / n_sk, prz_so / n_so, prz_rk / n_rk  # segment: kontrola / oferta; reszta: kontrola
p_c = (prz_sk + prz_rk) / (n_sk + n_rk)  # cała populacja bez oferty
uplift = p_so - p_sk

# 3. Metryka 1: uplift w segmencie docelowym (oferta: 0,8·0,2·N, kontrola w segmencie: 0,2·0,2·N)
def mde_proporcji(p0, n_t, n_c):
    """Najmniejsze d > 0, które test z (dwustronny, α) wykrywa z mocą MOC: d = Z·√(p1q1/n_t + p0q0/n_c), p1 = p0+d."""
    d = 0.1
    for _ in range(100):
        p1 = min(p0 + d, 0.999)
        d = Z * np.sqrt(p1 * (1 - p1) / n_t + p0 * (1 - p0) / n_c)
    return d

def metryka1(kw):
    n = kw * N
    return mde_proporcji(p_sk, (1 - U_KONTROLA) * U_SEGMENT * n, U_KONTROLA * U_SEGMENT * n)

# 4. Metryka 2: zysk w PLN na koniec umowy w całym portfelu: ramię polityki (80%) − kontrola (20%)
#    Y = R·przedłużenie − D·przedłużenie·oferta − k·oferta; w kontroli Y = R·przedłużenie
e_s = (R - D) * p_so - k; v_s = (R - D) ** 2 * p_so * (1 - p_so)  # segment z ofertą
e_r = R * p_rk; v_r = R**2 * p_rk * (1 - p_rk)  # reszta ramienia polityki (bez oferty)
var_t = U_SEGMENT * v_s + (1 - U_SEGMENT) * v_r + U_SEGMENT * (1 - U_SEGMENT) * (e_s - e_r) ** 2
var_c = R**2 * p_c * (1 - p_c)
efekt_pln = U_SEGMENT * (uplift * R - D * p_so - k)  # oczekiwany zysk na umowę = 0,2 × zysk na ofertę

def metryka2(kw):
    n = kw * N
    return Z * np.sqrt(var_t / ((1 - U_KONTROLA) * n) + var_c / (U_KONTROLA * n))

def kwartaly_do_wykrycia(mde_fn, efekt):
    return next(kw for kw in range(1, 1000) if mde_fn(kw) <= abs(efekt))

# próg opłacalności: uplift, przy którym zysk na ofertę = 0: u·R = D·(p_sk + u) + k
u_zero = (D * p_sk + k) / (R - D)

print(f"N_Q4={N} B2B={b2b} najemcy={najemcy} kwartaly={kwartaly}")
print(f"Z={Z:.4f} R={R} D={D} k={k}")
print(f"test: seg kontrola {prz_sk}/{n_sk}={p_sk:.4f} seg oferta {prz_so}/{n_so}={p_so:.4f} uplift={uplift:.4f}")
print(f"test: reszta kontrola {prz_rk}/{n_rk}={p_rk:.4f}; cala kontrola p_c={p_c:.4f}")
print(f"n na kwartal: oferta={0.16*N:.0f} kontrola_seg={0.04*N:.0f} ramie_polityki={0.8*N:.0f} kontrola={0.2*N:.0f}")
print(f"sd_t={np.sqrt(var_t):.1f} sd_c={np.sqrt(var_c):.1f} efekt_pln_na_umowe={efekt_pln:.2f} zysk_na_oferte={efekt_pln/U_SEGMENT:.2f}")
print(f"u_zero={u_zero:.4f}")
for kw in (1, 2, 3, 4, 6, 8, 12, 16, 20, 30, 40):
    print(kw, f"MDE1={metryka1(kw)*100:.2f}pp", f"MDE2={metryka2(kw):.1f}PLN/umowe", f"MDE2_kw={metryka2(kw)*N*kw:.0f}")
print("Q1 (uplift test)", kwartaly_do_wykrycia(metryka1, uplift))
print("Q1 (u_zero)", kwartaly_do_wykrycia(metryka1, u_zero))
print("Q2 (efekt PLN)", kwartaly_do_wykrycia(metryka2, efekt_pln))

# 5. Dodatkowo: kwartały przy innych efektach, moc po 1 kwartale, koszt eksperymentu, zysk na ofertę w segmencie
for u in (0.05, 0.08, uplift, 0.15, 0.20):
    print(f"metryka1 efekt {u*100:.1f}pp -> kwartaly {kwartaly_do_wykrycia(metryka1, u)}")
for e in (-100.0, efekt_pln, -300.0):
    print(f"metryka2 efekt {e:.1f} PLN/umowe -> kwartaly {kwartaly_do_wykrycia(metryka2, e)}")
def moc(efekt, mde_fn, kw):
    return float(stats.norm.cdf(abs(efekt) / (mde_fn(kw) / Z) - stats.norm.ppf(1 - ALFA / 2)))
for kw in (1, 3, 7):
    print(f"moc po {kw} kw.: metryka1 {moc(uplift, metryka1, kw):.3f}, metryka2 {moc(efekt_pln, metryka2, kw):.3f}")
oferty_kw = (1 - U_KONTROLA) * U_SEGMENT * N
zysk_na_oferte = uplift * R - D * p_so - k
print(f"oferty na kwartal {oferty_kw:.1f}; oczekiwany wynik kampanii na kwartal {oferty_kw*zysk_na_oferte:.0f} PLN")
# zysk na ofertę w segmencie (ta sama wielkość co metryka 2 / 0,2, ale bez szumu z 80% umów bez oferty)
var_so = (R - D) ** 2 * p_so * (1 - p_so); var_sk = R**2 * p_sk * (1 - p_sk)
def metryka2_seg(kw):
    n = kw * N
    return Z * np.sqrt(var_so / ((1 - U_KONTROLA) * U_SEGMENT * n) + var_sk / (U_KONTROLA * U_SEGMENT * n))
print(f"zysk na oferte {zysk_na_oferte:.2f}; MDE 1 kw. {metryka2_seg(1):.1f}; "
      f"kwartaly {kwartaly_do_wykrycia(metryka2_seg, zysk_na_oferte)}; moc 1 kw. {moc(zysk_na_oferte, metryka2_seg, 1):.3f}")
# tabela MDE w raporcie: kw = 1, 2, 3, 4, 5, 6, 7, 8, 12 -> metryka1(kw), metryka2(kw), metryka2_seg(kw)
```

Wzory:

- MDE dla proporcji: najmniejsze d, przy którym d = (z₀,₉₇₅ + z₀,₈₀) · √(p₁(1−p₁)/n_oferta + p₀(1−p₀)/n_kontrola),
  gdzie p₀ = 64,5%, p₁ = p₀ + d (rozwiązanie iteracyjne); z₀,₉₇₅ + z₀,₈₀ = 2,8016.
- MDE dla PLN: 2,8016 · √(σ²_polityka / n_polityka + σ²_kontrola / n_kontrola), gdzie σ²_polityka to wariancja
  mieszaniny (20% segment z ofertą: Y = (R − D) · przedłużenie − k; 80% bez oferty: Y = R · przedłużenie),
  a σ²_kontrola = R² · p(1 − p).
- Kwartały: najmniejsze K, przy którym MDE(K · 1 543 umów) ≤ |efekt planistyczny|.
- Moc: Φ(|efekt| / SE − 1,96), SE = MDE / 2,8016.
