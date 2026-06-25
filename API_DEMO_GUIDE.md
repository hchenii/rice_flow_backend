# GeoRice Advisor — API Demo Guide (Panel / Capstone Defense)

**Purpose:** Show the panel that our environmental data is *live and real*, pulled from
public scientific APIs — not hardcoded. This guide gives copy-paste URLs for Postman and a
step-by-step script for the full pipeline.

**Demo coordinates:** Panabo City, Davao del Norte → `lat = 7.3086`, `lon = 125.6830`

> 💡 **The 30-second pitch:** "When a farmer pins a farm, we send the GPS coordinates to
> three public APIs in parallel — SoilGrids for soil, Open-Meteo for climate and elevation,
> and Google Gemini for AI guidance. Our backend fuses them into one Environmental Scan,
> then runs that through our FAO-based RSI engine to rank the top-3 rice varieties."

---

## Data Source Summary (the "where does the data come from" table)

| API | Who runs it | What it gives us | RSI factors fed |
|-----|-------------|------------------|-----------------|
| **SoilGrids** | ISRIC — World Soil Information | soil pH, texture, organic carbon, CEC, nitrogen | soil pH, soil texture, organic matter, drainage |
| **Open-Meteo Forecast** | Open-Meteo.com (free, no key) | temperature, humidity, solar radiation, rainfall | avg temp, temp at flowering, humidity, solar, seasonal rainfall |
| **Open-Meteo Archive** | Open-Meteo.com | real historical rainfall (past 365 days) | annual rainfall |
| **Open-Meteo Elevation** | Open-Meteo.com | elevation (m) from digital elevation model | elevation |
| **Google Gemini** | Google | AI planting guide + chat answers | (not RSI — guidance text) |

User-entered: farm GPS pin, ecosystem type, slope, field logs, harvest.
Computed by us: **RSI score, flood risk, drainage class, variety clustering, yield prediction.**
Seeded reference: rice varieties (PhilRice / NSIC), FAO suitability ranges + WLC weights.

---

# PART 1 — Raw External APIs (Postman: GET, no auth)

Best for proving "this is real data." Open Postman → **New → HTTP Request → GET** → paste URL → **Send**.

### 1.1 SoilGrids (ISRIC) — soil data
```
https://rest.isric.org/soilgrids/v2.0/properties/query?lon=125.6830&lat=7.3086&property=phh2o&property=clay&property=sand&property=silt&property=soc&property=bdod&property=nitrogen&property=cec&depth=0-5cm&value=mean
```
**Point at:** `properties.layers[].depths[0].values.mean`
- `phh2o` is **pH × 10** → 62 means pH 6.2
- `clay` / `sand` / `silt` are in **g/kg** → divide by 10 for %
- `soc` (soil organic carbon) → ÷10 = organic matter %

⚠️ SoilGrids is sometimes slow or rate-limited — allow 10–15 seconds, retry if it times out.

### 1.2 Open-Meteo Forecast — temperature / humidity / solar / rainfall (7-day)
```
https://api.open-meteo.com/v1/forecast?latitude=7.3086&longitude=125.6830&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_max,shortwave_radiation_sum,windspeed_10m_max,sunshine_duration&timezone=Asia/Manila&forecast_days=7
```
**Point at:** the `daily` arrays — avg temp = (max+min)/2, humidity, solar radiation, rainfall.

### 1.3 Open-Meteo Archive — real historical rainfall (past year)
```
https://archive-api.open-meteo.com/v1/archive?latitude=7.3086&longitude=125.6830&start_date=2025-05-29&end_date=2026-05-29&daily=precipitation_sum&timezone=Asia/Manila
```
**Point at:** annual rainfall = the **sum** of `daily.precipitation_sum`.
> Adjust the dates to roughly the last 365 days from your demo date.

### 1.4 Open-Meteo Elevation — meters above sea level
```
https://api.open-meteo.com/v1/elevation?latitude=7.3086&longitude=125.6830
```
**Point at:** `elevation[0]`.

### 1.5 Open-Meteo Current Weather — (the dashboard weather card)
```
https://api.open-meteo.com/v1/forecast?latitude=7.3086&longitude=125.6830&current=temperature_2m,weather_code,precipitation,relative_humidity_2m,wind_speed_10m&hourly=temperature_2m,weather_code,precipitation,precipitation_probability&forecast_days=2&timezone=Asia/Manila
```

### 1.6 Google Gemini — AI guidance (POST + key)
- **Method:** `POST`
- **URL:** `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=YOUR_GEMINI_KEY`
- **Headers:** `Content-Type: application/json`
- **Body (raw → JSON):**
```json
{
  "contents": [
    { "role": "user", "parts": [{ "text": "Anong uri ng palay ang maganda itanim sa Panabo City ngayong tag-ulan?" }] }
  ]
}
```
> 🔒 **Do NOT show your real Gemini key on screen.** It lives in `rice_flow_backend/.env`.
> If it ever appears in a screenshot, rotate it at https://aistudio.google.com.

---

# PART 2 — The Full Pipeline (YOUR backend combining the APIs)

This is the most impressive demo: one of our endpoints calls **all three APIs at once** and
returns a single clean scan, then the RSI engine ranks varieties. These need a JWT token.

**Base URL (local):** `http://127.0.0.1:8000`
First start the server: `python manage.py runserver`

### Step 1 — Log in to get a token
- **POST** `http://127.0.0.1:8000/api/auth/login/`
- **Body (raw → JSON):**
```json
{ "email": "your-account@email.com", "password": "your-password" }
```
- **Copy** the `access_token` from the response.

### Step 2 — List your farms (to get a farm id)
- **GET** `http://127.0.0.1:8000/api/farms/`
- **Headers:** `Authorization: Bearer <access_token>`
- Note the `id` of the farm you want to scan → call it `<farm_id>`.

### Step 3 — Run the Environmental Scan (calls SoilGrids + Open-Meteo live)
- **POST** `http://127.0.0.1:8000/api/environmental/scan/<farm_id>/`
- **Headers:** `Authorization: Bearer <access_token>`
- **Say this:** "This single call fires SoilGrids and the three Open-Meteo endpoints in
  parallel, then stores one EnvironmentalScan." Note the returned scan `id` → `<scan_id>`.

### Step 4 — Generate Recommendations (the RSI engine)
- **POST** `http://127.0.0.1:8000/api/recommendations/generate/<scan_id>/`
- **Headers:** `Authorization: Bearer <access_token>`
- **Point at:** the top-3 results with `rsi_score`, `suitability_class`, and `factor_scores`.
- **Say this:** "Each variety is scored across 12 weighted factors using the FAO land
  suitability framework; we rank them and return the best three."

---

# PART 3 — Bonus: prove the FAO ranges + weights are real (defense gold)

- **GET** `http://127.0.0.1:8000/api/recommendations/rules/`
- **Headers:** `Authorization: Bearer <access_token>`
- Shows the live `SuitabilityRuleSet` — every factor's FAO range and its WLC weight
  (weights sum to exactly 1.00). Great answer to "where do your weights come from?"

---

## Suggested demo order (smooth narrative)
1. **1.1 SoilGrids** → "real soil for our coordinates."
2. **1.2 Open-Meteo Forecast** → "real climate."
3. **1.4 Elevation** → "real topography."
4. **Step 3 Scan** → "our backend fuses all of them into one scan."
5. **Step 4 Recommend** → "RSI engine produces the top-3 varieties."
6. **Part 3 Rules** → "and here are the FAO ranges + weights behind the score."

---

## Troubleshooting
| Problem | Fix |
|---------|-----|
| SoilGrids times out | Retry; it's rate-limited. Have a saved screenshot as backup. |
| `401 Unauthorized` on backend | Token missing/expired — redo Step 1, re-copy `access_token`. |
| `404 Farm not found` | Use a `farm_id` that belongs to the logged-in user (Step 2). |
| Backend won't start | `pip install -r requirements.txt`, then `python manage.py runserver`. |
| Gemini `400/403` | Check the key in `.env` and that it's appended as `?key=...`. |
| No internet at venue | Pre-save Postman responses as screenshots the night before. |

## Pre-demo checklist
- [ ] `python manage.py runserver` works
- [ ] You have a real login email + password
- [ ] At least one farm exists for that account
- [ ] Postman collection imported (`RiceFlow_API_Demo.postman_collection.json`)
- [ ] Tested all Part 1 URLs return data
- [ ] Backup screenshots saved (in case venue Wi-Fi fails)
- [ ] Gemini key hidden from screen share

---

*All URLs and parameters in this guide are copied directly from the backend source:*
*`apps/environmental/services/soilgrids.py`, `apps/environmental/services/openmeteo.py`,*
*`apps/ai/views.py`, and the route files under each `apps/*/urls.py`.*