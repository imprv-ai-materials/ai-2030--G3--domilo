import pandas as pd
import pytest
from api.contexts_boundaries.maintenance_bc.alarmy_wind import (
    PODZESPOLY_Z_SYGNALEM,
    moment,
    ocen_alarmy,
    wczytaj_zalozenia,
    wybierz_alarmy,
)

PON = pd.Timestamp("2026-03-02")  # poniedziałek
TYDZ = pd.Timedelta(days=7)


def _ryzyko(dni: list[pd.Timestamp], ryzyka: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [(w, d, r) for w, rr in ryzyka.items() for d, r in zip(dni, rr, strict=True)],
        columns=["id_windy", "dzien", "ryzyko"],
    )


def test_zalozenia_od_uzytkownika():
    z = wczytaj_zalozenia()
    assert (z["alarmy_na_tydzien"], z["dzien_alarmu"], z["przerwa_dni"]) == (3, 0, 7)


def test_tylko_poniedzialki_i_limit():
    dni = [PON + pd.Timedelta(days=i) for i in range(7)]
    r = _ryzyko(dni, {f"W{i}": [0.1 * i] * 7 for i in range(6)})
    a = wybierz_alarmy(r, limit=3, przerwa_dni=7)
    assert set(a["dzien"]) == {PON}
    assert list(a["id_windy"]) == ["W5", "W4", "W3"]
    assert list(a["pozycja"]) == [1, 2, 3]


def test_przerwa_blokuje_nastepny_poniedzialek():
    dni = [PON, PON + TYDZ, PON + 2 * TYDZ]
    r = _ryzyko(dni, {"A": [0.9, 0.9, 0.9], "B": [0.5, 0.5, 0.5], "C": [0.1, 0.1, 0.1]})
    a = wybierz_alarmy(r, limit=1, przerwa_dni=7)
    assert list(a["id_windy"]) == ["A", "B", "A"]  # A zablokowana w t+7, wraca w t+14
    bez = wybierz_alarmy(r, limit=1, przerwa_dni=0)
    assert list(bez["id_windy"]) == ["A", "A", "A"]


def test_brak_wiersza_to_brak_alarmu_i_remis_po_id():
    # winda stojąca o 06:00 nie ma wiersza w dni_wind, więc nie może dostać alarmu
    r = _ryzyko([PON], {"B": [0.5], "A": [0.5], "C": [0.4]})
    a = wybierz_alarmy(r, limit=2, przerwa_dni=7)
    assert list(a["id_windy"]) == ["A", "B"]


def test_moment_0600_warszawa_i_zmiana_czasu():
    assert str(moment(pd.Timestamp("2026-03-23"))) == "2026-03-23 06:00:00+01:00"
    assert str(moment(pd.Timestamp("2026-03-30"))) == "2026-03-30 06:00:00+02:00"


def test_ocena_precyzja_czulosc_wyprzedzenie():
    alarmy = pd.DataFrame(
        {"dzien": [PON, PON, PON + TYDZ], "pozycja": [1, 2, 1], "id_windy": ["A", "B", "A"], "ryzyko": [0.9] * 3}
    )
    start = moment(PON)
    awarie = pd.DataFrame(
        {
            "id_awarii": ["a1", "a2", "a3", "a4", "a5"],
            "id_windy": ["A", "C", "A", "B", "A"],
            "podzespol": ["drzwi", "naped", "zewnetrzna", "sterownik", "brak"],
            "start_tz": [
                start + pd.Timedelta(hours=10),  # A złapana alarmem PON (10 h)
                start + pd.Timedelta(hours=20),  # C bez alarmu
                start + TYDZ,  # A dokładnie o 06:00 t+7: należy do okna PON (domknięte), nie PON+7
                start + TYDZ + pd.Timedelta(hours=1),  # B w drugim tygodniu, alarm B był w pierwszym
                start + 2 * TYDZ + pd.Timedelta(hours=1),  # poza zakresem (ostatnie okno kończy się w t+14)
            ],
        }
    )
    w = ocen_alarmy(alarmy, awarie, poniedzialki=[PON, PON + TYDZ])
    o = w["ogolem"]
    assert o["alarmy"] == 3 and o["trafne"] == 1  # alarm A w PON trafny; B w PON i A w PON+7 nie
    assert o["precyzja"] == pytest.approx(1 / 3)
    assert o["awarie"] == 4 and o["zlapane"] == 2  # a1 i a3 w oknie alarmu A z PON
    assert o["awarie_sygnal"] == 3 and o["zlapane_sygnal"] == 1  # a1 (drzwi), a2 (naped), a4 (sterownik)
    assert o["mediana_wyprzedzenia_h"] == pytest.approx(10.0)
    t = w["tygodnie"].set_index("tydzien")
    assert t.loc[PON, "awarie"] == 3 and t.loc[PON + TYDZ, "awarie"] == 1
    assert t.loc[PON, "trafne"] == 1 and t.loc[PON + TYDZ, "trafne"] == 0
    assert set(PODZESPOLY_Z_SYGNALEM) == {"drzwi", "naped", "hamulec_liny", "sterownik"}
