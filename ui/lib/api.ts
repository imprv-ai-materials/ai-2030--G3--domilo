// Odczyty z API wyceny (api/api/main.py). Wywołania po stronie serwera Next.js, bez pamięci podręcznej:
// panel ma pokazywać stan po ostatnim przebiegu zadania nocnego.

export const API_URL = process.env.API_URL ?? "http://localhost:8101";

export type Rodzaj = "lokal" | "oferta";

export type PozycjaKolejki = {
  rodzaj: Rodzaj;
  id_obiektu: string;
  miasto: string | null;
  dzielnica: string | null;
  metraz: number | null;
  cena_ofertowa: number | null;
  powod: string | null;
  czas_przebiegu: string;
};

export type OfertaPonizejP10 = {
  id_obiektu: string;
  miasto: string | null;
  dzielnica: string | null;
  metraz: number | null;
  cena_ofertowa: number;
  p10: number;
  p50: number;
  p90: number;
  cena_do_p10: number;
  czas_przebiegu: string;
};

export type Czynnik = { cecha: string; opis: string; wplyw_pln: number };

export type KartaWyceny = {
  rodzaj: Rodzaj;
  id_obiektu: string;
  miasto: string | null;
  dzielnica: string | null;
  metraz: number | null;
  wersja_modelu: string;
  czas_przebiegu: string;
  dzien_wyceny: string | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  odmowa: boolean;
  powod: string | null;
  cena_ofertowa: number | null;
  wartosc_bazowa: number | null;
  czynniki: Czynnik[];
  historia: { czas_przebiegu: string; p10: number | null; p50: number | null; p90: number | null; odmowa: boolean }[];
};

export class BladApi extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function pobierz<T>(sciezka: string): Promise<T> {
  let odp: Response;
  try {
    odp = await fetch(`${API_URL}${sciezka}`, { cache: "no-store" });
  } catch {
    throw new BladApi(0, `Brak połączenia z API wyceny (${API_URL}). Uruchom: cd api && poetry run uvicorn api.main:app --port 8101`);
  }
  if (!odp.ok) {
    throw new BladApi(odp.status, `API wyceny zwróciło ${odp.status} dla ${sciezka}`);
  }
  return (await odp.json()) as T;
}

export const kolejkaNieWiem = () => pobierz<PozycjaKolejki[]>("/valuation/kolejka-nie-wiem");
export const ofertyPonizejP10 = () => pobierz<OfertaPonizejP10[]>("/valuation/oferty-ponizej-p10");
export const kartaWyceny = (rodzaj: string, id: string) =>
  pobierz<KartaWyceny>(`/valuation/karta/${encodeURIComponent(rodzaj)}/${encodeURIComponent(id)}`);

const zl = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0 });
const m2 = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const proc = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 });

export const fmtZl = (x: number | null | undefined) => (x == null ? "—" : `${zl.format(x)} zł`);
export const fmtM2 = (x: number | null | undefined) => (x == null ? "—" : `${m2.format(x)} m²`);
export const fmtProc = (x: number) => `${proc.format(x)}%`;
export const fmtCzas = (iso: string) =>
  new Date(iso).toLocaleString("pl-PL", { timeZone: "Europe/Warsaw", dateStyle: "short", timeStyle: "short" });

// --- Panel kierownika zespołu najmu (GET /team/dashboard; metryki z modeli dbt, docs/kolejka_panel.md) ----------

export type ZrodloKolejki = "symulacja_wstecz" | "zadanie";

export type TydzienPrzychodu = {
  tydzien: string;
  koniec_tygodnia: string;
  pelny_tydzien_przychodu: boolean;
  podpisania_z_zapytan: number;
  godziny_doradcow: number;
  wartosc_umow_z_zapytan: number;
  przychod_na_godzine_doradcy: number;
};

export type TydzienKolejki = {
  tydzien: string;
  koniec_tygodnia: string;
  zrodlo_kolejki: string;
  dni_kolejki: number;
  pierwsze_kontakty: number | null;
  pierwsze_kontakty_z_top: number | null;
  pierwsze_kontakty_poza_rankingiem: number | null;
  adopcja: number | null;
  adopcja_losowa: number | null;
  zapytania_decyl: number | null;
  umowy_decyl: number | null;
  konwersja_decyl: number | null;
  mediana_godz_kontaktu_decyl: number | null;
  bez_kontaktu_decyl: number | null;
  zapytania_poza_decylem: number | null;
  konwersja_poza_decylem: number | null;
  mediana_godz_kontaktu_poza_decylem: number | null;
  pominiecia: number;
  przychod_na_godzine_doradcy: number | null;
};

export type OkresAdopcji = {
  zrodlo_kolejki: ZrodloKolejki;
  od: string;
  do: string;
  dni: number;
  dni_z_kontaktami: number;
  pierwsze_kontakty: number;
  z_top: number;
  poza_rankingiem: number;
  adopcja: number | null;
  adopcja_losowa: number | null;
};

export type OkresDecyla = {
  zrodlo_kolejki: ZrodloKolejki;
  gorny_decyl: boolean;
  zapytania: number;
  umowy: number;
  konwersja: number | null;
  mediana_godz_kontaktu: number | null;
  bez_kontaktu: number | null;
};

export type OkresPrzychodu = {
  zrodlo_kolejki: ZrodloKolejki;
  od: string;
  do: string;
  tygodnie: number;
  wartosc_umow_z_zapytan: number;
  godziny_doradcow: number;
  przychod_na_godzine_doradcy: number | null;
};

export type AdopcjaDoradcy = {
  zrodlo_kolejki: ZrodloKolejki;
  id_doradcy: string;
  miasto: string;
  dni: number;
  pierwsze_kontakty: number;
  z_top: number;
  adopcja: number | null;
  adopcja_losowa: number | null;
};

export type PowodPominiecia = { powod: string; opis: string; pominiecia: number; w_gornym_decylu: number };

export type Pominiecie = {
  data_kolejki: string;
  id_doradcy: string;
  miasto: string | null;
  pozycja: number;
  id_leada: string;
  powod: string;
  komentarz: string | null;
  zgloszono: string;
  zmieniono: string;
  ev_pln: number | null;
};

export type PanelKierownika = {
  przychod: {
    wartosc_wyjsciowa: {
      poczatek_okresu: string;
      koniec_okresu: string;
      przychod_na_godzine_doradcy: number;
      wartosc_umow_z_zapytan: number;
      godziny_doradcow: number;
    } | null;
    tygodnie: TydzienPrzychodu[];
  };
  tygodnie: TydzienKolejki[];
  okresy: { adopcja: OkresAdopcji[]; decyl: OkresDecyla[]; przychod: OkresPrzychodu[] };
  doradcy: AdopcjaDoradcy[];
  pominiecia: { powody: PowodPominiecia[]; ostatnie: Pominiecie[] };
};

export const panelKierownika = () => pobierz<PanelKierownika>("/team/dashboard");

const godz = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const fmtGodz = (x: number | null | undefined) => (x == null ? "—" : `${godz.format(x)} h`);
export const fmtUdzial = (x: number | null | undefined) => (x == null ? "—" : `${proc.format(100 * x)}%`);
export const fmtData = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("pl-PL", { day: "numeric", month: "short", year: "numeric" });
