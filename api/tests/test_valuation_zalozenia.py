from api.contexts_boundaries.valuation_bc.zalozenia import SCIEZKA_ZALOZEN, bez_odpowiedzialnego, wczytaj_zalozenia


def test_zalozenia_wyceny_maja_wartosci_od_uzytkownika():
    z = wczytaj_zalozenia()
    assert z["koszt_operatu_pln"]["wartosc"] == 450
    assert z["koszt_wyceny_wewnetrznej_pln"]["wartosc"] == 150
    assert z["probka_kontrolna_lokali"]["wartosc"] == 300
    assert z["bank_mape_max_proc"]["wartosc"] == 8
    assert z["bank_przedzial_poziom"]["wartosc"] == 0.8
    assert (z["bank_pokrycie_min_proc"]["wartosc"], z["bank_pokrycie_max_proc"]["wartosc"]) == (77, 83)


def test_kazda_liczba_ma_zrodlo_i_pole_odpowiedzialny():
    for nazwa, pozycja in wczytaj_zalozenia().items():
        assert {"wartosc", "opis", "zrodlo", "odpowiedzialny"} <= set(pozycja), nazwa
        assert pozycja["zrodlo"], nazwa


def test_bez_odpowiedzialnego_wypisuje_pozycje_z_pustym_polem(tmp_path):
    plik = tmp_path / "z.yaml"
    plik.write_text(
        "a:\n  wartosc: 1\n  opis: x\n  zrodlo: y\n  odpowiedzialny: null\n"
        "b:\n  wartosc: 2\n  opis: x\n  zrodlo: y\n  odpowiedzialny: Jan Kowalski (CFO)\n",
        encoding="utf-8",
    )
    assert bez_odpowiedzialnego(wczytaj_zalozenia(plik)) == ["a"]
    assert SCIEZKA_ZALOZEN.name == "zalozenia.yaml"
