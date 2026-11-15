import datetime as dt

import joblib
import numpy as np
import pandas as pd
import pytest
from api.ai.lead_model.base import KOLUMNY_WEJSCIA, ModelLeadow
from api.ai.lead_model.evals.metryki import dzienna_liczba_zapytan, lift_at, metryki_rankingu, precision_at_k
from api.ai.lead_model.versions.v0_regula_zrodla.model import ModelRegulaZrodla
from api.ai.lead_model.versions.v1_llm_zero_shot.model import ModelLLMZeroShot
from api.contexts_boundaries.leasing_bc.zalozenia import koszt_na_1000_zapytan
from pomocnicze_llm import SerwerOpenAI
from pomocnicze_llm import klient as _klient

WARSZAWA = dt.timezone(dt.timedelta(hours=1))


def _leady(n: int = 1, **nadpisz) -> pd.DataFrame:
    wiersz = {
        "id_leada": "L1",
        "utworzono": pd.Timestamp("2025-03-05 10:00", tz="Europe/Warsaw"),
        "zrodlo": "www",
        "miasto": "Łódź",
        "linia_pref": "B2C",
        "budzet_max": 2400,
        "termin_wprowadzenia": pd.Timestamp("2025-04-01"),
        "liczba_osob": 2,
        "zwierze": None,
        "liczba_lokali": None,
        "wiadomosc": "Szukam mieszkania. Pozdrawiam, Ala",
        "imie": "Ala",
    }
    df = pd.DataFrame([{**wiersz, "id_leada": f"L{i}"} for i in range(n)])
    for k, v in nadpisz.items():
        df[k] = v
    return df


# --- metryki rankingu ------------------------------------------------------------------------------------------

Y = [1, 0, 1, 0, 0]
WYNIK = [0.9, 0.8, 0.5, 0.5, 0.1]


@pytest.mark.parametrize("k, oczekiwana", [(1, 1.0), (2, 0.5), (3, 0.5), (4, 0.5), (5, 0.4)])
def test_precision_at_k_przy_remisie_liczy_wartosc_oczekiwana_losowej_kolejnosci(k, oczekiwana):
    # k=3: pewne L0, L1 (1 umowa) + 1 z 2 remisujących po 0,5 (średnio 0,5 umowy) -> 1,5 / 3
    assert precision_at_k(Y, WYNIK, k) == pytest.approx(oczekiwana)


def test_lift_to_precyzja_czolowki_przez_konwersje_wszystkich():
    # 40% z 5 = 2 zapytania: precyzja 0,5, konwersja 2/5 = 0,4 -> lift 1,25
    assert lift_at(Y, WYNIK, frakcja=0.4) == pytest.approx(1.25)


def test_staly_wynik_daje_lift_1_i_auc_0_5():
    m = metryki_rankingu(np.array([1, 0, 0, 1, 0, 0, 0, 0, 0, 0]), np.full(10, 0.3), k=3)
    assert m["lift_10"] == pytest.approx(1.0)
    assert m["auc"] == pytest.approx(0.5)
    assert m["precision_k"] == pytest.approx(0.2)
    assert (m["n"], m["umowy"], m["k"]) == (10, 2, 3)


def test_dzienna_liczba_zapytan_to_srednia_na_dzien_kalendarzowy_w_czasie_warszawskim():
    utworzono = pd.Series(
        pd.to_datetime(
            ["2025-03-03 23:30+01:00", "2025-03-03 22:59+00:00", "2025-03-04 08:00+01:00", "2025-03-04 09:00+01:00"],
            utc=True,
        )
    )
    # 22:59 UTC = 23:59 w Warszawie (3 marca) -> 2 dni po 2 zapytania
    assert dzienna_liczba_zapytan(utworzono) == 2


# --- kontrakt --------------------------------------------------------------------------------------------------


def test_kontrakt_wymaga_kolumn_znanych_przy_utworzeniu_zapytania():
    with pytest.raises(ValueError, match="wiadomosc"):
        ModelLeadow.sprawdz_kolumny(_leady().drop(columns=["wiadomosc"]))


def test_kontrakt_nie_zawiera_stanu_na_dzien_eksportu():
    assert not set(KOLUMNY_WEJSCIA) & {"status", "data_statusu", "powod_utraty", "id_doradcy", "id_umowy", "jezyk"}


# --- v0: konwersja źródło × linia ------------------------------------------------------------------------------


@pytest.fixture
def v0():
    historia = pd.DataFrame(
        {
            "zrodlo": ["www", "www", "www", "www", "www", "social", "social"],
            "linia_pref": ["B2C", "B2C", "B2C", "B2C", "MID", "B2C", "B2C"],
        }
    )
    y = pd.Series([1, 1, 0, 0, 1, 0, 0])
    return ModelRegulaZrodla().fit(historia, y)


def test_v0_wynik_to_konwersja_pary_zrodlo_linia(v0):
    leady = pd.concat([_leady(), _leady(linia_pref="MID"), _leady(zrodlo="social")], ignore_index=True)
    assert list(v0.predict(leady)) == pytest.approx([0.5, 1.0, 0.0])


def test_v0_nieznana_para_dostaje_konwersje_zrodla_a_nieznane_zrodlo_konwersje_ogolna(v0):
    leady = pd.concat([_leady(linia_pref="B2B"), _leady(zrodlo="polecenie")], ignore_index=True)
    # www: 3 z 5; wszystkie: 3 z 7
    assert list(v0.predict(leady)) == pytest.approx([3 / 5, 3 / 7])
    assert list(v0.explain(leady)["poziom"]) == ["zrodlo", "ogolna"]


# --- v1: ocena LLM / 10 ----------------------------------------------------------------------------------------


def test_v1_wynik_to_ocena_podzielona_przez_10(tmp_path):
    serwer = SerwerOpenAI(dane={"ocena": 7, "uzasadnienie": "Konkretne pytania.", "sygnaly": ["konkretne_pytania"]})
    model = ModelLLMZeroShot(klient=_klient(serwer, tmp_path))
    assert list(model.predict(_leady(2))) == pytest.approx([0.7, 0.7])


def test_v1_wysyla_opis_bez_imienia_i_zapisuje_tokeny(tmp_path):
    serwer = SerwerOpenAI(dane={"ocena": 4, "uzasadnienie": "Ogólne.", "sygnaly": []}, tokeny_z_cache=3)
    wyjasnienie = ModelLLMZeroShot(klient=_klient(serwer, tmp_path)).explain(_leady())

    assert "Ala" not in serwer.zadania[0]["input"]
    assert "linia: B2C" in serwer.zadania[0]["input"]
    w = wyjasnienie.iloc[0]
    assert (w["ocena"], w["tokeny_wejscia"], w["tokeny_wejscia_z_cache"], w["tokeny_wyjscia"]) == (4, 10, 3, 5)


def test_v1_blad_wywolania_daje_brak_wyniku_a_nie_przerwanie(tmp_path):
    serwer = SerwerOpenAI(dane={"ocena": 4, "uzasadnienie": "Ogólne.", "sygnaly": []}, blad_dla="awaria")
    leady = pd.concat([_leady(), _leady(wiadomosc="awaria")], ignore_index=True)
    wyjasnienie = ModelLLMZeroShot(klient=_klient(serwer, tmp_path)).explain(leady)
    assert wyjasnienie["wynik"].isna().tolist() == [False, True]
    assert wyjasnienie["blad"].notna().tolist() == [False, True]


def test_v1_zapisany_model_nie_zawiera_klienta_api(tmp_path):
    serwer = SerwerOpenAI(dane={"ocena": 4, "uzasadnienie": "Ogólne.", "sygnaly": []})
    model = ModelLLMZeroShot(klient=_klient(serwer, tmp_path))
    model.zapisz(tmp_path / "model.joblib")
    wczytany = ModelLeadow.wczytaj(tmp_path / "model.joblib")
    assert wczytany.nazwa_promptu == "ocena_leada_v1"
    assert wczytany._klient is None
    assert joblib.load(tmp_path / "model.joblib").wersja == "v1_llm_zero_shot"


# --- koszt z cennika -------------------------------------------------------------------------------------------

CENNIK = {
    "waluta": "USD",
    "wejscie_za_1m_tokenow": 2.0,
    "wejscie_z_cache_za_1m_tokenow": 0.5,
    "wyjscie_za_1m_tokenow": 8.0,
}


def test_koszt_na_1000_zapytan_rozdziela_wejscie_z_cache_i_bez():
    # 1 000 zapytań: 2 mln wejścia, w tym 1 mln z cache, 0,5 mln wyjścia, na 2 000 zapytań
    koszt = koszt_na_1000_zapytan(4_000_000, 2_000_000, 1_000_000, 2_000, CENNIK)
    assert koszt == pytest.approx(1.0 * 2.0 + 1.0 * 0.5 + 0.5 * 8.0)


def test_bez_cennika_koszt_jest_nieznany():
    assert koszt_na_1000_zapytan(1, 0, 1, 1, {**CENNIK, "wyjscie_za_1m_tokenow": None}) is None


# --- zbiór: wejście z crm_leady + cel z leady_cel --------------------------------------------------------------


def test_zbior_laczy_wejscie_z_celem_i_nie_zawiera_stanu_na_eksport():
    import duckdb
    from api.ai.features.leady.zbior import wczytaj_zbior

    con = duckdb.connect()
    con.execute(
        "CREATE TABLE crm_leady AS SELECT 'L1' AS id_leada, TIMESTAMPTZ '2025-03-05 10:00:00+01' AS utworzono, "
        "'www' AS zrodlo, 'Łódź' AS miasto, 'B2C' AS linia_pref, 2400 AS budzet_max, NULL::TIMESTAMP AS "
        "termin_wprowadzenia, 2 AS liczba_osob, NULL::BOOLEAN AS zwierze, NULL::BIGINT AS liczba_lokali, "
        "'Dzień dobry' AS wiadomosc, 'Ala' AS imie, 'pl' AS jezyk, 'umowa' AS status, 'U1' AS id_umowy"
    )
    con.execute(
        "CREATE TABLE leady_cel AS SELECT 'L1' AS id_leada, 1 AS umowa_45d, TRUE AS okno_migracji, "
        "FALSE AS cenzurowany, TRUE AS obsluzony, TRUE AS zamkniety"
    )
    zbior = wczytaj_zbior(con)

    assert set(KOLUMNY_WEJSCIA) <= set(zbior.columns)
    assert not set(zbior.columns) & {"jezyk", "status", "id_umowy"}
    flagi = ["umowa_45d", "okno_migracji", "cenzurowany", "obsluzony", "zamkniety"]
    assert zbior.loc[0, flagi].tolist() == [1, True, False, True, True]


# --- v2_lgbm_naiwny ---------------------------------------------------------------------------------------------


def _cechy_v2(n: int = 4000, ziarno: int = 0) -> tuple[pd.DataFrame, np.ndarray]:
    from api.ai.features.leady.cechy import KOLUMNY_CECH

    rng = np.random.default_rng(ziarno)
    df = pd.DataFrame({k: rng.integers(0, 3, n).astype(float) for k in KOLUMNY_CECH})
    df["zrodlo"] = rng.choice(["www", "domteraz", "polecenie"], n)
    df["miasto"] = rng.choice(["Łódź", "Kraków"], n)
    df["linia"] = rng.choice(["B2C", "MID"], n)
    df["utworzono"] = pd.date_range("2024-01-01", "2026-02-28", periods=n, tz="Europe/Warsaw")
    df["id_leada"] = [f"L{i}" for i in range(n)]
    logit = -2.5 + 1.5 * (df["zrodlo"] == "polecenie") + 0.8 * df["www_spacer_3d"]
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df, y


@pytest.fixture(scope="module")
def v2_wyuczony():
    from api.ai.lead_model.versions.v2_lgbm_naiwny.model import ModelLGBMNaiwny

    X, y = _cechy_v2()
    return ModelLGBMNaiwny(parametry={"num_threads": 1}).fit(X, y), X, y


def test_v2_uczy_sie_sygnalu_i_zwraca_prawdopodobienstwo(v2_wyuczony):
    from sklearn.metrics import roc_auc_score

    model, X, y = v2_wyuczony
    wynik = model.predict(X)
    assert wynik.shape == (len(X),) and ((wynik > 0) & (wynik < 1)).all()
    assert roc_auc_score(y, wynik) > 0.6
    assert model.liczba_drzew_ >= 1


def test_v2_wymaga_cech_z_features_leady(v2_wyuczony):
    model, X, _ = v2_wyuczony
    with pytest.raises(ValueError, match="www_spacer_3d"):
        model.predict(X.drop(columns=["www_spacer_3d"]))


def test_v2_nieznana_kategoria_nie_przerywa_predykcji(v2_wyuczony):
    model, X, _ = v2_wyuczony
    wynik = model.predict(X.head(3).assign(zrodlo="nowe_zrodlo"))
    assert np.isfinite(wynik).all()


def test_v2_wklady_sumuja_sie_do_log_szansy(v2_wyuczony):
    model, X, _ = v2_wyuczony
    wyj = model.explain(X.head(20))
    logit = wyj.filter(like="wklad_").sum(axis=1)
    assert np.allclose(1 / (1 + np.exp(-logit)), wyj["wynik"])


def test_v2_zapis_i_odczyt_daje_ten_sam_wynik(v2_wyuczony, tmp_path):
    model, X, _ = v2_wyuczony
    model.zapisz(tmp_path / "model.joblib")
    assert np.allclose(ModelLeadow.wczytaj(tmp_path / "model.joblib").predict(X.head(50)), model.predict(X.head(50)))


def test_target_treningu_v2_nieobsluzone_to_zero():
    from api.ai.lead_model.evals.ewaluacja_v2 import target_treningu

    tr = pd.DataFrame({"umowa_45d": [1, 1, 0, 0], "obsluzony": [True, False, True, False]})
    assert list(target_treningu(tr)) == [1, 0, 0, 0]
