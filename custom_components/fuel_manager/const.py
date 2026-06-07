"""Stałe dla integracji Fuel Manager."""
from __future__ import annotations

DOMAIN = "fuel_manager"

# Wersja składowanych danych (helpers.storage.Store)
STORAGE_VERSION = 1
STORAGE_KEY_TPL = f"{DOMAIN}.{{entry_id}}"

# Klucze konfiguracji
CONF_NAME = "name"
CONF_CURRENCY = "currency"
CONF_TANK_CAPACITY = "tank_capacity"
CONF_DEVICE_TRACKER = "device_tracker"  # lokalizacja AUTA (opcjonalny zapas)
CONF_PHONE_TRACKER = "phone_tracker"  # lokalizacja TELEFONU (główne źródło)
CONF_DEFAULT_FUEL_TYPE = "default_fuel_type"
CONF_STATION_RADIUS = "station_radius"
CONF_USE_OVERPASS = "use_overpass"

DEFAULT_NAME = "Samochód"
DEFAULT_CURRENCY = "zł"
DEFAULT_TANK_CAPACITY = 55.0
DEFAULT_FUEL_TYPE = 110
DEFAULT_STATION_RADIUS = 300  # metry – snap do znanej stacji
DEFAULT_OVERPASS_RADIUS = 1500  # metry – wyszukiwanie nowych stacji w OSM

# Sygnał dispatchera (aktualizacja sensorów po zmianie danych)
SIGNAL_UPDATE = f"{DOMAIN}_update_{{entry_id}}"

# Nazwy serwisów
SERVICE_ADD_FUELING = "add_fueling"
SERVICE_EDIT_FUELING = "edit_fueling"
SERVICE_DELETE_FUELING = "delete_fueling"
SERVICE_IMPORT_FUELIO = "import_fuelio"
SERVICE_EXPORT_FUELIO = "export_fuelio"
SERVICE_FIND_STATIONS = "find_nearby_stations"
SERVICE_REBUILD_STATS = "rebuild_statistics"

# Atrybuty pojedynczego tankowania
ATTR_ID = "id"
ATTR_TIMESTAMP = "timestamp"
ATTR_ODOMETER = "odometer"
ATTR_FUEL = "fuel"
ATTR_PRICE_PER_LITER = "price_per_liter"
ATTR_TOTAL_COST = "total_cost"
ATTR_FULL = "full"
ATTR_FUEL_TYPE = "fuel_type"
ATTR_LATITUDE = "latitude"
ATTR_LONGITUDE = "longitude"
ATTR_STATION_NAME = "station_name"
ATTR_STATION_ID = "station_id"
ATTR_NOTES = "notes"
ATTR_TANK_NUMBER = "tank_number"
ATTR_CONSUMPTION = "consumption"

# Mapowanie kodów Fuelio FuelType -> czytelna nazwa (edytowalne).
# Z pliku użytkownika występują 110/111/112 = benzyny (samochód PHEV).
FUEL_TYPES: dict[int, str] = {
    0: "Inny / nieokreślony",
    110: "Benzyna 95 (Pb95)",
    111: "Benzyna 98 (Pb98)",
    112: "Benzyna 100 (Pb100 / Verva / V-Power)",
    113: "Benzyna E10",
    114: "Benzyna E85",
    120: "Diesel (ON)",
    121: "Diesel Premium (Verva ON / Ultimate)",
    130: "LPG",
    140: "CNG",
    150: "Wodór",
    160: "Prąd (EV)",
}


def fuel_type_name(code: int | str | None) -> str:
    """Zwraca czytelną nazwę typu paliwa dla kodu Fuelio."""
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        return FUEL_TYPES[0]
    return FUEL_TYPES.get(code_int, f"Paliwo {code_int}")
