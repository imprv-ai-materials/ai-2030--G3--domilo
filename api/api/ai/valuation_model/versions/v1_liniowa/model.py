"""v1: regresja liniowa (scikit-learn, MNK) na ln(ceny transakcyjnej).

Cechy:
- metraż: ln(metraż) (`metraz_log=True`, wybrane na zbiorze walidacyjnym) albo metraż w m²;
- pokoje, piętro: liczbowo;
- przedział roku budowy (`przedzial_roku_budowy`): zmienne 0/1, poziom odniesienia „1970–1989”;
- dzielnica: zmienne 0/1 dla par (miasto, dzielnica), po jednej na dzielnicę, bez wyrazu wolnego (każda dzielnica ma
  własny poziom ceny). Dzielnice z < `min_transakcji_dzielnicy` (30) transakcjami w zbiorze treningowym łączymy
  w jedną kategorię „reszta miasta” w obrębie swojego miasta.

Dzielnica nieznana w treningu: „reszta miasta”, jeśli miasto ją ma; w przeciwnym razie średni poziom dzielnic miasta
ważony liczbą transakcji treningowych („średnia miasta”). Miasto nieznane w treningu: błąd.
Wycena = exp(przewidywany ln(ceny)), czyli mediana, nie średnia, ceny przy danych cechach (bez korekty na rozrzut).
"""

import numpy as np
import pandas as pd
from api.ai.valuation_model.base import ModelWyceny
from sklearn.linear_model import LinearRegression

RESZTA_MIASTA = "reszta miasta"
SREDNIA_MIASTA = "średnia miasta"
PRZEDZIALY_ROKU = (  # (etykieta, rok od, rok do włącznie)
    ("do 1944", None, 1944),
    ("1945–1969", 1945, 1969),
    ("1970–1989", 1970, 1989),
    ("1990–2009", 1990, 2009),
    ("2010–2019", 2010, 2019),
    ("od 2020", 2020, None),
)
PRZEDZIAL_ODNIESIENIA = "1970–1989"


def przedzial_roku_budowy(rok: pd.Series) -> pd.Series:
    wynik = pd.Series(pd.NA, index=rok.index, dtype="object")
    for etykieta, od, do in PRZEDZIALY_ROKU:
        maska = pd.Series(True, index=rok.index)
        if od is not None:
            maska &= rok >= od
        if do is not None:
            maska &= rok <= do
        wynik[maska] = etykieta
    return wynik


def _klucz(miasto, dzielnica) -> str:
    return f"{miasto} | {dzielnica}"


class ModelLiniowy(ModelWyceny):
    wersja = "v1_liniowa"

    def __init__(self, *, min_transakcji_dzielnicy: int = 30, metraz_log: bool = True):
        self.min_transakcji_dzielnicy = min_transakcji_dzielnicy
        self.metraz_log = metraz_log

    # --- cechy ---------------------------------------------------------------------------------------------------

    def _dzielnica_w_modelu(self, X: pd.DataFrame) -> pd.Series:
        wynik = []
        for miasto, dzielnica in zip(X["miasto"], X["dzielnica"]):
            if miasto not in self.miasta_:
                raise ValueError(f"Miasto nieznane w zbiorze treningowym: {miasto}")
            klucz = _klucz(miasto, dzielnica)
            if klucz in self.kategorie_dzielnic_:
                wynik.append(klucz)
            elif _klucz(miasto, RESZTA_MIASTA) in self.kategorie_dzielnic_:
                wynik.append(_klucz(miasto, RESZTA_MIASTA))
            else:
                wynik.append(_klucz(miasto, SREDNIA_MIASTA))
        return pd.Series(wynik, index=X.index)

    def _macierz(self, X: pd.DataFrame, dzielnica: pd.Series) -> pd.DataFrame:
        metraz = X["metraz"].astype(float)
        cechy = {
            "metraz": np.log(metraz) if self.metraz_log else metraz,
            "pokoje": X["pokoje"].astype(float),
            "pietro": X["pietro"].astype(float),
        }
        przedzial = przedzial_roku_budowy(X["rok_budowy"])
        for etykieta, _, _ in PRZEDZIALY_ROKU:
            if etykieta != PRZEDZIAL_ODNIESIENIA:
                cechy[f"rok_budowy={etykieta}"] = (przedzial == etykieta).astype(float)
        for kategoria in self.kategorie_dzielnic_:
            cechy[f"dzielnica={kategoria}"] = (dzielnica == kategoria).astype(float)
        return pd.DataFrame(cechy, index=X.index)

    # --- kontrakt ------------------------------------------------------------------------------------------------

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModelLiniowy":
        self.sprawdz_kolumny(X)
        liczby = X.groupby(["miasto", "dzielnica"]).size()
        male = liczby[liczby < self.min_transakcji_dzielnicy]
        self.dzielnice_polaczone_ = {k: int(v) for k, v in male.items()}
        self.miasta_ = sorted(X["miasto"].unique())
        polaczone = {_klucz(*k) for k in self.dzielnice_polaczone_}
        surowe = pd.Series([_klucz(m, d) for m, d in zip(X["miasto"], X["dzielnica"])], index=X.index)
        dzielnica = surowe.where(~surowe.isin(polaczone), X["miasto"].map(lambda m: _klucz(m, RESZTA_MIASTA)))
        self.kategorie_dzielnic_ = sorted(dzielnica.unique())
        self.liczba_transakcji_kategorii_ = dzielnica.value_counts().to_dict()

        A = self._macierz(X, dzielnica)
        self.reg_ = LinearRegression(fit_intercept=False).fit(A.to_numpy(), np.log(np.asarray(y, dtype=float)))
        self.wspolczynniki_ = pd.Series(self.reg_.coef_, index=A.columns)

        # Poziom „średnia miasta” dla dzielnic nieznanych w mieście bez „reszty miasta”.
        self.srednia_miasta_ = {}
        for miasto in self.miasta_:
            kat = [k for k in self.kategorie_dzielnic_ if k.startswith(f"{miasto} | ")]
            wagi = np.array([self.liczba_transakcji_kategorii_[k] for k in kat], dtype=float)
            poziomy = np.array([self.wspolczynniki_[f"dzielnica={k}"] for k in kat])
            self.srednia_miasta_[_klucz(miasto, SREDNIA_MIASTA)] = float(np.average(poziomy, weights=wagi))
        return self

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Wkłady cech do ln(wyceny): suma kolumn `wklad_*` = ln(wycena_pln)."""
        self.sprawdz_kolumny(X)
        dzielnica = self._dzielnica_w_modelu(X)
        A = self._macierz(X, dzielnica)
        wklady = A * self.wspolczynniki_
        kolumny_roku = [k for k in A.columns if k.startswith("rok_budowy=")]
        kolumny_dzielnic = [k for k in A.columns if k.startswith("dzielnica=")]
        wyj = pd.DataFrame(
            {
                "dzielnica_w_modelu": dzielnica,
                "przedzial_roku_budowy": przedzial_roku_budowy(X["rok_budowy"]),
                "wklad_dzielnica": wklady[kolumny_dzielnic].sum(axis=1) + dzielnica.map(self.srednia_miasta_).fillna(0),
                "wklad_metraz": wklady["metraz"],
                "wklad_pokoje": wklady["pokoje"],
                "wklad_pietro": wklady["pietro"],
                "wklad_rok_budowy": wklady[kolumny_roku].sum(axis=1),
            },
            index=X.index,
        )
        wyj["wycena_pln"] = np.exp(wyj[[k for k in wyj.columns if k.startswith("wklad_")]].sum(axis=1))
        return wyj

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.explain(X)["wycena_pln"].to_numpy()

    def efekty_procentowe(self) -> pd.DataFrame:
        """Współczynniki jako zmiana ceny w % (100·(e^b − 1)) przy pozostałych cechach bez zmian.

        - dzielnica: b = poziom dzielnicy − średni poziom dzielnic jej miasta (ważony liczbą transakcji treningowych);
        - rok budowy: b względem przedziału 1970–1989;
        - pokoje, piętro: b na +1 pokój / +1 piętro;
        - metraż: przy ln(metraż) efekt +10% metrażu, czyli 100·(1,1^b − 1) (e^b − 1 dotyczyłoby metrażu × e).
        """
        w = self.wspolczynniki_
        wiersze = []
        for kat in self.kategorie_dzielnic_:
            miasto = kat.split(" | ")[0]
            b = w[f"dzielnica={kat}"] - self.srednia_miasta_[_klucz(miasto, SREDNIA_MIASTA)]
            wiersze.append(
                (
                    "dzielnica: " + kat,
                    "dzielnica",
                    b,
                    f"średnia dzielnic: {miasto}",
                    self.liczba_transakcji_kategorii_[kat],
                )
            )
        for etykieta, _, _ in PRZEDZIALY_ROKU:
            if etykieta != PRZEDZIAL_ODNIESIENIA:
                wiersze.append(
                    (f"rok budowy: {etykieta}", "rok_budowy", w[f"rok_budowy={etykieta}"], PRZEDZIAL_ODNIESIENIA, None)
                )
        wiersze.append(("pokoje (+1)", "pokoje", w["pokoje"], "o 1 pokój mniej", None))
        wiersze.append(("piętro (+1)", "pietro", w["pietro"], "o 1 piętro niżej", None))
        ef = pd.DataFrame(wiersze, columns=["cecha", "typ", "b", "odniesienie", "transakcje_trening"])
        ef["efekt_proc"] = 100 * (np.exp(ef["b"]) - 1)
        if self.metraz_log:
            metraz = (
                "metraż (+10%)",
                "metraz",
                w["metraz"],
                "metraż o 10% mniejszy",
                None,
                100 * (1.1 ** w["metraz"] - 1),
            )
        else:
            metraz = ("metraż (+1 m²)", "metraz", w["metraz"], "o 1 m² mniej", None, 100 * (np.exp(w["metraz"]) - 1))
        ef.loc[len(ef)] = metraz
        return ef
