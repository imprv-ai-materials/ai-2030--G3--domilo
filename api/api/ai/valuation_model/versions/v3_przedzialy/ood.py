"""Detektor danych spoza zakresu (OOD) dla wyceny: czy lokal przypomina transakcje, na których uczył się model.

Trzy rodziny sygnałów, każdy z progiem ustalonym na zbiorze treningowym (`fit`):

1. Reguły:
   - miasto albo para (miasto, dzielnica) z mniej niż `min_transakcji` (80) transakcjami w treningu;
   - metraż albo rok budowy poza zakresem p0,5–p99,5 treningu (albo brak wartości);
   - nietypowy typ lokalu. RCN nie ma kolumny „typ lokalu”, a lokale Domilo nie mają `typ_budynku`, więc typ lokalu
     to liczba pokoi i metraż przy tej liczbie pokoi: liczba pokoi z < 80 transakcjami w treningu albo metraż poza
     p0,5–p99,5 lokali z tą samą liczbą pokoi (np. 1 pokój i 60 m²).
2. Odległość do `k` (10) najbliższych transakcji treningowych w przestrzeni cech liczbowych modelu, standaryzowanych
   średnią i odchyleniem z treningu (średnia odległość euklidesowa); w powodzie dwie cechy lokalu najdalej od
   średniej treningu. Próg domyślny: kwantyl `kwantyl_progu` (0,99)
   tej samej odległości liczonej dla transakcji treningowych (bez nich samych jako sąsiada).
3. Isolation Forest na tych samych standaryzowanych cechach; wynik = −score_samples (większy = bardziej nietypowy),
   próg domyślny jak wyżej: kwantyl 0,99 wyników treningu.

Braki w cechach przestrzeni uzupełniamy przed standaryzacją: `odl_metro_m` (metro tylko w Warszawie) maksimum treningu
(„daleko od metra”), `sasiedzi_mediana_ceny_m2` (brak sąsiadów) zerem, co celowo oddala punkt od treningu, pozostałe
medianą treningu.
`ocen` zwraca decyzję (`odmowa`), kody powodów (`kody`) i powody słowami (`powody`, rozdzielone „; ”).
"""

import math

import numpy as np
import pandas as pd
from api.ai.valuation_model.versions.v2_lgbm_geo.model import CECHY_DOMYSLNE
from api.ai.valuation_model.versions.v2_lightgbm.model import KOLUMNY_LICZBOWE
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors

KOLUMNY_PRZESTRZENI = tuple(KOLUMNY_LICZBOWE) + tuple(CECHY_DOMYSLNE)
KOLUMNY_REGUL = ("miasto", "dzielnica", "metraz", "pokoje", "rok_budowy")

KOD_MIASTO = "miasto"
KOD_DZIELNICA = "dzielnica"
KOD_METRAZ = "metraz"
KOD_ROK = "rok_budowy"
KOD_TYP = "typ_lokalu"
KOD_KNN = "knn"
KOD_IF = "isolation_forest"
KODY = (KOD_MIASTO, KOD_DZIELNICA, KOD_METRAZ, KOD_ROK, KOD_TYP, KOD_KNN, KOD_IF)

UZUPELNIJ_MAKSIMUM = ("odl_metro_m",)
UZUPELNIJ_ZEREM = ("sasiedzi_mediana_ceny_m2",)

OPISY_CECH = {
    "metraz": "metraż",
    "pokoje": "liczba pokoi",
    "pietro": "piętro",
    "rok_budowy": "rok budowy",
    "odl_stacja_m": "odległość do stacji",
    "odl_metro_m": "odległość do metra",
    "odl_tramwaj_m": "odległość do tramwaju",
    "odl_park_m": "odległość do parku",
    "odl_uczelnia_m": "odległość do uczelni",
    "metro_do_700m": "metro do 700 m",
    "tramwaj_do_300m": "tramwaj do 300 m",
    "park_do_400m": "park do 400 m",
    "odl_centrum_m": "odległość do centrum",
    "gestosc_os_km2": "gęstość zaludnienia dzielnicy",
    "wskaznik_dochodu": "wskaźnik dochodu dzielnicy",
    "sasiedzi_mediana_ceny_m2": "mediana ceny m² sąsiednich transakcji",
    "sasiedzi_liczba": "liczba sąsiednich transakcji",
}


def _l(x: float, miejsca: int = 1) -> str:
    """Liczba po polsku: spacja tysięcy, przecinek dziesiętny."""
    return f"{x:,.{miejsca}f}".replace(",", " ").replace(".", ",")


def _pokoje_slowo(p: int) -> str:
    return f"{p}-pokojow"


class DetektorOOD:
    def __init__(
        self,
        *,
        kolumny: tuple[str, ...] = KOLUMNY_PRZESTRZENI,
        min_transakcji: int = 80,
        kwantyle: tuple[float, float] = (0.005, 0.995),
        k: int = 10,
        kwantyl_progu: float = 0.99,
        n_drzew: int = 200,
        random_state: int = 42,
    ):
        self.kolumny = tuple(kolumny)
        self.min_transakcji = min_transakcji
        self.kwantyle = kwantyle
        self.k = k
        self.kwantyl_progu = kwantyl_progu
        self.n_drzew = n_drzew
        self.random_state = random_state

    # --- uczenie ---------------------------------------------------------------------------------------------

    def _sprawdz(self, X: pd.DataFrame) -> None:
        brak = [c for c in KOLUMNY_REGUL + self.kolumny if c not in X.columns]
        if brak:
            raise ValueError(f"Brak kolumn wymaganych przez detektor OOD: {', '.join(brak)}")

    def fit(self, X: pd.DataFrame) -> "DetektorOOD":
        self._sprawdz(X)
        self.n_treningu_ = int(len(X))
        self.liczba_miasto_ = X["miasto"].value_counts().to_dict()
        self.liczba_dzielnica_ = (X["miasto"].astype(str) + " | " + X["dzielnica"].astype(str)).value_counts().to_dict()
        self.liczba_pokoje_ = X["pokoje"].value_counts().to_dict()
        lo, hi = self.kwantyle
        self.zakresy_ = {
            k: tuple(float(v) for v in np.nanquantile(X[k].astype(float), [lo, hi])) for k in ("metraz", "rok_budowy")
        }
        self.zakresy_metrazu_pokoje_ = {
            int(p): tuple(float(v) for v in np.quantile(g["metraz"].astype(float), [lo, hi]))
            for p, g in X.groupby("pokoje")
        }

        A = X[list(self.kolumny)].astype(float)
        self.uzupelnienia_ = {}
        for c in self.kolumny:
            if c in UZUPELNIJ_MAKSIMUM:
                self.uzupelnienia_[c] = float(A[c].max())
            elif c in UZUPELNIJ_ZEREM:
                self.uzupelnienia_[c] = 0.0
            else:
                self.uzupelnienia_[c] = float(A[c].median())
        A = A.fillna(self.uzupelnienia_)
        self.srednie_ = A.mean().to_numpy()
        odch = A.std(ddof=0).to_numpy()
        self.odchylenia_ = np.where(odch > 0, odch, 1.0)
        Z = self._standaryzuj(X)
        self.knn_ = NearestNeighbors(n_neighbors=self.k + 1).fit(Z)
        self.if_ = IsolationForest(n_estimators=self.n_drzew, random_state=self.random_state).fit(Z)
        w = self.wyniki(X, bez_siebie=True)
        self.prog_knn_ = float(np.quantile(w["odl_knn"], self.kwantyl_progu))
        self.prog_if_ = float(np.quantile(w["wynik_if"], self.kwantyl_progu))
        return self

    def _standaryzuj(self, X: pd.DataFrame) -> np.ndarray:
        A = X[list(self.kolumny)].astype(float).fillna(self.uzupelnienia_).to_numpy()
        return (A - self.srednie_) / self.odchylenia_

    # --- wyniki ciągłe ---------------------------------------------------------------------------------------

    def _knn(self, Z: np.ndarray, bez_siebie: bool) -> tuple[np.ndarray, np.ndarray]:
        odl, idx = self.knn_.kneighbors(Z, n_neighbors=self.k + 1)
        if bez_siebie:
            return odl[:, 1:], idx[:, 1:]
        return odl[:, : self.k], idx[:, : self.k]

    def wyniki(self, X: pd.DataFrame, bez_siebie: bool = False) -> pd.DataFrame:
        """odl_knn (średnia odległość do k najbliższych z treningu) i wynik_if; bez_siebie=True dla punktów treningu."""
        Z = self._standaryzuj(X)
        odl, _ = self._knn(Z, bez_siebie)
        return pd.DataFrame({"odl_knn": odl.mean(axis=1), "wynik_if": -self.if_.score_samples(Z)}, index=X.index)

    # --- decyzja z powodami ----------------------------------------------------------------------------------

    def _odstajace_cechy(self, z: np.ndarray, ile: int = 2) -> str:
        """Cechy najdalej od średniej treningu (z-score lokalu). Nie porównujemy z sąsiadami: dla lokalu bez
        sąsiedztwa RCN najbliższe są inne nietypowe transakcje treningu, więc różnica z nimi ukrywa przyczynę."""
        kolejnosc = np.argsort(-np.abs(z))[:ile]
        return ", ".join(
            f"{OPISY_CECH.get(self.kolumny[i], self.kolumny[i])} ({_l(z[i], 1)} odch. std. od średniej treningu)"
            for i in kolejnosc
        )

    def ocen(self, X: pd.DataFrame, prog_knn: float | None = None, prog_if: float | None = None) -> pd.DataFrame:
        """Jeden wiersz na lokal: odmowa, kody, powody, odl_knn, wynik_if oraz flaga 0/1 dla każdego kodu."""
        self._sprawdz(X)
        prog_knn = self.prog_knn_ if prog_knn is None else prog_knn
        prog_if = self.prog_if_ if prog_if is None else prog_if
        Z = self._standaryzuj(X)
        odl, _ = self._knn(Z, bez_siebie=False)
        odl_knn = odl.mean(axis=1)
        wynik_if = -self.if_.score_samples(Z)
        lo_q, hi_q = (_l(100 * q, 1).rstrip("0").rstrip(",") for q in self.kwantyle)
        zakres_opis = f"p{lo_q}–p{hi_q}"

        kody_wszystkie, powody_wszystkie = [], []
        for i, w in enumerate(X[list(KOLUMNY_REGUL)].itertuples(index=False)):
            kody, powody = [], []
            n_m = int(self.liczba_miasto_.get(w.miasto, 0))
            if n_m < self.min_transakcji:
                kody.append(KOD_MIASTO)
                powody.append(
                    f"Miasto {w.miasto}: {n_m} transakcji w zbiorze treningowym "
                    f"(wymagane co najmniej {self.min_transakcji})"
                )
            n_d = int(self.liczba_dzielnica_.get(f"{w.miasto} | {w.dzielnica}", 0))
            if n_d < self.min_transakcji:
                kody.append(KOD_DZIELNICA)
                powody.append(
                    f"Dzielnica {w.dzielnica} ({w.miasto}): {n_d} transakcji w zbiorze treningowym "
                    f"(wymagane co najmniej {self.min_transakcji})"
                )
            lo, hi = self.zakresy_["metraz"]
            if w.metraz is None or (isinstance(w.metraz, float) and math.isnan(w.metraz)):
                kody.append(KOD_METRAZ)
                powody.append("Brak metrażu")
            elif not lo <= w.metraz <= hi:
                kody.append(KOD_METRAZ)
                powody.append(f"Metraż {_l(w.metraz)} m² poza zakresem treningu {_l(lo)}–{_l(hi)} m² ({zakres_opis})")
            lo, hi = self.zakresy_["rok_budowy"]
            if pd.isna(w.rok_budowy):
                kody.append(KOD_ROK)
                powody.append("Brak roku budowy")
            elif not lo <= w.rok_budowy <= hi:
                kody.append(KOD_ROK)
                powody.append(
                    f"Rok budowy {int(w.rok_budowy)} poza zakresem treningu {lo:.0f}–{hi:.0f} ({zakres_opis})"
                )
            if pd.isna(w.pokoje):
                kody.append(KOD_TYP)
                powody.append("Nietypowy typ lokalu: brak liczby pokoi")
            else:
                p = int(w.pokoje)
                n_p = int(self.liczba_pokoje_.get(p, 0))
                if n_p < self.min_transakcji:
                    kody.append(KOD_TYP)
                    powody.append(
                        f"Nietypowy typ lokalu: {p} pokoi, w zbiorze treningowym {n_p} takich transakcji "
                        f"(wymagane co najmniej {self.min_transakcji})"
                    )
                elif not pd.isna(w.metraz):
                    lo, hi = self.zakresy_metrazu_pokoje_[p]
                    if not lo <= w.metraz <= hi:
                        kody.append(KOD_TYP)
                        powody.append(
                            f"Nietypowy typ lokalu: {_pokoje_slowo(p)}y o metrażu {_l(w.metraz)} m², w treningu "
                            f"{_pokoje_slowo(p)}e mają {_l(lo)}–{_l(hi)} m² ({zakres_opis})"
                        )
            if odl_knn[i] > prog_knn:
                kody.append(KOD_KNN)
                powody.append(
                    f"Lokal daleko od transakcji treningowych: średnia odległość do {self.k} najbliższych "
                    f"{_l(odl_knn[i], 2)} (próg {_l(prog_knn, 2)}), najbardziej odstają: " + self._odstajace_cechy(Z[i])
                )
            if wynik_if[i] > prog_if:
                kody.append(KOD_IF)
                powody.append(
                    f"Nietypowa kombinacja cech (Isolation Forest): wynik {_l(wynik_if[i], 3)} (próg {_l(prog_if, 3)})"
                )
            kody_wszystkie.append(kody)
            powody_wszystkie.append("; ".join(powody))

        wyj = pd.DataFrame(
            {
                "odmowa": [bool(k) for k in kody_wszystkie],
                "kody": kody_wszystkie,
                "powody": powody_wszystkie,
                "odl_knn": odl_knn,
                "wynik_if": wynik_if,
            },
            index=X.index,
        )
        for kod in KODY:
            wyj[f"powod_{kod}"] = [kod in k for k in kody_wszystkie]
        return wyj
