"""v2_przezycie_cox: model Coxa (lifelines) na okresach umów, cechy v1 policzone na początek okresu.

Jednostka: okres umowy rocznej (features/najemcy/okresy_umow.sql). Czas = miesiące od początku okresu do końca
najmu w tym okresie (zdarzenie = 1) albo do końca okresu / końca obserwacji (cenzura). Najem przedłużony ma kolejny
wiersz z nowymi cechami, więc cechy są aktualizowane na początku każdego okresu.

To inny kontrakt niż base.ModelNajemcow (ryzyko 0–1 w dniu migawki, 60 dni przed końcem umowy): v2 ocenia ryzyko
od początku okresu. Wspólna jest ochrona przed kolumnami zakazanymi (base.KOLUMNY_ZAKAZANE).

Cechy (`KOLUMNY_CECH` v1 po przekształceniu, `przygotuj`):
- linia -> `b2b` (1 = B2B);
- indeksacja_ostatnia_pct -> `indeksacja_powyzej_6` (1 = indeksacja bieżącego przedłużenia > 6%; 0 także dla
  pierwszej umowy, którą odróżnia `nr_okresu`);
- staz_dni -> `staz_lat` (dni / 365,25; ta sama informacja, czytelniejszy HR);
- windy_awarie_90d_na_winde pominięta (= windy_awarie_90d / liczba_wind, puste dla budynków bez wind);
- nr_okresu pominięty: na treningu korelacja ze staz_lat wynosi 1,00 (oba mierzą to samo, a razem dają
  nieczytelne współczynniki); pierwszy okres to staz_lat = 0;
- braki: mediana z treningu; dla czynsz_do_podobnych dodatkowo `czynsz_do_podobnych_brak`. Brak płatności, ocen,
  ankiet i logowań opisują już cechy v1 (plat_liczba_90d = 0, ocena_liczba_365d = 0, ankieta_brak_wyniku,
  portal_miesiace_3m = 0).
Warstwy (`warstwy`): kolumny, dla których model ma osobną krzywą bazową zamiast współczynnika (stratyfikacja).
Interakcje z czasem (`interakcje_czasu`): cecha × 1[czas >= próg] przez podział wiersza w progu (lifelines nie ma
zmiennych zależnych od czasu w CoxPHFitter, więc wiersz dzielimy na dwa: [0, próg) i [próg, koniec)).
"""

import numpy as np
import pandas as pd
from api.ai.churn_model.base import KOLUMNY_ZAKAZANE
from api.ai.features.najemcy.cechy import KOLUMNY_CECH
from lifelines import CoxPHFitter
from scipy.optimize import brentq

POMINIETE_Z_V1 = ("windy_awarie_90d_na_winde", "nr_okresu")
ZAMIANY = {"linia": "b2b", "indeksacja_ostatnia_pct": "indeksacja_powyzej_6", "staz_dni": "staz_lat"}
CECHY = tuple(ZAMIANY.get(k, k) for k in KOLUMNY_CECH if k not in POMINIETE_Z_V1) + ("czynsz_do_podobnych_brak",)
PROG_INDEKSACJI = 6.0
HORYZONT_RYZYKA = 12.0  # ryzyko = 1 - S(12 mies. od początku okresu | cechy), porównywalne między warstwami
# Specyfikacja v2 ustalona po teście Schoenfelda na treningu, przed oceną na teście (docs/przezycie_cox.md):
# warstwy po długości umowy (12 / 18 / 24 mies.), interakcja z czasem dla cech łamiących proporcjonalność po
# poprawce Bonferroniego; próg 11,5 mies. oddziela koniec najmu w trakcie okresu od końca na koniec umowy.
WARSTWY_V2 = ("miesiecy_umowy",)
PROG_KONCA_OKRESU = 11.5
INTERAKCJE_V2 = {"czynsz_m2": PROG_KONCA_OKRESU, "zgl_365d": PROG_KONCA_OKRESU}


def przygotuj(okresy: pd.DataFrame) -> pd.DataFrame:
    """Kolumny CECH z cech v1 okresu (bez uzupełniania braków)."""
    X = pd.DataFrame(index=okresy.index)
    for k in KOLUMNY_CECH:
        if k in POMINIETE_Z_V1:
            continue
        if k == "linia":
            X["b2b"] = (okresy["linia"] == "B2B").astype(float)
        elif k == "indeksacja_ostatnia_pct":
            X["indeksacja_powyzej_6"] = (okresy[k].fillna(0) > PROG_INDEKSACJI).astype(float)
        elif k == "staz_dni":
            X["staz_lat"] = okresy[k].astype(float) / 365.25
        else:
            X[k] = okresy[k].astype(float)
    X["czynsz_do_podobnych_brak"] = okresy["czynsz_do_podobnych"].isna().astype(float)
    return X[list(CECHY)]


class ModelCox:
    wersja = "v2_przezycie_cox"

    def __init__(
        self,
        cechy: tuple[str, ...] = CECHY,
        warstwy: tuple[str, ...] = WARSTWY_V2,
        interakcje_czasu: dict[str, float] | None = INTERAKCJE_V2,
        penalizer: float = 0.0,
    ):
        zle = sorted(set(cechy) & KOLUMNY_ZAKAZANE)
        if zle:
            raise ValueError(f"{self.wersja}: kolumny zakazane jako cechy (churn_model/base.py): {', '.join(zle)}")
        self.cechy = tuple(cechy)
        self.warstwy = tuple(warstwy)
        self.interakcje_czasu = dict(interakcje_czasu or {})
        if not set(self.warstwy) <= set(self.cechy):
            raise ValueError(f"{self.wersja}: warstwy muszą być wśród cech")
        self.penalizer = penalizer

    # --- dane --------------------------------------------------------------------------------------------------

    def macierz(self, okresy: pd.DataFrame) -> pd.DataFrame:
        """Cechy po przygotowaniu i uzupełnieniu braków medianą z treningu (bez czasu i zdarzenia)."""
        X = przygotuj(okresy)[list(self.cechy)]
        return X.fillna(self.mediany_)

    def _ramka(self, okresy: pd.DataFrame) -> pd.DataFrame:
        """Ramka do lifelines: cechy + czas, zdarzenie, klaster (id_najemcy); podział wierszy przy interakcjach."""
        df = self.macierz(okresy)
        df["czas"] = okresy["czas"].astype(float).to_numpy()
        df["zdarzenie"] = okresy["zdarzenie"].astype(int).to_numpy()
        df["klaster"] = okresy["id_najemcy"].to_numpy()
        if not self.interakcje_czasu:
            df["start"] = 0.0
            return df
        progi = sorted(set(self.interakcje_czasu.values()))
        czesci = []
        granice = [0.0, *progi, np.inf]
        for od, do in zip(granice[:-1], granice[1:]):
            cz = df[df["czas"] > od].copy()
            cz["start"] = od
            cz["zdarzenie"] = np.where(cz["czas"] <= do, cz["zdarzenie"], 0)
            cz["czas"] = np.minimum(cz["czas"], do)
            for cecha, prog in self.interakcje_czasu.items():
                cz[f"{cecha}_po_{prog:g}"] = cz[cecha] * float(od >= prog)
            czesci.append(cz)
        return pd.concat(czesci, ignore_index=True)

    # --- uczenie i wynik ---------------------------------------------------------------------------------------

    def fit(self, okresy: pd.DataFrame) -> "ModelCox":
        self.mediany_ = przygotuj(okresy)[list(self.cechy)].median()
        df = self._ramka(okresy)
        self.cph_ = CoxPHFitter(penalizer=self.penalizer, strata=list(self.warstwy) or None)
        opcje = {"entry_col": "start"} if self.interakcje_czasu else {}
        self.cph_.fit(
            df.drop(columns=[] if self.interakcje_czasu else ["start"]),
            "czas",
            "zdarzenie",
            cluster_col="klaster",
            **opcje,
        )
        self.baza_kp_ = self._baza_kalbfleisch_prentice(df)
        self.liczba_okresow_ = int(len(okresy))
        self.liczba_zdarzen_ = int(okresy["zdarzenie"].sum())
        return self

    def _baza_kalbfleisch_prentice(self, df: pd.DataFrame) -> pd.DataFrame:
        """Skumulowany hazard bazowy Kalbfleischa-Prentice'a (-Σ log α_j) na warstwę, przy tych samych β i centrowaniu.

        W każdym czasie zdarzenia t_j α_j rozwiązuje Σ_{zdarzenia} θ_i / (1 - α^θ_i) = Σ_{ryzyko} θ_i,
        θ_i = exp((z_i - średnia)·β); S(t | x) = Π_{t_j <= t} α_j^θ(x). W odróżnieniu od Breslowa nie zakłada ciągłego
        czasu, więc zgadza się z Kaplanem-Meierem także przy wielu zdarzeniach w jednym dniu (koniec umowy)."""
        beta = self.cph_.params_
        theta = np.exp(((df[beta.index] - self.cph_._norm_mean.reindex(beta.index)) * beta).sum(axis=1)).to_numpy()
        start = df["start"].to_numpy() if "start" in df else np.zeros(len(df))
        czas, zdarzenie = df["czas"].to_numpy(), df["zdarzenie"].to_numpy().astype(bool)
        klucze = df[self.warstwy[0]].to_numpy() if self.warstwy else np.zeros(len(df))
        kolumny = {}
        for warstwa in np.unique(klucze):
            w = klucze == warstwa
            czasy_zd = np.unique(czas[w & zdarzenie])
            H = []
            for tj in czasy_zd:
                ryzyko = theta[w & (start < tj) & (czas >= tj)].sum()
                th_d = theta[w & zdarzenie & (czas == tj)]

                def f(x: float) -> float:  # α = exp(-x); Σ_D θ / (1 - α^θ) - Σ_R θ, przy θ = 1: α = 1 - d / n
                    return float(np.sum(th_d / -np.expm1(-x * th_d))) - ryzyko

                x = brentq(f, 1e-12, 50.0)  # f maleje: +∞ przy x -> 0, (Σ_D θ - Σ_R θ) <= 0 przy dużym x
                H.append(x)
            kolumny[warstwa] = pd.Series(np.cumsum(H), index=czasy_zd)
        bazowa = pd.DataFrame(kolumny).sort_index().ffill().fillna(0.0)
        bazowa.columns = list(kolumny)
        return bazowa

    def ramka_treningu(self, okresy: pd.DataFrame) -> pd.DataFrame:
        """Ramka w formacie z fit (do reszt Schoenfelda; tylko bez interakcji czasu)."""
        return self._ramka(okresy).drop(columns=["start"])

    def skumulowany_hazard(self, X: pd.DataFrame, czasy, metoda: str = "kp") -> np.ndarray:
        """H(t | x) dla cech po `macierz` (wiersze) i czasów od początku okresu (kolumny): macierz n × len(czasy).

        H(t) = suma po przedziałach [od, do) z (H0_warstwy(min(t, do)) - H0_warstwy(min(t, od))) × exp((z - średnia)·β),
        gdzie z to cechy z interakcjami właściwymi dla przedziału (cecha × 1[od >= próg]); S(t | x) = exp(-H(t | x)).
        metoda="kp" (domyślna): H0 Kalbfleischa-Prentice'a (`baza_kp_`, _baza_kalbfleisch_prentice).
        metoda="breslow": H0 z lifelines (Breslow), czyli S = exp(-H) jak predict_survival_function. Breslow zakłada
        ciągły czas; tu większość zdarzeń wypada w jednym dniu (koniec umowy), więc zawyża przeżycie
        (docs/przezycie_cox.md, sekcja „Kalibracja”)."""
        if metoda not in ("kp", "breslow"):
            raise ValueError(f"Nieznana metoda: {metoda}")
        czasy = np.atleast_1d(np.asarray(czasy, dtype=float))
        beta = self.cph_.params_
        srednie = self.cph_._norm_mean.reindex(beta.index)
        if metoda == "kp":
            bazowa = self.baza_kp_
        else:
            bazowa = self.cph_.baseline_cumulative_hazard_.sort_index().ffill().fillna(0.0)
        if self.warstwy:
            if len(self.warstwy) > 1:
                raise NotImplementedError("Obsługiwana jest jedna kolumna warstw")
            kolumny = list(bazowa.columns)
            nr_kolumny = X[self.warstwy[0]].map({k: i for i, k in enumerate(kolumny)})
            if nr_kolumny.isna().any():
                raise ValueError(f"Wartości warstwy spoza treningu: {sorted(set(X[self.warstwy[0]]) - set(kolumny))}")
            nr_kolumny = nr_kolumny.astype(int).to_numpy()
        else:
            nr_kolumny = np.zeros(len(X), dtype=int)
        t_bazowe, wartosci = bazowa.index.to_numpy(), bazowa.to_numpy()

        def H0(t: np.ndarray) -> np.ndarray:
            i = np.searchsorted(t_bazowe, t, side="right") - 1
            w = np.where((i >= 0)[:, None], wartosci[np.clip(i, 0, None)], 0.0)  # len(t) × warstwy
            return w[:, nr_kolumny].T  # n × len(t)

        progi = sorted(set(self.interakcje_czasu.values()))
        granice = [0.0, *progi, np.inf]
        H = np.zeros((len(X), len(czasy)))
        for od, do in zip(granice[:-1], granice[1:]):
            Z = X.copy()
            for cecha, prog in self.interakcje_czasu.items():
                Z[f"{cecha}_po_{prog:g}"] = Z[cecha] * float(od >= prog)
            lp = ((Z[beta.index] - srednie) * beta).sum(axis=1).to_numpy()
            H += (H0(np.minimum(czasy, do)) - H0(np.minimum(czasy, od))) * np.exp(lp)[:, None]
        return H

    def ryzyko(self, okresy: pd.DataFrame, horyzont: float = HORYZONT_RYZYKA, metoda: str = "kp") -> np.ndarray:
        """1 - S(horyzont | cechy z początku okresu): ryzyko końca najmu w `horyzont` mies. od początku okresu.

        metoda="breslow" bez interakcji z czasem to wynik CoxPHFitter.predict_survival_function (sprawdza test)."""
        return 1.0 - np.exp(-self.skumulowany_hazard(self.macierz(okresy), [horyzont], metoda)[:, 0])

    def hazard_ratio(self) -> pd.DataFrame:
        """HR = exp(coef) z 95% przedziałem (odporne błędy standardowe, klaster = najemca) i p."""
        s = self.cph_.summary
        return pd.DataFrame(
            {
                "hr": s["exp(coef)"],
                "hr_95_od": s["exp(coef) lower 95%"],
                "hr_95_do": s["exp(coef) upper 95%"],
                "p": s["p"],
            }
        )

    def explain(self, okresy: pd.DataFrame) -> pd.DataFrame:
        """`ryzyko` + wkład każdej cechy w log-hazard względem średniej treningu: (x - średnia) × β."""
        X = self.macierz(okresy)
        beta = self.cph_.params_.reindex(self.cechy).fillna(0.0)  # warstwy nie mają współczynnika
        srednie = self.cph_._norm_mean.reindex(self.cechy).fillna(0.0)
        wyj = (X - srednie) * beta
        wyj.columns = [f"wklad_{k}" for k in X.columns]
        wyj.insert(0, "ryzyko", self.ryzyko(okresy))
        return wyj
