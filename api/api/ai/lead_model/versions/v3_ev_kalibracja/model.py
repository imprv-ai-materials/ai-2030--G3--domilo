"""v3: v2b_lgbm_ipw (bez cech wykluczonych) + kalibracja izotoniczna „kontakt” + wartość oczekiwana (EV) zapytania.

Składniki (docs/kolejka_cechy_chronione.md, ai/lead_model/evals/kalibracja.md, docs/kolejka_ev.md):
1. `ModelLGBMIPW` na cechach `KOLUMNY_CECH` (sprawdzonych względem features/leady/wykluczone.yaml), uczony na
   zapytaniach z utworzeniem przed `koniec_treningu` (domyślnie 2025-07-01).
2. Kalibracja izotoniczna na zapytaniach od `koniec_treningu`: tylko obsłużone, waga min(1 / P(obsłużony), 10)
   z modelu skłonności z kroku 1. `predict` = szansa na umowę w 45 dni po kontakcie doradcy.
3. `wartosc_oczekiwana`: EV = p × mediana czynszu × czas najmu × liczba lokali (contexts_boundaries/leasing_bc).
Kolejka: według EV malejąco; uzasadnienie: SHAP z kroku 1 (`explain`, ai/lead_model/uzasadnienie.py).
"""

import numpy as np
import pandas as pd
from api.ai.features.leady.cechy import KOLUMNY_CECH
from api.ai.features.leady.wykluczone import sprawdz_brak_wykluczonych
from api.ai.lead_model.base import ModelLeadow
from api.ai.lead_model.versions.v2b_lgbm_ipw.model import ModelLGBMIPW
from api.contexts_boundaries.leasing_bc.wartosc import wartosc_oczekiwana
from sklearn.isotonic import IsotonicRegression

KONIEC_TRENINGU = pd.Timestamp("2025-07-01", tz="Europe/Warsaw")


class ModelV3EVKalibracja(ModelLeadow):
    wersja = "v3_ev_kalibracja"

    def __init__(self, cechy: tuple[str, ...] = KOLUMNY_CECH, koniec_treningu: pd.Timestamp = KONIEC_TRENINGU):
        sprawdz_brak_wykluczonych(cechy, self.wersja)
        self.cechy = tuple(cechy)
        self.koniec_treningu = koniec_treningu

    def fit(self, leady: pd.DataFrame, y, obsluzony=None) -> "ModelV3EVKalibracja":
        """`leady`: cechy + `utworzono` (+ `obsluzony`, jeśli nie podano osobno), cały zbiór uczący z walidacją."""
        y = np.asarray(y, dtype=int)
        obsl = np.asarray(leady["obsluzony"] if obsluzony is None else obsluzony, dtype=bool)
        uczacy = (pd.to_datetime(leady["utworzono"], utc=True) < self.koniec_treningu).to_numpy()
        if uczacy.all() or not uczacy.any():
            raise ValueError("fit: potrzebne zapytania przed i po koniec_treningu (uczenie i kalibracja)")
        tr = leady[uczacy].reset_index(drop=True).assign(obsluzony=obsl[uczacy])
        self.model_ = ModelLGBMIPW(cechy=self.cechy).fit(tr, y[uczacy])
        wal = leady[~uczacy].reset_index(drop=True)
        wal_obsl = wal[obsl[~uczacy]].reset_index(drop=True)
        wagi = self.model_.wagi(wal_obsl)
        self.kalibracja_ = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(
            self.model_.predict(wal_obsl), y[~uczacy][obsl[~uczacy]], sample_weight=wagi
        )
        self.liczebnosci_ = {
            "trening": int(uczacy.sum()),
            "trening_obsluzone": int(obsl[uczacy].sum()),
            "kalibracja_obsluzone": int(len(wal_obsl)),
            "kalibracja_umowy": int(y[~uczacy][obsl[~uczacy]].sum()),
            "kalibracja_suma_wag": float(wagi.sum()),
        }
        return self

    def predict_przed_kalibracja(self, leady: pd.DataFrame) -> np.ndarray:
        return self.model_.predict(leady)

    def predict(self, leady: pd.DataFrame) -> np.ndarray:
        """Szansa na umowę w 45 dni po kontakcie (po kalibracji)."""
        return self.kalibracja_.predict(self.model_.predict(leady))

    def explain(self, leady: pd.DataFrame) -> pd.DataFrame:
        """`wynik` (po kalibracji), `wynik_przed_kalibracja` i wkłady SHAP (log-szansa przed kalibracją)."""
        wyj = self.model_.explain(leady)
        wyj.insert(0, "wynik_przed_kalibracja", wyj["wynik"].to_numpy())
        wyj["wynik"] = self.kalibracja_.predict(wyj["wynik_przed_kalibracja"].to_numpy())
        return wyj

    def wartosc_oczekiwana(self, X: pd.DataFrame, leady: pd.DataFrame, zalozenia: dict | None = None) -> np.ndarray:
        """EV (PLN) dla zapytań: X = cechy modelu, leady = miasto, linia_pref, liczba_lokali (te same wiersze)."""
        return wartosc_oczekiwana(self.predict(X), leady, zalozenia)

    @property
    def booster_(self):
        return self.model_.booster_
