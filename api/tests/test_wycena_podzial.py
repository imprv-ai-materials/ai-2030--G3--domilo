import duckdb
import pytest
from api.ai.features.wycena.podzial import ZBIORY, podzial

# (id, data_aktu, data_publikacji_rejestru, oczekiwany zbiór; None = poza podziałem)
PRZYPADKI = [
    ("T_przed", "2022-12-31 23:59:59", "2023-03-01", None),
    ("T_tr_od", "2023-01-01 00:00:00", "2023-03-02", "trening"),
    ("T_tr_do", "2025-06-30 23:59:59", "2025-09-01", "trening"),
    ("T_wal_od", "2025-07-01 00:00:00", "2025-09-01", "walidacja"),
    ("T_wal_do", "2025-12-31 00:00:00", "2026-03-01", "walidacja"),
    ("T_test_od", "2026-01-01 00:00:00", "2026-03-01", "test"),
    ("T_test_do", "2026-06-30 00:00:00", "2026-09-30", "test"),
    ("T_test_po_eksporcie", "2026-06-30 00:00:00", "2026-10-01", None),
    ("T_po", "2026-07-01 00:00:00", "2026-09-15", None),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE rcn_transakcje (id_transakcji VARCHAR, data_aktu TIMESTAMP, data_publikacji_rejestru TIMESTAMP)"
    )
    con.executemany("INSERT INTO rcn_transakcje VALUES (?, ?, ?)", [p[:3] for p in PRZYPADKI])
    yield con
    con.close()


def test_kazda_transakcja_trafia_do_zbioru_wedlug_daty_aktu_a_nieznane_w_dniu_eksportu_odpadaja(con):
    wynik = dict(podzial(con).select("id_transakcji, zbior").fetchall())
    oczekiwane = {id_: zbior for id_, _, _, zbior in PRZYPADKI if zbior is not None}
    assert wynik == oczekiwane


def test_zbiory_sa_w_kolejnosci_czasu():
    assert ZBIORY == ("trening", "walidacja", "test")
