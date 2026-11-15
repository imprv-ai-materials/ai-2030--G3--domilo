-- Migawki najemców: jeden wiersz = kończąca się umowa roczna (B2C lub B2B), stan na dzień migawki
-- 60 dni przed data_do; target odejdzie (opis i liczby: docs/target_najemcy.md).
--
-- Populacja: pms_umowy typu 'pierwsza' albo 'przedłużenie' (linie B2C i B2B; 'średnioterminowa' = linia MID
--   pomijamy) z data_do od 2023-03-01 do 2026-09-30 włącznie. Jak w retencja_decyzje („kończąca się umowa
--   roczna”) należą tu też pierwsze umowy B2B na 18 i 24 miesiące; miesiecy_umowy pozwala je odfiltrować.
-- Wcześniejsze rozwiązania pomijamy: najem z data_wyprowadzenia < data_do tej umowy (wyprowadzka przed końcem).
-- data_do to ostatni dzień umowy (kolejny okres zaczyna się data_do + 1 dzień).
-- data_migawki = data_do - 60 dni. Migawka to stan na początek tego dnia: zdarzenie z datą < data_migawki już
--   znamy, zdarzenie z datą >= data_migawki jeszcze nie.
-- odejdzie = 1, gdy najem nie ma kolejnego okresu umowy (nr_okresu + 1 w pms_umowy) i nie było przeprowadzki;
--   0 w przeciwnym razie.
-- przeprowadzka: ten sam najemca (id_najemcy) wprowadził się do innego najmu Domilo (dowolna linia) między
--   dniem migawki (data_do - 60 dni) a data_do + 30 dni, a najem nie ma kolejnego okresu umowy (gdy ma, drugi
--   najem jest równoległy). Najem zaczęty wcześniej to najem równoległy, a później to powrót po przerwie (lokal
--   stoi pusty), czyli odejście.
-- wypowiedzenie_przed_migawka: pms_najmy.wypowiedzenie_data < data_migawki. Znane w dniu migawki, ale prawie
--   przesądza wynik (wypowiedzenie mają tylko najmy, które się kończą).
-- Kolumny po odejdzie (id_umowy_nastepnej, id_najmu_przeprowadzki, data_wyprowadzenia, powod_odejscia,
--   wypowiedzenie_data) opisują wynik po fakcie: nie są cechami do predykcji.
-- Daty PMS (TIMESTAMP bez strefy, północ czasu warszawskiego) rzutujemy na DATE.
WITH parametry AS (
    SELECT
        DATE '2023-03-01' AS koniec_od,
        DATE '2026-09-30' AS koniec_do,
        60 AS dni_przed_koncem,
        30 AS dni_na_przeprowadzke
),
umowy AS (
    SELECT
        u.id_umowy,
        u.id_najmu,
        u.nr_okresu,
        u.typ,
        u.data_od::DATE AS data_od,
        u.data_do::DATE AS data_do,
        u.id_umowy_ramowej,
        n.id_najemcy,
        n.id_lokalu,
        n.linia,
        n.data_wyprowadzenia::DATE AS data_wyprowadzenia,
        n.powod_odejscia,
        n.wypowiedzenie_data::DATE AS wypowiedzenie_data
    FROM pms_umowy AS u
    JOIN pms_najmy AS n USING (id_najmu)
    WHERE u.typ IN ('pierwsza', 'przedłużenie')
),
populacja AS (
    SELECT
        u.*,
        u.data_do - p.dni_przed_koncem AS data_migawki
    FROM umowy AS u, parametry AS p
    WHERE u.data_do BETWEEN p.koniec_od AND p.koniec_do
      AND (u.data_wyprowadzenia IS NULL OR u.data_wyprowadzenia >= u.data_do)
),
nastepna AS (
    SELECT p.id_umowy, u2.id_umowy AS id_umowy_nastepnej
    FROM populacja AS p
    JOIN pms_umowy AS u2 ON u2.id_najmu = p.id_najmu AND u2.nr_okresu = p.nr_okresu + 1
),
przeprowadzka AS (
    SELECT
        p.id_umowy,
        arg_min(b.id_najmu, b.data_wprowadzenia) AS id_najmu_przeprowadzki
    FROM populacja AS p
    CROSS JOIN parametry AS par
    JOIN pms_najmy AS b
        ON b.id_najemcy = p.id_najemcy
       AND b.id_najmu <> p.id_najmu
       AND b.data_wprowadzenia::DATE BETWEEN p.data_migawki AND p.data_do + par.dni_na_przeprowadzke
    WHERE p.id_umowy NOT IN (SELECT id_umowy FROM nastepna)
    GROUP BY p.id_umowy
)
SELECT
    p.id_umowy,
    p.id_najmu,
    p.id_najemcy,
    p.id_lokalu,
    p.linia,
    p.typ,
    p.nr_okresu,
    p.data_od,
    p.data_do,
    date_diff('month', p.data_od, p.data_do + 1) AS miesiecy_umowy,
    p.id_umowy_ramowej,
    p.data_migawki,
    date_trunc('month', p.data_do)::DATE AS miesiac_konca,
    coalesce(p.wypowiedzenie_data < p.data_migawki, false) AS wypowiedzenie_przed_migawka,
    CASE WHEN n.id_umowy_nastepnej IS NULL AND pr.id_najmu_przeprowadzki IS NULL THEN 1 ELSE 0 END AS odejdzie,
    n.id_umowy_nastepnej,
    pr.id_najmu_przeprowadzki IS NOT NULL AS przeprowadzka,
    pr.id_najmu_przeprowadzki,
    p.data_wyprowadzenia,
    p.powod_odejscia,
    p.wypowiedzenie_data
FROM populacja AS p
LEFT JOIN nastepna AS n USING (id_umowy)
LEFT JOIN przeprowadzka AS pr USING (id_umowy)
ORDER BY p.data_do, p.id_umowy
