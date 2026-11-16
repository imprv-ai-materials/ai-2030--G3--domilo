"""Oferta retencyjna dla jednego najmu (część `oferta` w GET /risk/{id_najmu}): uplift, EV i zalecana akcja.

Model: v3_uplift_tlearner (churn_model/versions/v3_uplift_tlearner): P(przedłuży | oferta), P(przedłuży | bez
oferty), uplift = różnica. Wartość oczekiwana: EV = uplift × R − D × P(przedłuży | oferta) − k (R, D, k z
retention_bc/zalozenia.yaml, podane przez użytkownika; polityka_rabatow.wartosc_oferty).

Dzień decyzji (cechy v1 liczone tylko ze zdarzeń sprzed niego, jak w migawkach, na których uczono v3):
migawka = koniec bieżącego okresu − 60 dni, a gdy migawka jest jeszcze w przyszłości, dzień oceny (stan na dziś).

Zalecana akcja (kolejność sprawdzania):
0. cechy poza zakresem danych uczących v3 (ModelUpliftT.poza_zakresem: brak, którego w treningu nie było, albo
   wartość poza [min, max] treningu, np. najem krótszy niż najkrótszy w treningu): „bez rabatu” z uzasadnieniem
   „zalecenie w dniu migawki” — model uczono tylko na migawkach, więc dla takich najmów nie zgadujemy upliftu;
1. „nie budzić”: uplift <= PROG_NIE_BUDZIC (oferta wyraźnie obniża szansę przedłużenia);
2. „rabat”: EV > 0 i oferta mieści się w rocznym budżecie rabatów (budżet nieustalony = bez limitu, z adnotacją);
3. „bez rabatu”: pozostałe.
PROG_NIE_BUDZIC = 20. percentyl przewidywanego upliftu v3 na zbiorze oceny (część testowa test_2025,
retention_bc/wyniki/ev_najemcow.parquet; pilnuje test_oferta_najmu). Decyzja wykonawcy, do potwierdzenia: „wyraźnie
ujemny” nie ma liczby od użytkownika. W tej grupie oferta faktycznie obniżyła przedłużenia z 57,7% (130 umów
kontrolnych) do 47,7% (153 umowy z ofertą); różnica nie jest istotna statystycznie (churn_model/evals/uplift.md).
Budżet: umowy aktywnych najmów kończące się w ciągu 365 dni od dnia oceny, z EV > 0, w kolejności malejącego EV;
oferta mieści się, gdy suma spodziewanych kosztów rabatu (D × P(przedłuży | oferta)) do niej włącznie <= budżet.
Uzasadnienie: jedno zdanie z trzema cechami o największym wkładzie w uplift (ModelUpliftT.wklady_upliftu, SHAP
przeliczony na punkty procentowe), w kierunku zgodnym z akcją.
"""

import math
from datetime import date, timedelta
from pathlib import Path

import joblib
import pandas as pd
from api.ai.churn_model.versions.v3_uplift_tlearner.model import ModelUpliftT, macierz
from api.ai.features.najemcy.cechy_okresow import cechy_okresow, okresy_umow
from api.contexts_boundaries.retention_bc.polityka_rabatow import wartosc_oferty
from api.contexts_boundaries.retention_bc.zalozenia import ZalozeniaOferty, budzet_rabatow, zalozenia_oferty

SCIEZKA_MODELU_UPLIFT = (
    Path(__file__).resolve().parents[2] / "ai" / "churn_model" / "versions" / "v3_uplift_tlearner" / "model.joblib"
)
DNI_MIGAWKI = 60
PROG_NIE_BUDZIC = -0.0643  # 20. percentyl upliftu v3 na zbiorze oceny (wyniki/ev_najemcow.parquet)
HORYZONT_BUDZETU_DNI = 365
AKCJE = ("rabat", "bez rabatu", "nie budzić")
UWAGI_STALE = (
    "Uplift i szanse przedłużenia z modelu v3_uplift_tlearner: na teście nie był lepszy od reguły „górne 35% "
    "score_polityki” i zawyża skrajne wartości (najwyższy kwintyl: przewidywane +22,2 p.p., obserwowane +11,4 p.p.; "
    "churn_model/evals/uplift.md).",
    "Próg „nie budzić” (uplift <= −6,43 p.p.) to 20. percentyl upliftu v3 na zbiorze oceny; decyzja wykonawcy, "
    "do potwierdzenia.",
    "EV = uplift × R − D × P(przedłuży | oferta) − k; R, D, k to założenia z retention_bc/zalozenia.yaml "
    "(docs/polityka_rabatow.md).",
)


# --- opisy cech --------------------------------------------------------------------------------------------------


def _l(x: float, miejsc: int = 0) -> str:
    """Liczba po polsku: przecinek dziesiętny, spacja tysięcy, znak minus."""
    s = f"{x:,.{miejsc}f}".replace(",", " ").replace(".", ",")
    return s.replace("-", "−")


def _odm(n: float, formy: tuple[str, str, str]) -> str:
    """„1 zgłoszenie”, „2 zgłoszenia”, „5 zgłoszeń” (n całkowite)."""
    n = int(round(n))
    if n == 0:
        return f"brak {formy[2]}"
    if n == 1:
        forma = formy[0]
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        forma = formy[1]
    else:
        forma = formy[2]
    return f"{_l(n)} {forma}"


def _brak(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


OPISY = {
    "b2b": lambda v: "klient firmowy (B2B)" if v == 1 else "klient prywatny (B2C)",
    "miesiecy_umowy": lambda v: f"umowa na {_odm(v, ('miesiąc', 'miesiące', 'miesięcy'))}",
    "nr_okresu": lambda v: "pierwsza umowa" if v == 1 else f"okres umowy nr {_l(v)}",
    "staz_dni": lambda v: f"najem trwa {_l(v / 365.25, 1)} roku",
    "indeksacja_ostatnia_pct": lambda v: (
        "pierwsza umowa, bez wcześniejszej podwyżki" if _brak(v) else f"ostatnia podwyżka czynszu {_l(v, 1)}%"
    ),
    "czynsz_m2": lambda v: f"czynsz {_l(v)} zł za m²",
    "czynsz_do_podobnych": lambda v: (
        "brak porównania czynszu z podobnymi lokalami"
        if _brak(v)
        else (
            "czynsz jak w podobnych lokalach"
            if round((v - 1) * 100) == 0
            else f"czynsz o {_l(abs(round((v - 1) * 100)))}% {'wyższy' if v > 1 else 'niższy'} "
            "niż w podobnych lokalach"
        )
    ),
    "plat_liczba_90d": lambda v: f"{_odm(v, ('płatność', 'płatności', 'płatności'))} w 90 dniach",
    "plat_spoznione_90d": lambda v: (
        f"{_odm(v, ('spóźniona płatność', 'spóźnione płatności', 'spóźnionych płatności'))} w 90 dniach"
    ),
    "plat_zalegle_na_migawke": lambda v: (
        f"{_odm(v, ('niezapłacona rata', 'niezapłacone raty', 'niezapłaconych rat'))} w dniu decyzji"
    ),
    "plat_max_opoznienie_90d": lambda v: (
        "brak płatności w 90 dniach"
        if _brak(v)
        else (
            "płatności bez opóźnień w 90 dniach"
            if v == 0
            else f"najdłuższe opóźnienie płatności {_odm(v, ('dzień', 'dni', 'dni'))}"
        )
    ),
    "plat_srednie_opoznienie_90d": lambda v: (
        "brak płatności w 90 dniach"
        if _brak(v)
        else ("płatności bez opóźnień w 90 dniach" if v == 0 else f"średnie opóźnienie płatności {_l(v, 1)} dnia")
    ),
    "zgl_90d": lambda v: f"{_odm(v, ('zgłoszenie', 'zgłoszenia', 'zgłoszeń'))} w portalu w 90 dniach",
    "zgl_365d": lambda v: f"{_odm(v, ('zgłoszenie', 'zgłoszenia', 'zgłoszeń'))} w portalu w ciągu roku",
    "zgl_otwarte_na_migawke": lambda v: _odm(v, ("otwarte zgłoszenie", "otwarte zgłoszenia", "otwartych zgłoszeń")),
    "ocena_srednia_365d": lambda v: (
        "brak ocen obsługi w ciągu roku" if _brak(v) else f"średnia ocena obsługi {_l(v, 1)} na 5"
    ),
    "ocena_min_365d": lambda v: (
        "brak ocen obsługi w ciągu roku" if _brak(v) else f"najniższa ocena obsługi {_l(v)} na 5"
    ),
    "ocena_liczba_365d": lambda v: f"{_odm(v, ('ocena', 'oceny', 'ocen'))} obsługi w ciągu roku",
    "ankieta_ostatni_wynik": lambda v: (
        "brak odpowiedzi w ankiecie satysfakcji" if _brak(v) else f"ostatnia ankieta satysfakcji {_l(v)} na 10"
    ),
    "ankieta_dni_od_odpowiedzi": lambda v: (
        "brak odpowiedzi w ankiecie satysfakcji"
        if _brak(v)
        else f"ostatnia odpowiedź w ankiecie {_odm(v, ('dzień', 'dni', 'dni'))} temu"
    ),
    "ankieta_brak_wyniku": lambda v: (
        "brak odpowiedzi w ankiecie satysfakcji" if v == 1 else "jest odpowiedź w ankiecie satysfakcji"
    ),
    "ankiety_bez_odpowiedzi_365d": lambda v: (
        f"{_odm(v, ('ankieta', 'ankiety', 'ankiet'))} bez odpowiedzi w ciągu roku"
    ),
    "portal_miesiace_3m": lambda v: (
        "brak danych z portalu z 3 miesięcy" if v == 0 else f"dane z portalu z {_l(v)} z 3 ostatnich miesięcy"
    ),
    "portal_logowania_3m": lambda v: (
        "brak danych o logowaniach do portalu"
        if _brak(v)
        else f"{_odm(v, ('logowanie', 'logowania', 'logowań'))} do portalu w 3 miesiące"
    ),
    "portal_odslony_oferty_3m": lambda v: (
        "brak danych z portalu"
        if _brak(v)
        else f"{_odm(v, ('odsłona', 'odsłony', 'odsłon'))} oferty przedłużenia w portalu w 3 miesiące"
    ),
    "liczba_wind": lambda v: "budynek bez wind" if v == 0 else f"{_odm(v, ('winda', 'windy', 'wind'))} w budynku",
    "windy_awarie_90d": lambda v: f"{_odm(v, ('awaria', 'awarie', 'awarii'))} wind w budynku w 90 dniach",
    "windy_awarie_90d_na_winde": lambda v: (
        "budynek bez wind" if _brak(v) else f"{_l(v, 1)} awarii na windę w 90 dniach"
    ),
}


def opis_cechy(nazwa: str, wartosc) -> str:
    """Krótki opis cechy z wartością, bez kropek (wchodzi do jednego zdania uzasadnienia)."""
    if nazwa in OPISY:
        return OPISY[nazwa](wartosc)
    return f"{nazwa} = {'brak' if _brak(wartosc) else _l(wartosc, 1)}"


# --- decyzja -------------------------------------------------------------------------------------------------------


def data_decyzji(koniec_okresu: date, dzien_oceny: date) -> date:
    """Migawka (koniec okresu − 60 dni), a gdy jeszcze nie nastąpiła: dzień oceny."""
    return min(koniec_okresu - timedelta(days=DNI_MIGAWKI), dzien_oceny)


def zalecana_akcja(uplift: float, ev: float, w_budzecie: bool | None, prog: float = PROG_NIE_BUDZIC) -> str:
    if uplift <= prog:
        return "nie budzić"
    if ev > 0 and w_budzecie is not False:
        return "rabat"
    return "bez rabatu"


def miesci_sie_w_budzecie(ev: pd.Series, koszt: pd.Series, id_umowy: str, budzet: float | None) -> bool | None:
    """Czy oferta dla `id_umowy` mieści się w budżecie, gdy oferty (EV > 0) idą od największego EV.
    None, gdy budżetu nie ustalono."""
    if budzet is None:
        return None
    if id_umowy not in ev.index or ev[id_umowy] <= 0:
        return False
    kolejka = ev[ev > 0].sort_values(ascending=False, kind="stable")
    suma = koszt.reindex(kolejka.index).cumsum()
    return bool(suma[id_umowy] <= budzet)


def trzy_cechy(wklady: pd.Series, wartosci: pd.Series, akcja: str) -> list[dict]:
    """Trzy cechy o największym wkładzie w uplift: dla „rabat” podnoszące, dla „nie budzić” obniżające (gdy brak,
    uzupełniamy największymi |wkładami|), dla „bez rabatu” największe |wkłady|."""
    po_modulach = wklady.abs().sort_values(ascending=False, kind="stable").index.tolist()
    if akcja == "rabat":
        kierunek = wklady[wklady > 0].sort_values(ascending=False, kind="stable").index.tolist()
    elif akcja == "nie budzić":
        kierunek = wklady[wklady < 0].sort_values(ascending=True, kind="stable").index.tolist()
    else:
        kierunek = []
    wybrane = (kierunek + [c for c in po_modulach if c not in kierunek])[:3]
    return [
        {
            "cecha": c,
            "opis": opis_cechy(c, wartosci[c]),
            "wartosc": None if _brak(wartosci[c]) else float(wartosci[c]),
            "wklad_pp": round(100 * float(wklady[c]), 2),
        }
        for c in wybrane
    ]


def _lista(cechy: list[dict], z_kierunkiem: bool = False) -> str:
    opisy = [c["opis"] + ((" (podnosi)" if c["wklad_pp"] > 0 else " (obniża)") if z_kierunkiem else "") for c in cechy]
    return ", ".join(opisy[:-1]) + f" i {opisy[-1]}" if len(opisy) > 1 else opisy[0]


def uzasadnienie(
    akcja: str, uplift: float, ev: float, p_oferta: float, cechy: list[dict], w_budzecie: bool | None
) -> str:
    """Jedno zdanie (jedna kropka, na końcu) z liczbami i trzema cechami."""
    pp = _l(abs(100 * uplift), 1)
    ev_txt = f"{_l(ev)} zł"
    lista = _lista(cechy)
    if akcja == "rabat":
        budzet = "mieści się w budżecie" if w_budzecie else "budżetu rabatów jeszcze nie ustalono"
        return (
            f"Rabat: oferta podnosi szansę przedłużenia o {pp} punktu procentowego, wartość oczekiwana to {ev_txt} "
            f"({budzet}), a najbardziej podnoszą ją: {lista}."
        )
    if akcja == "nie budzić":
        return (
            f"Nie budzić: oferta obniża szansę przedłużenia o {pp} punktu procentowego (wartość oczekiwana "
            f"{ev_txt}), a najbardziej obniżają ją: {lista}."
        )
    if ev > 0 and w_budzecie is False:
        return (
            f"Bez rabatu: oferta byłaby opłacalna (wartość oczekiwana {ev_txt}), ale nie mieści się już w rocznym "
            f"budżecie rabatów; najwięcej ważą: {lista}."
        )
    zmiana = "podnosi" if uplift >= 0 else "obniża"
    return (
        f"Bez rabatu: oferta {zmiana} szansę przedłużenia tylko o {pp} punktu procentowego, a przy "
        f"{_l(100 * p_oferta)}% szansy przedłużenia z ofertą rabat kosztuje więcej, niż daje (wartość oczekiwana "
        f"{ev_txt}); najwięcej ważą: {_lista(cechy, z_kierunkiem=True)}."
    )


def uzasadnienie_poza_zakresem(poza: list[dict], migawka: date, dzien_oceny: date) -> str:
    """Jedno zdanie, gdy cechy najmu wykraczają poza dane uczące v3 (nie zgadujemy upliftu)."""
    dalej = (
        f"zalecenie policzymy w dniu migawki {migawka.isoformat()}"
        if migawka > dzien_oceny
        else "oferty nie oceniamy automatycznie"
    )
    return (
        "Bez rabatu: model jeszcze nie ocenia tego najmu, bo poza zakresem danych, na których go uczono (najmy "
        f"60 dni przed końcem umowy), są: {_lista(poza)}; {dalej}."
    )


def decyzja(
    uplift: float,
    ev: float,
    p_oferta: float,
    wklady: pd.Series,
    wartosci: pd.Series,
    poza: list[str],
    w_budzecie: bool | None,
    migawka: date,
    dzien_oceny: date,
) -> dict:
    """Akcja, trzy cechy i uzasadnienie dla jednego najmu. Cechy poza zakresem danych uczących -> „bez rabatu”."""
    if poza:
        akcja = "bez rabatu"
        cechy = trzy_cechy(wklady, wartosci, akcja)
        opisy_poza = [{"opis": opis_cechy(c, wartosci[c]), "wklad_pp": 0.0} for c in poza[:3]]
        return {
            "akcja": akcja,
            "cechy": cechy,
            "uzasadnienie": uzasadnienie_poza_zakresem(opisy_poza, migawka, dzien_oceny),
        }
    akcja = zalecana_akcja(uplift, ev, w_budzecie)
    cechy = trzy_cechy(wklady, wartosci, akcja)
    return {
        "akcja": akcja,
        "cechy": cechy,
        "uzasadnienie": uzasadnienie(akcja, uplift, ev, p_oferta, cechy, w_budzecie),
    }


# --- obliczenia na bazie -------------------------------------------------------------------------------------------


def wczytaj_model_uplift(sciezka: Path = SCIEZKA_MODELU_UPLIFT) -> ModelUpliftT:
    model = joblib.load(sciezka)
    if not isinstance(model, ModelUpliftT):
        raise TypeError(f"{sciezka} nie zawiera modelu v3_uplift_tlearner")
    return model


def oferty_okresow(
    con, okresy: pd.DataFrame, model: ModelUpliftT, z: ZalozeniaOferty, dzien_oceny: date
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Dla każdego okresu (wiersz okresy_umow): dzień decyzji, szanse, uplift, EV; do tego wkłady cech w uplift
    i wartości cech (kolumny `macierz`), indeks = id_umowy."""
    wej = okresy.copy()
    wej["data_migawki"] = [pd.Timestamp(data_decyzji(pd.Timestamp(d).date(), dzien_oceny)) for d in wej["data_do"]]
    cechy = cechy_okresow(con, wej)
    df = wej[["id_umowy", "id_najmu", "data_do", "data_migawki"]].merge(cechy, on="id_umowy", validate="1:1")
    df = df.set_index("id_umowy", drop=False)
    p_o, p_k = model.predict_skladowe(df)
    wynik = df[["id_umowy", "id_najmu", "data_do", "data_migawki"]].copy()
    wynik["p_oferta"], wynik["p_bez_oferty"] = p_o, p_k
    wynik["uplift"] = p_o - p_k
    wynik["ev"] = wartosc_oferty(wynik["uplift"], p_o, z)
    wynik["koszt_rabatu"] = z.D * p_o
    wynik["poza_zakresem"] = model.poza_zakresem(df)
    wynik["migawka"] = wynik["data_do"] - pd.Timedelta(days=DNI_MIGAWKI)
    return wynik, model.wklady_upliftu(df), macierz(df, model.cechy)


_CACHE_BUDZETU: dict = {}


def populacja_budzetu(con, model: ModelUpliftT, z: ZalozeniaOferty, dzien_oceny: date) -> pd.DataFrame:
    """Oferty dla aktywnych najmów B2C / B2B, których bieżący okres kończy się w ciągu 365 dni od dnia oceny."""
    klucz = (dzien_oceny, id(model), z)
    if klucz not in _CACHE_BUDZETU:
        okresy = okresy_umow(con, "2100-12-31")
        biezace = okresy.loc[okresy.groupby("id_najmu")["nr_okresu"].idxmax()]
        dzien = pd.Timestamp(dzien_oceny)
        aktywne = biezace[
            (biezace["data_wyprowadzenia"].isna() | (biezace["data_wyprowadzenia"] > dzien))
            & (biezace["data_do"] > dzien)
            & (biezace["data_do"] <= dzien + pd.Timedelta(days=HORYZONT_BUDZETU_DNI))
        ]
        _CACHE_BUDZETU[klucz] = oferty_okresow(con, aktywne, model, z, dzien_oceny)[0]
    return _CACHE_BUDZETU[klucz]


def oferta_najmu(
    con, biezacy: pd.DataFrame, model: ModelUpliftT, dzien_oceny: date, z: ZalozeniaOferty | None = None
) -> dict:
    """Część `oferta` odpowiedzi /risk dla bieżącego okresu najmu (jeden wiersz z okresy_umow)."""
    z = z or zalozenia_oferty()
    budzet = budzet_rabatow()
    wynik, wklady, wartosci = oferty_okresow(con, biezacy, model, z, dzien_oceny)
    w = wynik.iloc[0]
    id_umowy = str(w["id_umowy"])
    if budzet is None:
        w_budzecie = None
    else:
        pop = populacja_budzetu(con, model, z, dzien_oceny)
        w_budzecie = (
            miesci_sie_w_budzecie(pop["ev"], pop["koszt_rabatu"], id_umowy, budzet) if id_umowy in pop.index else None
        )
    uplift, ev, p_o = float(w["uplift"]), float(w["ev"]), float(w["p_oferta"])
    d = decyzja(
        uplift, ev, p_o, wklady.drop(columns="wklad_staly").iloc[0], wartosci.iloc[0], list(w["poza_zakresem"]),
        w_budzecie, pd.Timestamp(w["migawka"]).date(), dzien_oceny,
    )  # fmt: skip
    akcja, cechy = d["akcja"], d["cechy"]
    uwagi = list(UWAGI_STALE)
    if akcja == "rabat":
        uwagi.append(
            "Na zbiorze oceny 30 umów z EV > 0 według v3 nie dało dodatkowych przedłużeń (15 z ofertą, 15 bez; "
            "docs/polityka_rabatow.md): zalecenie „rabat” traktuj jako kandydata do testu, nie pewny zysk."
        )
    if budzet is None:
        uwagi.append("Budżetu rabatów nie ustalono (retention_bc/zalozenia.yaml: budzet_rabatow_rok = null).")
    elif w_budzecie is None:
        uwagi.append("Koniec okresu poza 365 dniami od dnia oceny: budżetu tego roku nie sprawdzano.")
    wypowiedzenie = con.execute(
        "SELECT wypowiedzenie_data::DATE FROM pms_najmy WHERE id_najmu = ?", [str(w["id_najmu"])]
    ).fetchone()[0]
    if wypowiedzenie is not None and wypowiedzenie <= dzien_oceny:
        uwagi.append(f"Najemca złożył wypowiedzenie {wypowiedzenie}: oferta prawdopodobnie przychodzi za późno.")
    return {
        "wersja_modelu": model.wersja,
        "id_umowy": id_umowy,
        "koniec_okresu": pd.Timestamp(w["data_do"]).date(),
        "data_decyzji": pd.Timestamp(w["data_migawki"]).date(),
        "p_przedluzy_z_oferta": p_o,
        "p_przedluzy_bez_oferty": float(w["p_bez_oferty"]),
        "uplift": uplift,
        "ev_pln": ev,
        "zalecana_akcja": akcja,
        "uzasadnienie": d["uzasadnienie"],
        "poza_zakresem_modelu": list(w["poza_zakresem"]),
        "najwazniejsze_cechy": cechy,
        "prog_nie_budzic": PROG_NIE_BUDZIC,
        "w_budzecie": w_budzecie,
        "zalozenia": {"R": z.R, "D": z.D, "k": z.k, "budzet_rabatow_rok": budzet},
        "uwagi": uwagi,
    }


def wiersz_z_wkladami(
    wklady: pd.DataFrame, wartosci: pd.DataFrame, wynik: pd.DataFrame, dzien_oceny: date
) -> pd.DataFrame:
    """Przegląd wsadowy: akcja i uzasadnienie dla każdego wiersza oferty_okresow (budżet nieustalony)."""
    wiersze = []
    for i in wynik.index:
        w = wynik.loc[i]
        d = decyzja(
            w["uplift"], w["ev"], w["p_oferta"], wklady.drop(columns="wklad_staly").loc[i], wartosci.loc[i],
            list(w["poza_zakresem"]), None, pd.Timestamp(w["migawka"]).date(), dzien_oceny,
        )  # fmt: skip
        wiersze.append({"id_umowy": i, "akcja": d["akcja"], "uzasadnienie": d["uzasadnienie"]})
    return pd.DataFrame(wiersze).set_index("id_umowy")
