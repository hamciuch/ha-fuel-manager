# ⛽ Fuel Manager dla Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-1.0.0-blue.svg)

Integracja do prowadzenia **dziennika tankowań** w Home Assistant: ręczne
wpisywanie tankowań (przebieg, litry, cena/litr, kwota), automatyczny czas
i lokalizacja (wyszukiwanie / „przyklejanie” najbliższej stacji), wybór rodzaju
paliwa oraz **import danych z aplikacji Fuelio** (CSV).

## ✨ Funkcje

- Serwis `fuel_manager.add_fueling` – zapis tankowania z pełnym zestawem pól;
  brakująca cena lub kwota jest doliczana automatycznie.
- **Lokalizacja stacji** – domyślnie z **telefonu wprowadzającego tankowanie**
  (osoba/`device_tracker` telefonu), bo to on jest na stacji; pozycja auta jest
  opcjonalnym zapasem. Można też podać jawne GPS lub konkretną encję. Gdy punkt
  jest blisko znanej z historii stacji, jej nazwa/ID przyklejają się
  automatycznie (konfigurowalny promień).
- `fuel_manager.find_nearby_stations` – wyszukiwanie stacji w OpenStreetMap
  (Overpass, bez klucza API) + z historii; może wypełnić `input_select`.
- Wybór rodzaju paliwa (kody Fuelio 110/111/112 = Pb95/98/100 itd.).
- **Import / eksport Fuelio** – dedup po GUID (import można powtarzać).
- Sensory: ostatnie tankowanie, średnie/ostatnie spalanie (liczone jak Fuelio),
  średnia cena, suma kosztów/litrów, koszt na km, najbliższa stacja, historia.
- Dane w `.storage` – przeżywają restart, niezależne od recordera.

## 📦 Instalacja

### Opcja A — HACS (zalecane)

1. HACS → **Integrations** → menu (⋮) → **Custom repositories**.
2. Wklej URL repo, kategoria: **Integration**, **Add**.
3. Wyszukaj „Fuel Manager”, **Download**, zrestartuj Home Assistant.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=yourusername&repository=ha-fuel-manager&category=integration)

### Opcja B — ręcznie

Skopiuj `custom_components/fuel_manager/` do `/config/custom_components/`
i zrestartuj HA.

### Konfiguracja

**Ustawienia → Urządzenia i usługi → Dodaj integrację → „Fuel Manager”**.
Podaj nazwę pojazdu (np. `MG HS`), walutę, pojemność baku, domyślne paliwo,
**lokalizację telefonu** (osoba lub `device_tracker` telefonu – główne źródło
pozycji), opcjonalnie lokalizację auta (zapas) i promień „snapowania” do znanej
stacji.

### Lokalizacja przy tankowaniu

Tankowania wpisujesz w telefonie, więc to jego GPS jest źródłem pozycji.
Priorytet: jawne `latitude/longitude` → `location_entity` → telefon
(`use_phone_location`) → auto (`use_car_location`). Aby pozycja była świeża,
przykładowy skrypt może najpierw wymusić aktualizację GPS przez aplikację
mobilną (`notify.mobile_app_<telefon>` z treścią `request_location_update`) –
podmień nazwę swojego `notify` w pakiecie lub usuń ten krok.

> Nazwa pojazdu wyznacza `entity_id` sensorów: „MG HS” → `sensor.mg_hs_*`
> (np. `sensor.mg_hs_najblizsza_stacja`). Przy innej nazwie popraw encje
> w plikach z katalogu [`examples/`](examples/).

## 🖥️ Formularz i dashboard (opcjonalnie)

W [`examples/packages/`](examples/packages/) jest pakiet z pomocnikami
(`input_number/select/...`) i skryptami formularza. Skopiuj go do
`/config/packages/` i dodaj w `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

Gotowy widok Lovelace: [`examples/lovelace/dashboard_tankowania.yaml`](examples/lovelace/dashboard_tankowania.yaml).
Przepływ: **Szukaj stacji** → litry/cena → **Zapisz**.

## 📈 Historia i oś czasu

Wszystkie tankowania trafiają do `.storage` i są widoczne:

- **Tabela historii** – karta markdown w przykładowym dashboardzie czyta atrybut
  `fuelings` z `sensor.<auto>_historia_tankowan` (do 500 wpisów, z datą, przebiegiem,
  litrami, ceną, kwotą, spalaniem i stacją).
- **Wykresy w czasie** – przy imporcie integracja zapisuje **statystyki
  długoterminowe z oryginalnymi datami** z pliku (cena/litr, spalanie, przebieg,
  kwota oraz skumulowane wydatki i litry). ID statystyk: `fuel_manager:<slug>_price`,
  `..._consumption`, `..._fill_cost`, `..._odometer`, `..._spend`, `..._volume`
  (slug z nazwy auta, np. `mg_hs`). Dodaj je kartą **Statistics graph** albo
  obejrzyj w **Narzędzia deweloperskie → Statystyki**.

> Jeśli widzisz tylko „ostatnie tankowanie” i podsumowanie – to znaczy, że
> patrzysz na stany sensorów. Pełny dziennik jest w tabeli historii i na wykresach
> statystyk (wymaga dodania kart z `examples/lovelace/`).

## 🚗🚙 Więcej niż jedno auto

Po prostu **dodaj integrację ponownie** dla każdego auta (Dodaj integrację →
Fuel Manager → inna nazwa). Każde auto ma wtedy własne urządzenie, własne
sensory (`sensor.mg_hs_*`, `sensor.skoda_*`), osobny zapis danych i niezależny
import. W serwisach wskazujesz auto parametrem `vehicle` (gdy aut jest więcej,
jest wymagany):

```yaml
service: fuel_manager.add_fueling
data:
  vehicle: "Skoda Octavia"
  odometer: 154000
  fuel: 45.2
  price_per_liter: 6.49
```

Przykładowy formularz/dashboard są **wieloautowe** – wybierasz auto w
`input_select.fuel_vehicle` (wpisz w nim nazwy aut dokładnie jak w integracji),
a statystyki i historia automatycznie podążają za wybranym autem.

## 📥 Import z Fuelio

```yaml
service: fuel_manager.import_fuelio
data:
  vehicle: "MG HS"   # gdy masz więcej aut
  file_path: /config/fuelio/car5-20260427-105230.csv
```

Działa bez dodatkowej konfiguracji plik z `/config` (np. `/config/car5.csv`,
wrzucony dodatkiem File editor / Samba / Studio Code Server), z `/config/www`
(czyli `/local/...`) oraz z `/media` (na HAOS możesz go wgrać wprost z panelu
*Media*, nawet z telefonu, i podać `file_path: /media/car5.csv`). Inne lokalizacje
wymagają wpisu w `allowlist_external_dirs`. Możesz też pominąć plik i wkleić całą
zawartość CSV w polu `content`. Import jest idempotentny (po GUID).

## ⛽ Kody rodzaju paliwa (Fuelio)

| Kod | Paliwo | Kod | Paliwo |
| --- | --- | --- | --- |
| 110 | Benzyna 95 (Pb95) | 120 | Diesel (ON) |
| 111 | Benzyna 98 (Pb98) | 121 | Diesel Premium |
| 112 | Benzyna 100 (Pb100/Verva) | 130/140/160/0 | LPG / CNG / EV / Inny |

Mapowanie jest w `custom_components/fuel_manager/const.py` (`FUEL_TYPES`).
Nieznane kody są zachowywane i wyświetlane jako „Paliwo &lt;kod&gt;”.

## 🛠️ Serwisy

`add_fueling`, `edit_fueling`, `delete_fueling`, `import_fuelio`,
`export_fuelio`, `find_nearby_stations` – formularze widoczne w
**Narzędzia deweloperskie → Akcje**.

## ⚠️ Uwagi

- Sekcje `## Costs` z Fuelio nie są importowane (integracja dotyczy paliwa).
- Overpass to publiczny endpoint OSM (fair-use); można go wyłączyć w opcjach.

## Licencja

MIT — patrz [LICENSE](LICENSE).
