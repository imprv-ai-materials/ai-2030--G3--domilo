import duckdb
import pytest
from api.ai.features.leady.leady_cel import TABELA, leady_cel, zbuduj_leady_cel

# Czas CRM jest w bazie jako TIMESTAMPTZ; wartości poniżej z jawnym przesunięciem (Europe/Warsaw).
# (id_leada, utworzono, zrodlo, id_umowy)
LEADY = [
    ("L_umowa_10d", "2025-06-01 10:00:00+02", "www", "U1"),
    ("L_umowa_dokladnie_45d", "2025-06-01 10:00:00+02", "www", "U2"),
    ("L_umowa_45d_i_minuta", "2025-06-01 10:00:00+02", "www", "U3"),
    ("L_umowa_tylko_pms", "2025-06-01 10:00:00+02", "www", "U4"),
    ("L_utracony", "2025-06-01 10:00:00+02", "lokum24", None),
    ("L_mlody_z_umowa", "2026-08-20 12:00:00+02", "www", "U5"),
    ("L_granica_45d", "2026-08-17 00:00:00+02", "www", None),
    ("L_granica_45d_i_minuta", "2026-08-17 00:01:00+02", "www", None),
    ("L_w_toku_dlugo", "2026-05-20 09:00:00+02", "social", None),
    ("L_w_toku_krotko", "2026-07-25 09:00:00+02", "social", None),
    ("L_okno_od", "2025-03-03 00:00:00+01", "www", None),
    ("L_przed_oknem", "2025-03-02 23:59:00+01", "www", None),
    ("L_okno_do", "2025-04-13 23:59:00+02", "www", None),
    ("L_po_oknie", "2025-04-14 00:00:00+02", "www", None),
]

# (id_leada, data_czas, status_z, status_na)
HISTORIA = [
    ("L_umowa_10d", "2025-06-01 10:00:00+02", None, "otwarty"),
    ("L_umowa_10d", "2025-06-02 10:00:00+02", "otwarty", "w_toku"),
    ("L_umowa_10d", "2025-06-11 10:00:00+02", "w_toku", "umowa"),
    ("L_umowa_dokladnie_45d", "2025-06-01 10:00:00+02", None, "otwarty"),
    ("L_umowa_dokladnie_45d", "2025-07-16 10:00:00+02", "otwarty", "umowa"),
    ("L_umowa_45d_i_minuta", "2025-06-01 10:00:00+02", None, "otwarty"),
    ("L_umowa_45d_i_minuta", "2025-07-16 10:01:00+02", "otwarty", "umowa"),
    ("L_umowa_tylko_pms", "2025-06-01 10:00:00+02", None, "otwarty"),
    ("L_utracony", "2025-06-01 10:00:00+02", None, "otwarty"),
    ("L_utracony", "2025-06-05 10:00:00+02", "otwarty", "utracony"),
    ("L_mlody_z_umowa", "2026-08-20 12:00:00+02", None, "otwarty"),
    ("L_mlody_z_umowa", "2026-08-25 12:00:00+02", "otwarty", "umowa"),
    ("L_granica_45d", "2026-08-17 00:00:00+02", None, "otwarty"),
    ("L_granica_45d_i_minuta", "2026-08-17 00:01:00+02", None, "otwarty"),
    ("L_w_toku_dlugo", "2026-05-20 09:00:00+02", None, "otwarty"),
    ("L_w_toku_dlugo", "2026-05-21 09:00:00+02", "otwarty", "w_toku"),
    ("L_w_toku_krotko", "2026-07-25 09:00:00+02", None, "otwarty"),
    ("L_w_toku_krotko", "2026-07-26 09:00:00+02", "otwarty", "w_toku"),
    ("L_okno_od", "2025-03-03 00:00:00+01", None, "otwarty"),
    ("L_przed_oknem", "2025-03-02 23:59:00+01", None, "otwarty"),
    ("L_okno_do", "2025-04-13 23:59:00+02", None, "otwarty"),
    ("L_po_oknie", "2025-04-14 00:00:00+02", None, "otwarty"),
]

# (id_aktywnosci, id_leada, id_doradcy, data_czas, typ, wynik)
AKTYWNOSCI = [
    ("A1", "L_umowa_10d", "D01", "2025-06-02 09:00:00+02", "telefon_wych", "nieodebrany"),
    ("A2", "L_umowa_10d", "D01", "2025-06-11 10:00:00+02", "email", "podpisanie"),
    ("A3", "L_umowa_dokladnie_45d", "D02", "2025-07-16 10:00:00+02", "email", "podpisanie"),
    ("A4", "L_okno_od", "CC", "2025-03-03 08:00:00+01", "telefon_wych", "rozmowa"),
    ("A5", "L_utracony", "D03", "2025-07-20 10:00:00+02", "telefon_wych", "rozmowa"),
]

# (id_umowy, data_podpisania)
UMOWY = [
    ("U1", "2025-06-11"),
    ("U2", "2025-07-16"),
    ("U3", "2025-07-16"),
    ("U4", "2025-06-20"),
    ("U5", "2026-08-25"),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'Europe/Warsaw'")
    con.execute(
        "CREATE TABLE crm_leady (id_leada VARCHAR, utworzono TIMESTAMPTZ, zrodlo VARCHAR, id_umowy VARCHAR, "
        "status VARCHAR)"
    )
    # crm_leady.status celowo kłamie (stan na eksport ≠ historia): wynik nie może od niego zależeć.
    con.executemany("INSERT INTO crm_leady VALUES (?, ?, ?, ?, 'umowa')", LEADY)
    con.execute(
        "CREATE TABLE crm_historia_statusow (id_leada VARCHAR, data_czas TIMESTAMPTZ, status_z VARCHAR, "
        "status_na VARCHAR, id_doradcy VARCHAR)"
    )
    con.executemany("INSERT INTO crm_historia_statusow VALUES (?, ?, ?, ?, 'D01')", HISTORIA)
    con.execute(
        "CREATE TABLE crm_aktywnosci (id_aktywnosci VARCHAR, id_leada VARCHAR, id_doradcy VARCHAR, "
        "data_czas TIMESTAMPTZ, typ VARCHAR, wynik VARCHAR)"
    )
    con.executemany("INSERT INTO crm_aktywnosci VALUES (?, ?, ?, ?, ?, ?)", AKTYWNOSCI)
    con.execute("CREATE TABLE pms_umowy (id_umowy VARCHAR, data_podpisania TIMESTAMP)")
    con.executemany("INSERT INTO pms_umowy VALUES (?, ?)", UMOWY)
    yield con
    con.close()


def _kolumna(con, kolumna):
    return dict(leady_cel(con).select(f"id_leada, {kolumna}").fetchall())


def test_jeden_wiersz_na_zapytanie(con):
    assert sorted(_kolumna(con, "1")) == sorted(id_ for id_, *_ in LEADY)


@pytest.mark.parametrize(
    "id_leada, oczekiwane",
    [
        ("L_umowa_10d", 1),
        ("L_umowa_dokladnie_45d", 1),
        ("L_umowa_45d_i_minuta", 0),
        ("L_umowa_tylko_pms", 1),
        ("L_utracony", 0),
        ("L_w_toku_dlugo", 0),
        ("L_granica_45d", 0),
    ],
)
def test_umowa_45d_to_umowa_najpozniej_45_dni_po_utworzeniu(con, id_leada, oczekiwane):
    assert _kolumna(con, "umowa_45d")[id_leada] == oczekiwane


@pytest.mark.parametrize(
    "id_leada, cenzurowany",
    [
        ("L_mlody_z_umowa", True),
        ("L_granica_45d_i_minuta", True),
        ("L_w_toku_krotko", False),
        ("L_granica_45d", False),
        ("L_umowa_10d", False),
    ],
)
def test_zapytanie_mlodsze_niz_45_dni_w_dniu_eksportu_jest_cenzurowane(con, id_leada, cenzurowany):
    wynik = dict(leady_cel(con).select("id_leada, (cenzurowany, umowa_45d IS NULL)").fetchall())
    assert wynik[id_leada] == (cenzurowany, cenzurowany)


@pytest.mark.parametrize(
    "id_leada, status_koncowy, zamkniety",
    [
        ("L_umowa_10d", "umowa", True),
        ("L_utracony", "utracony", True),
        ("L_w_toku_dlugo", "utracony", True),
        ("L_w_toku_krotko", "w_toku", False),
        ("L_granica_45d", "otwarty", False),
    ],
)
def test_status_koncowy_z_historii_a_w_toku_ponad_90_dni_to_utracony(con, id_leada, status_koncowy, zamkniety):
    wynik = dict(leady_cel(con).select("id_leada, (status_koncowy, zamkniety)").fetchall())
    assert wynik[id_leada] == (status_koncowy, zamkniety)


def test_utrata_po_90_dniach_w_toku_ma_date_zamkniecia_90_dni_po_wejsciu_w_w_toku(con):
    wynik = dict(leady_cel(con).select("id_leada, strftime(data_zamkniecia, '%Y-%m-%d %H:%M')").fetchall())
    assert wynik["L_w_toku_dlugo"] == "2026-08-19 09:00"


@pytest.mark.parametrize(
    "id_leada, obsluzony, obsluzony_cc",
    [
        ("L_umowa_10d", True, False),
        ("L_umowa_dokladnie_45d", False, False),  # samo podpisanie to wynik, nie obsługa
        ("L_okno_od", True, True),
        ("L_utracony", False, False),  # kontakt dopiero po 45 dniach od utworzenia
        ("L_po_oknie", False, False),
    ],
)
def test_obsluzony_to_kontakt_doradcy_lub_call_center_w_45_dniach(con, id_leada, obsluzony, obsluzony_cc):
    wynik = dict(leady_cel(con).select("id_leada, (obsluzony, obsluzony_cc)").fetchall())
    assert wynik[id_leada] == (obsluzony, obsluzony_cc)


@pytest.mark.parametrize(
    "id_leada, w_oknie",
    [("L_przed_oknem", False), ("L_okno_od", True), ("L_okno_do", True), ("L_po_oknie", False)],
)
def test_okno_migracji_obejmuje_dni_od_3_marca_do_13_kwietnia_2025(con, id_leada, w_oknie):
    assert _kolumna(con, "okno_migracji")[id_leada] is w_oknie


def test_zbuduj_tworzy_tabele_w_bazie(con):
    assert zbuduj_leady_cel(con) == len(LEADY)
    assert con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0] == len(LEADY)


def test_remis_czasu_w_historii_rozstrzyga_kolejnosc_statusow(con):
    # W danych dwa leady mają przejścia otwarty->w_toku i w_toku->umowa z tym samym czasem.
    # Kolejność wierszy w tabeli nie może decydować: 'w_toku' jest przed statusem końcowym.
    con.execute("INSERT INTO crm_leady VALUES ('L_remis', '2025-06-01 10:00:00+02', 'www', NULL, 'umowa')")
    con.executemany(
        "INSERT INTO crm_historia_statusow VALUES ('L_remis', ?, ?, ?, 'D01')",
        [
            ("2025-06-03 10:00:00+02", "w_toku", "utracony"),
            ("2025-06-03 10:00:00+02", "otwarty", "w_toku"),
            ("2025-06-01 10:00:00+02", None, "otwarty"),
        ],
    )
    wynik = dict(
        leady_cel(con)
        .select("id_leada, (status_koncowy, utracony_90d, strftime(data_zamkniecia, '%Y-%m-%d'))")
        .fetchall()
    )
    assert wynik["L_remis"] == ("utracony", False, "2025-06-03")
