"""zapasowa_if: reguła zapasowa dla wind bez normy (pierwsze `DNI_BEZ_NORMY` dni telemetrii);
docs/b4_dryf_i_fallback.md.

Model główny (v3) porównuje sygnały windy z jej własną normą z 30 dni (dni 15–44 przed oceną). Nowa winda jej nie ma
(np. 11 wind z B37 i B38 od 2024-09-15), więc zamiast tego porównujemy ją z innymi windami tego samego modelu
(`serwis_windy.model`):
- cechy: średnia i maksimum z 24 h / 3 / 7 dni (`STATYSTYKI`) sygnałów, które wskazują podzespół
  (maintenance_bc/podzespoly.yaml, podzespół ≠ null) — bez norm, stosunków do normy i trendu;
- Isolation Forest (scikit-learn) osobno dla każdego modelu windy, uczony na dniach dojrzałych wind tego modelu
  (co najmniej `DNI_BEZ_NORMY` dni telemetrii); braki (np. wibracje przed montażem czujnika) = mediana z uczenia;
- `wynik` = −score_samples (wyżej = bardziej nietypowo); próg = kwantyl (1 − `udzial_alarmow`) wyników na danych
  uczących modelu windy. `udzial_alarmow` = alarmy_na_tydzien / liczba wind (maintenance_bc/zalozenia.yaml,
  serwis_windy), czyli reguła zapasowa alarmuje tak często jak reguła modelu głównego;
- `odchylenia`: 2 cechy różnych sygnałów najdalej od mediany modelu windy w jednostkach rozstępu międzykwartylowego
  (do opisu alertu).
Parametry lasu (`N_DRZEW`, `ZIARNO`) to stałe techniczne przyjęte w tej pracy.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

DNI_BEZ_NORMY = 44  # od użytkownika (2026-11-16): „windy w pierwszych 44 dniach telemetrii nie mają normy”
STATYSTYKI = ("sr_24h", "max_24h", "sr_3d", "max_3d", "sr_7d", "max_7d")
N_DRZEW = 200
ZIARNO = 42
ODCHYLEN_W_OPISIE = 2


def sygnal_cechy(cecha: str) -> str:
    """`<sygnał>_<statystyka>` -> sygnał (statystyki z STATYSTYKI)."""
    for st in STATYSTYKI:
        if cecha.endswith(f"_{st}"):
            return cecha[: -len(st) - 1]
    return cecha


class RegulaZapasowa:
    wersja = "zapasowa_if"

    def __init__(self, sygnaly: list[str], udzial_alarmow: float):
        self.sygnaly = tuple(sygnaly)
        self.cechy = tuple(f"{s}_{st}" for s in self.sygnaly for st in STATYSTYKI)
        self.udzial_alarmow = float(udzial_alarmow)

    def _macierz(self, dni: pd.DataFrame, model_windy: str) -> np.ndarray:
        return dni[list(self.cechy)].astype("float64").fillna(self.mediany_[model_windy]).to_numpy()

    def fit(self, dni: pd.DataFrame) -> "RegulaZapasowa":
        """dni: wiersze dojrzałych wind z kolumnami `model_windy` i self.cechy (każdy model windy osobno)."""
        self.lasy_, self.mediany_, self.rozstepy_, self.progi_, self.wiersze_ = {}, {}, {}, {}, {}
        for model_windy, grupa in dni.groupby("model_windy", sort=True):
            x = grupa[list(self.cechy)].astype("float64")
            self.mediany_[model_windy] = x.median()
            rozstep = (x.quantile(0.75) - x.quantile(0.25)).replace(0, np.nan)
            self.rozstepy_[model_windy] = rozstep.fillna(x.std().replace(0, np.nan)).fillna(1.0)
            las = IsolationForest(n_estimators=N_DRZEW, random_state=ZIARNO).fit(self._macierz(grupa, model_windy))
            self.lasy_[model_windy] = las
            wynik = -las.score_samples(self._macierz(grupa, model_windy))
            self.progi_[model_windy] = float(np.quantile(wynik, 1 - self.udzial_alarmow))
            self.wiersze_[model_windy] = len(grupa)
        return self

    def ocen(self, dni: pd.DataFrame) -> pd.DataFrame:
        """Dla każdego wiersza (kolumna `model_windy` + self.cechy): wynik, prog, alarm, odchylenia (lista dict)."""
        wyj = pd.DataFrame(index=dni.index, columns=["wynik", "prog", "alarm", "odchylenia"], dtype=object)
        for model_windy, grupa in dni.groupby("model_windy", sort=False):
            if model_windy not in self.lasy_:
                wyj.loc[grupa.index] = [[np.nan, np.nan, False, []]] * len(grupa)
                continue
            wynik = -self.lasy_[model_windy].score_samples(self._macierz(grupa, model_windy))
            prog = self.progi_[model_windy]
            z = (grupa[list(self.cechy)].astype("float64") - self.mediany_[model_windy]) / self.rozstepy_[model_windy]
            for i, (idx, w) in enumerate(zip(grupa.index, wynik, strict=True)):
                rzad = z.loc[idx].dropna()
                top, widziane = [], set()
                for c in rzad.abs().sort_values(ascending=False, kind="mergesort").index:
                    sygnal = sygnal_cechy(c)
                    if sygnal not in widziane:
                        top.append(c)
                        widziane.add(sygnal)
                    if len(top) == ODCHYLEN_W_OPISIE:
                        break
                odch = [
                    {
                        "cecha": c,
                        "wartosc": round(float(grupa.at[idx, c]), 4),
                        "mediana_modelu": round(float(self.mediany_[model_windy][c]), 4),
                        "odchylenie_iqr": round(float(rzad[c]), 2),
                    }
                    for c in top
                ]
                wyj.loc[idx] = [float(w), prog, bool(w >= prog), odch]
        wyj["wynik"] = wyj["wynik"].astype(float)
        wyj["prog"] = wyj["prog"].astype(float)
        wyj["alarm"] = wyj["alarm"].astype(bool)
        return wyj
