"""Fixed variable catalog. Keys are the VariableId values of frontend/src/api/types.ts.
The LLM planner (step 3) may only choose from these."""
from .config import LAST_FULL_YEAR

POWER_HOME = "https://power.larc.nasa.gov/"

# kind: "power" (monthly column) | "power_daily" (annual count) | "modis"
VARIABLES = {
    "T2M": dict(kind="power", col="T2M", label="Temperature", unit="°C", noun="air temperature",
                reason="Hotter air pulls more water out of soil and open water."),
    "T2M_MAX": dict(kind="power", col="T2M_MAX", label="Maximum temperature", unit="°C", noun="daytime peak temperature",
                    reason="Daily peaks show heat stress that averages can hide."),
    "PRECTOTCORR": dict(kind="power", col="PRECTOTCORR", label="Rainfall", unit="mm/day", noun="rain",
                        reason="Rain is what refills the land. If a place is drying up, rainfall is the first suspect."),
    "GWETROOT": dict(kind="power", col="GWETROOT", label="Root-zone soil moisture", unit="fraction (0-1)",
                     noun="water in the soil under the roots",
                     reason="Soil moisture shows whether the ground still holds water for plants."),
    "GWETTOP": dict(kind="power", col="GWETTOP", label="Surface soil moisture", unit="fraction (0-1)",
                    noun="water in the topsoil", reason="The top layer of soil reacts fastest to rain and heat."),
    "RH2M": dict(kind="power", col="RH2M", label="Humidity", unit="%", noun="humidity",
                 reason="Dry air speeds up evaporation."),
    "ALLSKY_SFC_SW_DWN": dict(kind="power", col="ALLSKY_SFC_SW_DWN", label="Solar radiation", unit="MJ/m²/day",
                              noun="sunlight reaching the ground", reason="Sunlight drives heating and evaporation.",
                              start_year=1984),
    "NDVI": dict(kind="modis", col="ndvi", label="Vegetation (NDVI)", unit="index", noun="vegetation greenness",
                 reason="Plants are the visible witness: green fades when water runs short. (Satellite record starts in 2000.)",
                 start_year=2000),
    "HOT_DAYS": dict(kind="power_daily", col="hot_days", label="Very hot days", unit="days/year above 35 °C",
                     noun="days above 35 °C", reason="Counting extreme-heat days shows how often the heat bites."),
}

# What a general audience calls each variable (used in "No clear change in <plain> since 2000 — could be chance").
PLAIN = {"T2M": "temperature", "T2M_MAX": "daytime peak temperature", "PRECTOTCORR": "rainfall", "GWETROOT": "soil moisture",
         "GWETTOP": "topsoil moisture", "RH2M": "humidity", "ALLSKY_SFC_SW_DWN": "sunshine", "NDVI": "plant greenness",
         "HOT_DAYS": "very hot days"}

# Default plan without the LLM (template fallback), in chain-of-evidence order.
DEFAULT_PLAN = ["T2M", "PRECTOTCORR", "GWETROOT", "HOT_DAYS"]  # NDVI is appended automatically once cached
