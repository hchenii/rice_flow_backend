import requests

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

TEXTURE_MAP = {
    (0,  15):  "clay",
    (15, 25):  "clay loam",
    (25, 40):  "silty clay loam",
    (40, 60):  "silt loam",
    (60, 100): "sandy loam",
}

def _classify_texture(clay_pct: float, sand_pct: float) -> str:
    if clay_pct >= 40:
        return "clay"
    if clay_pct >= 27 and sand_pct <= 20:
        return "silty clay"
    if clay_pct >= 27:
        return "clay loam"
    if clay_pct >= 18 and sand_pct <= 15:
        return "silt loam"
    if sand_pct >= 70:
        return "sandy loam"
    return "loam"


def get_soil_data(lat: float, lon: float) -> dict:
    params = {
        "lon":      lon,
        "lat":      lat,
        "property": ["phh2o", "clay", "sand", "silt", "soc", "bdod", "nitrogen", "cec"],
        "depth":    "0-5cm",
        "value":    "mean",
    }
    resp = requests.get(SOILGRIDS_URL, params=params, timeout=15)
    resp.raise_for_status()

    props = {p["name"]: p["depths"][0]["values"]["mean"]
             for p in resp.json().get("properties", {}).get("layers", [])}

    ph        = round((props.get("phh2o") or 62)  / 10, 1)   # SoilGrids pH×10; 62 = pH 6.2
    clay      = round((props.get("clay")  or 350) / 10, 1)   # g/kg → %
    sand      = round((props.get("sand")  or 300) / 10, 1)
    silt      = round((props.get("silt")  or 350) / 10, 1)
    soc       = round((props.get("soc")   or 25)  / 10, 2)   # dg/kg → %; 25 = 2.5%
    bulk_dens = round((props.get("bdod")  or 130) / 100, 2)  # cg/cm³ → g/cm³
    nitrogen  = round((props.get("nitrogen") or 1500) / 100, 1)  # cg/kg → mg/kg
    cec       = round((props.get("cec")  or 200) / 10, 1)    # mmol/kg → cmol/kg

    texture = _classify_texture(clay, sand)

    return {
        "ph":              ph,
        "texture":         texture,
        "clay_pct":        clay,
        "sand_pct":        sand,
        "silt_pct":        silt,
        "organic_matter":  soc,
        "bulk_density":    bulk_dens,
        "nitrogen_ppm":    nitrogen,
        "cec":             cec,
        "drainage":        "poorly drained" if clay > 35 else "moderately drained",
    }
