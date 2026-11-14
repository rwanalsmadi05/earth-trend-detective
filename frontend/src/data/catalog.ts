import type { VariableId } from "../api/types";

export interface CatalogItem { id: VariableId; label: string; icon: string; line: string; source: string; from?: number }

// The fixed variable catalog (the same list the AI planner is restricted to).
export const CATALOG: CatalogItem[] = [
  { id: "T2M", label: "Temperature", icon: "🌡️", line: "How warm the air is, on average.", source: "NASA POWER · T2M" },
  { id: "T2M_MAX", label: "Maximum temperature", icon: "🔥", line: "How hot the hottest part of the day gets.", source: "NASA POWER · T2M_MAX" },
  { id: "PRECTOTCORR", label: "Rainfall", icon: "🌧️", line: "How much rain and snow falls.", source: "NASA POWER · PRECTOTCORR" },
  { id: "GWETROOT", label: "Root-zone soil moisture", icon: "🌱", line: "Whether the ground under the roots still holds water.", source: "NASA POWER · GWETROOT" },
  { id: "GWETTOP", label: "Surface soil moisture", icon: "💧", line: "How wet the top few centimetres of soil are.", source: "NASA POWER · GWETTOP" },
  { id: "RH2M", label: "Humidity", icon: "💨", line: "How much water vapour is in the air.", source: "NASA POWER · RH2M" },
  { id: "ALLSKY_SFC_SW_DWN", label: "Solar radiation", icon: "☀️", line: "How much sunlight reaches the ground.", source: "NASA POWER · ALLSKY_SFC_SW_DWN" },
  { id: "NDVI", label: "Vegetation (NDVI)", icon: "🌿", line: "How green the plants look from space.", source: "MODIS MOD13Q1 · ORNL DAAC", from: 2000 },
  { id: "HOT_DAYS", label: "Very hot days", icon: "🥵", line: "How many days a year pass 35 °C.", source: "NASA POWER daily · T2M_MAX" },
];
