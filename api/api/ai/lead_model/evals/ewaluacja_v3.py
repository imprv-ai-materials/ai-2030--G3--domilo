"""Uczenie i ocena v3_ev_kalibracja po wykluczeniu cech chronionych (docs/kolejka_cechy_chronione.md).

Uruchomienie (po `pypyr baza` i `evals/kalibracja.py`, którego wynik jest stanem „przed”):
    cd api && poetry run python -m api.ai.lead_model.evals.ewaluacja_v3 [--bez-mlflow]

- Wykluczone: features/leady/wykluczone.yaml (jezyk, imie, rok_urodzenia). v3 uczy się na `KOLUMNY_CECH`
  sprawdzonych względem tej listy.
- „Przed”: v2b uczony do 2025-06 + ta sama kalibracja, z przebiegu evals/kalibracja.py (wyniki/kalibracja.parquet),
  czyli ta sama procedura przed dodaniem listy wykluczeń. „Po”: v3 uczony teraz.
- Zbiory (podzial_v2): uczenie = trening z utworzeniem < 2025-07-01, kalibracja = trening 2025-07 – 2026-02;
  ocena: okno migracji (główna) i test 2026-03 – 2026-06. Baseline v0_regula_zrodla uczona na tym samym uczeniu.
- Audyt (pola chronione czytane tylko tutaj, nigdy jako cecha): wyniki v3 w grupach `crm_leady.jezyk` w oknie,
  na ile cechy modelu zdradzają język (LightGBM jezyk ≠ pl z cech, uczony na treningu, AUC na teście),
  czy imię zostaje w treści wysyłanej do LLM po zamianie na „[imię]”.
Zapis: versions/v3_ev_kalibracja/{model.joblib, metryki.json}, MLflow (`leady`, run `v3_ev_kalibracja`).
"""

import json
import re
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd
from api.adapters.duckdb_baza import polacz
from api.adapters.mlflow_rejestr import ustaw_eksperyment, zapisz_run
from api.ai.features.leady.cechy import KATEGORIE, KOLUMNY_CECH, SYGNALY_KOLUMNY
from api.ai.features.leady.ocena_llm import SQL_LEADOW, _bez_imienia
from api.ai.features.leady.wykluczone import WYKLUCZONE, wczytaj_wykluczone
from api.ai.lead_model.evals.ewaluacja import EKSPERYMENT_MLFLOW, KATALOG_MODELU, KATALOG_WYNIKOW
from api.ai.lead_model.evals.ewaluacja_v2 import _json, _z_ci, przygotuj, target_treningu
from api.ai.lead_model.evals.kalibracja import miary
from api.ai.lead_model.evals.metryki import bootstrap_par, dzienna_liczba_zapytan
from api.ai.lead_model.versions.v0_regula_zrodla.model import ModelRegulaZrodla
from api.ai.lead_model.versions.v3_ev_kalibracja.model import KONIEC_TRENINGU, ModelV3EVKalibracja
from sklearn.metrics import roc_auc_score

ZBIORY_OCENY = ("okno_migracji", "test")
CECHY_Z_TEKSTU = (*SYGNALY_KOLUMNY, "dlugosc_wiadomosci")


def _macierz_kat(X: pd.DataFrame, cechy) -> pd.DataFrame:
    x = X[list(cechy)].copy()
    for k in cechy:
        x[k] = x[k].astype("category") if k in KATEGORIE else x[k].astype("float64")
    return x


def sila_sladu_jezyka(cechy: dict, jezyk_tr: np.ndarray, jezyk_te: np.ndarray) -> dict:
    """AUC przewidywania jezyk ≠ pl z cech modelu (LightGBM), wszystkie cechy i bez cech z tekstu wiadomości."""
    wynik = {"udzial_nie_pl_test": float(jezyk_te.mean())}
    bez_tekstu = tuple(c for c in KOLUMNY_CECH if c not in CECHY_Z_TEKSTU)
    for nazwa, kol in (("wszystkie_cechy", KOLUMNY_CECH), ("bez_cech_z_tekstu", bez_tekstu)):
        m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, random_state=42, verbose=-1)
        m.fit(_macierz_kat(cechy["trening"], kol), jezyk_tr)
        p_test = m.predict_proba(_macierz_kat(cechy["test"], kol))[:, 1]
        wynik[f"auc_{nazwa}"] = float(roc_auc_score(jezyk_te, p_test))
        if nazwa == "wszystkie_cechy":
            gain = pd.Series(m.booster_.feature_importance("gain"), index=kol)
            wynik["udzial_gain_top5"] = (gain / gain.sum()).sort_values(ascending=False).head(5).to_dict()
    return wynik


def _ci_roznicy(p: np.ndarray, y: np.ndarray, n_prob: int = 2000, ziarno: int = 42) -> list[float]:
    """95% CI (bootstrap zapytań w grupie) dla średnie p − odsetek umów."""
    rng = np.random.default_rng(ziarno)
    proby = [(p[i].mean() - y[i].mean()) for i in (rng.integers(0, len(p), len(p)) for _ in range(n_prob))]
    return [float(np.percentile(proby, 2.5)), float(np.percentile(proby, 97.5))]


def grupy_jezyka(okno: pd.DataFrame, p: np.ndarray) -> list[dict]:
    """Okno migracji: w każdej grupie języka liczba zapytań, umowy, konwersja, średnie p, udział w górnych 10%, AUC."""
    df = okno[["jezyk", "umowa_45d"]].assign(p=p)
    df["czolowka"] = df["p"].rank(ascending=False, method="first") <= round(0.10 * len(df))
    wiersze = []
    for jezyk, g in df.groupby("jezyk"):
        wiersze.append({
            "jezyk": jezyk, "zapytania": len(g), "umowy": int(g["umowa_45d"].sum()),
            "konwersja": float(g["umowa_45d"].mean()), "srednie_p": float(g["p"].mean()),
            "udzial_w_czolowce_10": float(g["czolowka"].mean()),
            "auc": float(roc_auc_score(g["umowa_45d"], g["p"])) if 0 < g["umowa_45d"].sum() < len(g) else None,
            "srednie_p_minus_konwersja_ci95": _ci_roznicy(g["p"].to_numpy(), g["umowa_45d"].to_numpy()),
        })  # fmt: skip
    return wiersze


def slad_imienia(con) -> dict:
    """Ile treści po zamianie imienia na „[imię]” wciąż zawiera rdzeń imienia (imię bez ostatniej litery, gdy > 4)."""
    leady = con.execute(SQL_LEADOW).df()
    leady = leady[leady["wiadomosc"].notna() & leady["imie"].notna()]
    przed, po, przyklady = 0, 0, []
    for r in leady.itertuples():
        imie = str(r.imie).strip()
        rdzen = re.compile(rf"(?<!\w){re.escape(imie[:-1] if len(imie) > 4 else imie)}", re.I)
        przed += bool(rdzen.search(str(r.wiadomosc)))
        tekst = _bez_imienia(str(r.wiadomosc), r.imie)
        trafienie = rdzen.search(tekst)
        if trafienie:
            po += 1
            przyklady.append(f"{imie}: …{tekst[max(0, trafienie.start() - 15):trafienie.end() + 10]}…")
    return {"wiadomosci_z_imieniem_w_polu": len(leady), "rdzen_imienia_w_tresci_przed": przed,
            "rdzen_imienia_po_zamianie": po, "przyklady_po_zamianie": sorted(set(przyklady))[:10]}  # fmt: skip


def main(mlflow_wlaczony: bool = True) -> None:
    con = polacz()
    zbiory, cechy = przygotuj(con)
    jezyk = con.execute("SELECT id_leada, jezyk FROM crm_leady").df().set_index("id_leada")["jezyk"]
    audyt_imienia = slad_imienia(con)
    con.close()

    tr = zbiory["trening"]
    X_tr = cechy["trening"].assign(obsluzony=tr["obsluzony"].to_numpy())
    v3 = ModelV3EVKalibracja().fit(X_tr, tr["umowa_45d"].astype(int).to_numpy())
    uczacy = (tr["utworzono"] < KONIEC_TRENINGU).to_numpy()
    v0 = ModelRegulaZrodla().fit(tr[uczacy], target_treningu(tr[uczacy]))
    przed = pd.read_parquet(KATALOG_WYNIKOW / "kalibracja.parquet")

    metryki = {
        "wersja": v3.wersja,
        "wykluczone": wczytaj_wykluczone(),
        "cechy": list(v3.cechy),
        "cechy_wykluczone_w_modelu": sorted(set(v3.cechy) & WYKLUCZONE),
        "cechy_boostera": list(v3.booster_.feature_name()),
        "uczony_na": "trening podzial_v2 z utworzeniem < 2025-07-01; kalibracja: obsłużone 2025-07 – 2026-02 z IPW",
        "liczebnosci": v3.liczebnosci_,
        "liczba_drzew": v3.model_.liczba_drzew_,
        "audyt_imienia": audyt_imienia,
        "slad_jezyka_w_cechach": sila_sladu_jezyka(
            cechy,
            (tr["id_leada"].map(jezyk) != "pl").astype(int).to_numpy(),
            (zbiory["test"]["id_leada"].map(jezyk) != "pl").astype(int).to_numpy(),
        ),
    }
    for nazwa in ZBIORY_OCENY:
        zbior, X = zbiory[nazwa], cechy[nazwa]
        y = zbior["umowa_45d"].astype(int).to_numpy()
        k = dzienna_liczba_zapytan(zbior["utworzono"])
        p_v3 = v3.predict(X)
        p_przed = (
            zbior[["id_leada"]]
            .merge(przed.loc[przed["zbior"] == nazwa, ["id_leada", "wynik_v2b_kontakt"]], on="id_leada", how="left")
            ["wynik_v2b_kontakt"].to_numpy()
        )  # fmt: skip
        if np.isnan(p_przed).any():
            raise RuntimeError(f"Brak wyniku „przed” dla części zapytań {nazwa}: uruchom evals/kalibracja.py")
        p_v0 = v0.predict(zbior)
        ci_v0 = bootstrap_par(y, p_v3, p_v0, k)
        ci_przed = bootstrap_par(y, p_v3, p_przed, k)
        obsl = zbior["obsluzony"].to_numpy(dtype=bool)
        metryki[nazwa] = {
            "v3_ev_kalibracja": _z_ci(miary(y, p_v3, k), ci_v0, "a"),
            "przed_wykluczeniem": _z_ci(miary(y, p_przed, k), ci_przed, "b"),
            "v0_regula_zrodla": _z_ci(miary(y, p_v0, k), ci_v0, "b"),
            "roznica_v3_minus_przed_ci95": {m: ci_przed[f"{m}_roznica"] for m in ("auc", "lift", "prec")},
            "roznica_v3_minus_v0_ci95": {m: ci_v0[f"{m}_roznica"] for m in ("auc", "lift", "prec")},
            "maks_roznica_p_v3_przed": float(np.max(np.abs(p_v3 - p_przed))),
            "v3_obsluzone": miary(y[obsl], p_v3[obsl], k) if obsl.sum() < len(y) else None,
        }
        if nazwa == "okno_migracji":
            metryki[nazwa]["grupy_jezyka_v3"] = grupy_jezyka(zbior.assign(jezyk=zbior["id_leada"].map(jezyk)), p_v3)

    katalog = KATALOG_MODELU / "versions" / v3.wersja
    v3.zapisz(katalog / "model.joblib")
    (katalog / "metryki.json").write_text(json.dumps(metryki, ensure_ascii=False, indent=2, default=_json), "utf-8")

    if mlflow_wlaczony:
        ustaw_eksperyment(EKSPERYMENT_MLFLOW)
        plaskie = {
            f"{z}_{w}_{m}": metryki[z][w][m]
            for z in ZBIORY_OCENY
            for w in ("v3_ev_kalibracja", "przed_wykluczeniem", "v0_regula_zrodla")
            for m in ("auc", "lift_10", "precision_k", "ece_10_rowne", "brier")
        }
        plaskie["auc_jezyk_z_cech"] = metryki["slad_jezyka_w_cechach"]["auc_wszystkie_cechy"]
        run = zapisz_run(
            v3.wersja,
            parametry={
                "wersja": v3.wersja,
                "wykluczone": ",".join(sorted(WYKLUCZONE)),
                "cechy": ",".join(v3.cechy)[:500],
                "kalibracja": "izotoniczna kontakt (IPW), 2025-07 – 2026-02",
                "koniec_treningu": "2025-07-01",
            },
            metryki=plaskie,
            tagi={"zbior_oceny": "okno migracji + test 2026-03 – 2026-06", "target": "leady_cel.umowa_45d"},
            artefakty=[katalog / "metryki.json", katalog / "model.joblib"],
        )
        print(f"MLflow: eksperyment {EKSPERYMENT_MLFLOW}, run {v3.wersja} = {run}")
    pokaz = ("auc", "lift_10", "precision_k", "ece_10_rowne", "brier")
    for z in ZBIORY_OCENY:
        for w in ("przed_wykluczeniem", "v3_ev_kalibracja", "v0_regula_zrodla"):
            print(z, w, {m: round(float(metryki[z][w][m]), 4) for m in pokaz})
        print(z, "maks |Δp|", metryki[z]["maks_roznica_p_v3_przed"], metryki[z]["roznica_v3_minus_przed_ci95"])
    klucze = ("cechy_wykluczone_w_modelu", "audyt_imienia", "slad_jezyka_w_cechach", "liczebnosci")
    print(json.dumps({k: metryki[k] for k in klucze}, ensure_ascii=False, indent=1, default=_json))
    print(pd.DataFrame(metryki["okno_migracji"]["grupy_jezyka_v3"]).round(4).to_string(index=False))


if __name__ == "__main__":
    main(mlflow_wlaczony="--bez-mlflow" not in sys.argv[1:])
