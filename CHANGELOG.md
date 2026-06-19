# Changelog

Wszystkie istotne zmiany w projekcie. Format wzorowany na
[Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
wersjonowanie [SemVer](https://semver.org/lang/pl/).

## [1.4.0] – 2026-06-08

### Dodane
- **Koszty dodatkowe** – nowy rejestr wydatków poza paliwem (przegląd, ubezpieczenie,
  serwis, naprawa, opony itd.) z kwotą, datą, przebiegiem i **opisem**. Serwisy
  `add_expense`, `edit_expense`, `delete_expense`; sensor `..._koszty_dodatkowe`
  (sumy łącznie/rok/wg kategorii). Osobna zakładka w panelu z formularzem, edycją
  i historią.
- **Rodzaj paliwa w edytorze** tankowań (wczytywanie i zapis).

### Zmienione
- Wykresy „… / rok” to teraz **słupki z latami** (kolejne lata dochodzą same),
  zamiast osi miesięcznej.
- Czytelniejsze karty Koszty/Odległość/Tankowanie: duża wartość główna,
  pogrubienia i rozdzielone sekcje (ceny/rachunki, koszt na km itd.).
- Stałe `entity_id` sensorów analizy i kosztów (np. `sensor.<auto>_analiza`),
  niezależne od obszaru urządzenia.

## [1.4.1] – 2026-06-19

### Dodane
- **Import kosztów z Fuelio.** `import_fuelio` czyta teraz także sekcje `## Costs`
  i `## CostCategories` i zapisuje je jako koszty dodatkowe (kategoria z mapy
  `CostTypeID → nazwa`, kwota, data, przebieg, opis = tytuł + notatka). Szablony
  (`isTemplate`) i przychody (`isIncome`) są pomijane. Odpowiedź serwisu zawiera
  `imported_expenses` i `total_expenses`.

### Zmienione
- **Twardszy dedup importu.** Tankowania odsiewane nie tylko po GUID, ale też po
  sygnaturze (data+przebieg+litry), a koszty po GUID – ponowny import tego samego
  pliku nie tworzy duplikatów, doda jedynie nowe wpisy.
- README: zaktualizowany opis importu (tankowania + koszty, idempotentność).

## [1.3.2] – 2026-06-19

### Naprawione
- Integracja nie wczytywała się (`NameError: name 'handle_import' is not defined`
  podczas `async_setup`). Ciało handlera importu Fuelio było przyklejone do
  `handle_delete_expense` bez własnej definicji funkcji – przywrócono nagłówek
  `async def handle_import(...)`, dzięki czemu serwis `import_fuelio` rejestruje
  się poprawnie, a `delete_expense` ma znów właściwe ciało.
- **Panel (apexcharts-card):** karty słupkowe „… / rok" i „… / miesiąc" zgłaszały
  `Błąd konfiguracji` (`value.chart_type is none of line/scatter/pie/donut/radialBar`).
  Usunięto nieprawidłowe `chart_type: bar` na poziomie karty – słupki realizuje już
  `type: column` na serii (poprawny sposób w apexcharts-card).
- **Panel:** karta „Koszty dodatkowe / rok" zgłaszała `value.series[0].color is not
  a string` – usunięto `color: null` (kolor dobiera motyw).

## [1.3.1] – 2026-06-18

### Naprawione
- Wykresy „na rok” (koszty/odległość/paliwo/koszty dodatkowe) pokazują teraz lata
  (słupek na rok), a nie miesiące; kolejne lata dochodzą automatycznie.
- Czytelniejsze karty statystyk (Koszty/Odległość/Tankowanie): sekcje, pogrubienia,
  duża suma na górze i polskie formatowanie liczb (spacja tysięcy, przecinek).
- Stały `entity_id` sensora analizy (`<auto>_analiza`) – obszar urządzenia nie
  zmieni już nazwy encji.

## [1.3.0] – 2026-06-07

### Dodane
- **Sensor „Analiza”** (`sensor.<auto>_analiza`) liczący komplet statystyk w atrybutach:
  koszty/dystans/paliwo łącznie, w tym roku i w poprzednich latach, min/max ceny i
  rachunków, koszt na km (śr./min/max), koszty dzienne oraz dane miesięczne (14 mies.).
- **Panel z zakładkami**: Tankowania (dodawanie + edycja + historia), Koszty,
  Odległość, Tankowanie – każda z porównaniem rok do roku (wykresy słupkowe) oraz
  wykresem wydatków/kilometrów/litrów dla ostatnich 14 miesięcy (porównanie z
  analogicznym miesiącem poprzedniego roku).

## [1.2.0] – 2026-06-07

### Dodane
- **Edytor tankowań w dashboardzie** – wybór wpisu z listy, automatyczne
  wczytanie wartości, poprawa i zapis na przycisk (oraz usuwanie). Zapis pozostaje
  ręczny; podczas wczytywania działa blokada przeliczania, by nie nadpisać danych.
- **Autowyliczanie w formularzu** (dodawanie i edycja): podaj dowolne dwa z pól
  litry / cena za litr / kwota, trzecie policzy się samo. Zabezpieczone przed
  zapętleniem.
- **Interaktywne wykresy ApexCharts** – każdy punkt to jedno tankowanie, dymek po
  najechaniu pokazuje datę i wartości (spalanie, cena, kwota, przebieg).

### Naprawione
- Jednostki na wykresach: serie mają własne jednostki (L/100km, zł/L, zł, km)
  zamiast dziedziczonej „szt.”.
- Renderowanie historii w karcie markdown (jawne nowe linie zamiast sklejonej tabeli).

## [1.1.3] – 2026-06-07

### Dodane
- **Lokalizacja dla wielu osób** – pozycja brana automatycznie z encji `person`
  użytkownika, który wywołał akcję (każdy domownik tankuje ze swojego telefonu).
  Kolejność: jawne GPS → `location_entity` → osoba wywołująca → telefon z opcji → auto.

## [1.1.2] – 2026-06-07

### Naprawione
- **Średnie spalanie** liczone metodą Fuelio: ważone dystansem
  (całe paliwo / cały dystans × 100), z pominięciem paliwa sprzed pierwszego
  pełnego baku. Wcześniej była to zawyżona średnia arytmetyczna z l/100km.

## [1.1.1] – 2026-06-07

### Dodane
- Serwis `fuel_manager.rebuild_statistics` – ręczne przeliczenie statystyk,
  zwraca liczbę zapisanych punktów.
- Obsługa `mean_type` w statystykach (zgodność z Home Assistant 2026+).

### Naprawione
- Wykresy w czasie pokazywały tylko bieżący miesiąc – w przykładach dodano
  `days_to_show`.
- Głośniejsze logowanie błędów przy przeliczaniu statystyk (pełny ślad).

## [1.1.0] – 2026-06-05

### Dodane
- **Statystyki długoterminowe z datami z importu** – cena/litr, spalanie,
  przebieg, kwota oraz skumulowane wydatki i litry trafiają na oś czasu z
  oryginalnymi datami (widoczne w Narzędzia deweloperskie → Statystyki).
- Pełna historia tankowań w atrybucie sensora (do 500 wpisów).
- Pliki ikon (gotowe pod `home-assistant/brands`) + `BRANDS.md`.
- Wieloautowe przykłady dashboardu (selektor auta, dynamiczne statystyki).

### Zmienione
- `after_dependencies: recorder` w manifeście.

## [1.0.2] – 2026-06-05

### Naprawione
- Import/eksport działa z `/config`, `/config/www` i `/media`; rozwiązywanie
  dowiązań symbolicznych (poprawne na HAOS).

## [1.0.1] – 2026-06-05

### Naprawione
- Import/eksport z katalogu `/config` bez potrzeby `allowlist_external_dirs`.

## [1.0.0] – 2026-06-05

### Dodane
- Pierwsze wydanie integracji `fuel_manager` (config flow, trwałe składowanie,
  sensory).
- Serwisy: `add_fueling`, `edit_fueling`, `delete_fueling`, `import_fuelio`,
  `export_fuelio`, `find_nearby_stations`.
- Import/eksport Fuelio (CSV) z deduplikacją po GUID; spalanie liczone jak Fuelio.
- Najbliższa stacja: „snap” do znanej z historii + wyszukiwanie w OpenStreetMap
  (Overpass, bez klucza API).
- Lokalizacja z telefonu jako główne źródło, auto jako opcjonalny zapas.
- Obsługa wielu pojazdów (osobny wpis integracji na auto).
- Przykładowy pakiet (helpery + skrypty) i dashboard.
- Metadane HACS, licencja MIT, CI (hassfest + HACS), workflow Release.

[1.4.0]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.4.0
[1.3.1]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.3.1
[1.3.0]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.3.0
[1.2.0]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.2.0
[1.1.3]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.1.3
[1.1.2]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.1.2
[1.1.1]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.1.1
[1.1.0]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.1.0
[1.0.2]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.0.2
[1.0.1]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.0.1
[1.0.0]: https://github.com/hamciuch/ha-fuel-manager/releases/tag/v1.0.0
