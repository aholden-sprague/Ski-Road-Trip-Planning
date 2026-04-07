import math
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import openrouteservice
from openrouteservice import convert
import pandas as pd
import pydeck as pdk
import pyomo.environ as pyo
import requests
import streamlit as st


# ------------------------------------------------------------
# Ski Road Trip Planner
# ------------------------------------------------------------
# Setup:
#   pip install streamlit pandas requests pydeck openrouteservice
#   PowerShell:
#       $env:ORS_API_KEY="your_real_openrouteservice_key"
#       streamlit run ski_road_trip_planner.py
#
# What it does:
#   - Geocodes your starting point with openrouteservice
#   - Scores ski resorts using forecast snowfall + resort stats + drive time
#   - Builds a multi-stop trip using score-based routing
#   - Splits the trip into practical day-by-day itinerary legs
#   - Draws the trip on a map
#
# Notes:
#   - Resort weather is approximated using Open-Meteo forecast snowfall.
#   - Routing works best when resort coordinates are near a base area / parking lot.
# ------------------------------------------------------------

ORS_BASE_URL = "https://api.openrouteservice.org"
DEFAULT_PROFILE = "driving-car"
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjBjZmMwMDgyZGM5YzQzZWRhYWFiYTg0OTkzYmM2YzA0IiwiaCI6Im11cm11cjY0In0="


@dataclass
class Place:
    name: str
    state: str
    lat: float
    lon: float
    region: str
    pass_type: str
    vertical_ft: int


def load_resorts() -> pd.DataFrame:
    resorts = [
        # Northeast / Mid-Atlantic
        Place("Killington", "VT", 43.6265, -72.7968, "Northeast", "Ikon", 3050),
        Place("Sugarbush", "VT", 44.1351, -72.8943, "Northeast", "Ikon", 2600),
        Place("Stowe", "VT", 44.4654, -72.6874, "Northeast", "Epic", 2360),
        Place("Sugarloaf", "ME", 45.0314, -70.3131, "Northeast", "Independent", 2820),
        Place("Whiteface", "NY", 44.3659, -73.9026, "Northeast", "Independent", 3430),
        Place("Hunter", "NY", 42.2031, -74.2100, "Northeast", "Epic", 1600),
        Place("Stratton", "VT", 43.1137, -72.9060, "Northeast", "Ikon", 2003),
        Place("Sunday River", "ME", 44.4734, -70.8567, "Northeast", "Independent", 2340),
        Place("Okemo", "VT", 43.4024, -72.7170, "Northeast", "Epic", 2200),
        Place("Mount Snow", "VT", 42.9600, -72.9205, "Northeast", "Epic", 1700),
        Place("Smugglers' Notch", "VT", 44.5898, -72.7814, "Northeast", "Independent", 2610),
        Place("Jay Peak", "VT", 44.9241, -72.5044, "Northeast", "Independent", 2153),
        Place("Loon", "NH", 44.0800, -71.6290, "Northeast", "Ikon", 2100),
        Place("Cannon", "NH", 44.1564, -71.6981, "Northeast", "Independent", 2180),
        Place("Bretton Woods", "NH", 44.2581, -71.4389, "Northeast", "Independent", 1500),
        Place("Cranmore", "NH", 44.0584, -71.1284, "Northeast", "Independent", 1200),
        Place("Attitash", "NH", 44.0823, -71.2268, "Northeast", "Epic", 1750),
        Place("Wildcat", "NH", 44.26455, -71.24037, "Northeast", "Epic", 2112),
        Place("Waterville Valley", "NH", 43.9615, -71.5031, "Northeast", "Ikon", 2020),
        Place("Gunstock", "NH", 43.5387, -71.3734, "Northeast", "Independent", 1400),
        Place("Pats Peak", "NH", 43.1817, -71.8448, "Northeast", "Independent", 710),
        Place("Ragged Mountain", "NH", 43.4846, -71.8402, "Northeast", "Independent", 1250),
        Place("Black Mountain", "NH", 44.2929, -71.2864, "Northeast", "Independent", 1100),
        Place("Pico", "VT", 43.6709, -72.8428, "Northeast", "Independent", 1967),
        Place("Mad River Glen", "VT", 44.2022, -72.9176, "Northeast", "Independent", 2037),
        Place("Bolton Valley", "VT", 44.4210, -72.8510, "Northeast", "Independent", 1704),
        Place("Burke Mountain", "VT", 44.5733, -71.8933, "Northeast", "Independent", 2011),
        Place("Magic Mountain", "VT", 43.2012, -72.7709, "Northeast", "Independent", 1500),
        Place("Bromley", "VT", 43.1973, -72.9388, "Northeast", "Independent", 1334),
        Place("Saskadena Six", "VT", 43.6670, -72.8145, "Northeast", "Independent", 650),
        Place("Belleayre", "NY", 42.1390, -74.5042, "Northeast", "Independent", 1404),
        Place("Gore Mountain", "NY", 43.6996, -74.0044, "Northeast", "Independent", 2537),
        Place("Greek Peak", "NY", 42.5082, -76.1458, "Northeast", "Independent", 952),
        Place("Bristol Mountain", "NY", 42.7418, -77.4026, "Northeast", "Independent", 1200),
        Place("Holiday Valley", "NY", 42.2631, -78.6664, "Northeast", "Independent", 750),
        Place("Catamount", "NY", 42.1334, -73.4829, "Northeast", "Independent", 1000),
        Place("Jiminy Peak", "MA", 42.5540, -73.2923, "Northeast", "Ikon", 1150),
        Place("Wachusett", "MA", 42.4882, -71.8869, "Northeast", "Independent", 1000),
        Place("Butternut", "MA", 42.1547, -73.3204, "Northeast", "Independent", 1000),
        Place("Berkshire East", "MA", 42.6202, -72.8756, "Northeast", "Independent", 1180),
        Place("Blue Mountain", "PA", 40.8105, -75.5218, "Northeast", "Independent", 1082),
        Place("Elk Mountain", "PA", 41.6942, -75.5461, "Northeast", "Independent", 1000),
        Place("Camelback", "PA", 41.0511, -75.3543, "Northeast", "Independent", 800),
        Place("Montage Mountain", "PA", 41.3606, -75.6630, "Northeast", "Independent", 1000),
        Place("Seven Springs", "PA", 40.0239, -79.2970, "Northeast", "Epic", 754),
        Place("Hidden Valley", "PA", 40.0710, -79.2567, "Northeast", "Epic", 610),
        Place("Laurel Mountain", "PA", 40.2059, -79.1732, "Northeast", "Epic", 761),
        Place("Roundtop", "PA", 40.1096, -76.9445, "Northeast", "Epic", 600),
        Place("Liberty", "PA", 39.7635, -77.3754, "Northeast", "Epic", 620),
        Place("Whitetail", "PA", 39.7450, -77.9219, "Northeast", "Epic", 935),
        Place("Mountain Creek", "NJ", 41.1940, -74.5036, "Northeast", "Independent", 1040),
        Place("Mount Southington", "CT", 41.5967, -72.8788, "Northeast", "Independent", 425),
        Place("Mohawk Mountain", "CT", 41.8392, -73.2785, "Northeast", "Independent", 650),
        Place("Yawgoo Valley", "RI", 41.9935, -71.5014, "Northeast", "Independent", 245),
        Place("Ski Ward", "MA", 42.2706, -71.6823, "Northeast", "Independent", 220),

        # Midwest
        Place("Granite Peak", "WI", 44.9318, -89.6834, "Midwest", "Independent", 700),
        Place("Cascade Mountain", "WI", 43.5264, -89.4999, "Midwest", "Independent", 460),
        Place("Devil's Head", "WI", 43.4213, -89.6276, "Midwest", "Independent", 500),
        Place("Wilmot", "WI", 42.5049, -88.1862, "Midwest", "Epic", 240),
        Place("Little Switzerland", "WI", 43.5238, -88.1931, "Midwest", "Independent", 200),
        Place("Chestnut Mountain", "IL", 42.4900, -90.6416, "Midwest", "Independent", 475),
        Place("The Highlands", "MI", 45.4701, -84.9153, "Midwest", "Ikon", 552),
        Place("Nubs Nob", "MI", 45.4713, -84.9362, "Midwest", "Independent", 427),
        Place("Boyne Mountain", "MI", 45.1646, -84.9257, "Midwest", "Independent", 500),
        Place("Mount Bohemia", "MI", 47.3886, -88.0708, "Midwest", "Independent", 900),
        Place("Cannonsburg", "MI", 43.0555, -85.5547, "Midwest", "Independent", 250),
        Place("Crystal Mountain", "MI", 44.5203, -85.9943, "Midwest", "Independent", 375),
        Place("Afton Alps", "MN", 44.8596, -92.7845, "Midwest", "Epic", 350),
        Place("Buck Hill", "MN", 44.7996, -93.2880, "Midwest", "Independent", 309),
        Place("Lutsen Mountains", "MN", 47.6632, -90.7137, "Midwest", "Independent", 825),
        Place("Welch Village", "MN", 44.5627, -92.7261, "Midwest", "Independent", 360),
        Place("Spirit Mountain", "MN", 46.6939, -92.2200, "Midwest", "Independent", 700),
        Place("Perfect North", "IN", 39.1470, -84.8502, "Midwest", "Independent", 400),
        Place("Mad River Mountain", "OH", 40.3625, -83.6676, "Midwest", "Independent", 300),
        Place("Snow Trails", "OH", 40.6624, -82.5169, "Midwest", "Independent", 300),
        Place("Paoli Peaks", "IN", 38.5649, -86.4682, "Midwest", "Independent", 300),
        Place("Mount Holly", "MI", 42.8165, -83.6273, "Midwest", "Independent", 350),

        # Canada
        Place("Whistler Blackcomb", "BC", 50.1147, -122.9484, "Canada", "Epic", 5280),
        Place("Revelstoke", "BC", 50.9583, -118.1638, "Canada", "Ikon", 5620),
        Place("Sun Peaks", "BC", 50.8844, -119.8827, "Canada", "Ikon", 2894),
        Place("Big White", "BC", 49.7217, -118.9314, "Canada", "Independent", 2550),
        Place("SilverStar", "BC", 50.3700, -119.0585, "Canada", "Ikon", 2500),
        Place("Kicking Horse", "BC", 51.2970, -117.0475, "Canada", "Independent", 4314),
        Place("Fernie", "BC", 49.5040, -115.0766, "Canada", "Ikon", 3550),
        Place("Panorama", "BC", 50.4581, -116.2378, "Canada", "Ikon", 4000),
        Place("RED Mountain", "BC", 49.1013, -117.8462, "Canada", "Ikon", 2919),
        Place("Whitewater", "BC", 49.4733, -117.2936, "Canada", "Independent", 2044),
        Place("Apex Mountain", "BC", 49.3905, -119.9038, "Canada", "Independent", 2000),
        Place("Marmot Basin", "AB", 52.8015, -118.0816, "Canada", "Independent", 3000),
        Place("Lake Louise", "AB", 51.4413, -116.1617, "Canada", "Ikon", 3250),
        Place("Banff Sunshine", "AB", 51.15507, -115.68824, "Canada", "Ikon", 3514),
        Place("Mt Norquay", "AB", 51.2006, -115.5982, "Canada", "Ikon", 1650),
        Place("Nakiska", "AB", 50.94191, -115.15139, "Canada", "Independent", 2412),
        Place("Mont Tremblant", "QC", 46.2123, -74.5859, "Canada", "Ikon", 2116),
        Place("Le Massif", "QC", 47.2819, -70.5193, "Canada", "Independent", 2526),
        Place("Mont-Sainte-Anne", "QC", 47.0781, -70.9150, "Canada", "Ikon", 2050),
        Place("Stoneham", "QC", 47.0319, -71.3857, "Canada", "Independent", 1370),
        Place("Sutton", "QC", 45.1063, -72.5432, "Canada", "Independent", 1500),
        Place("Bromont", "QC", 45.3175, -72.6487, "Canada", "Independent", 1450),
        Place("Mont Orford", "QC", 45.3162, -72.2482, "Canada", "Independent", 1930),
        Place("Blue Mountain", "ON", 44.5067, -80.3130, "Canada", "Ikon", 720),
        Place("Castle Mountain", "AB", 49.31926, -114.41270, "Canada", "Independent", 2845),

        # Rockies
        Place("Jackson Hole", "WY", 43.5885, -110.8278, "Rockies", "Ikon", 4139),
        Place("Big Sky", "MT", 45.2847, -111.4015, "Rockies", "Ikon", 4350),
        Place("Bridger Bowl", "MT", 45.8177, -110.8970, "Rockies", "Independent", 2600),
        Place("Whitefish", "MT", 48.4817, -114.3581, "Rockies", "Ikon", 2353),
        Place("Discovery", "MT", 46.2461, -113.2574, "Rockies", "Independent", 2380),
        Place("Aspen Snowmass", "CO", 39.2097, -106.9498, "Rockies", "Ikon", 4406),
        Place("Winter Park", "CO", 39.8860, -105.7625, "Rockies", "Ikon", 3060),
        Place("Copper Mountain", "CO", 39.5022, -106.1518, "Rockies", "Ikon", 2738),
        Place("Steamboat", "CO", 40.4597, -106.8048, "Rockies", "Ikon", 3668),
        Place("Arapahoe Basin", "CO", 39.6425, -105.8717, "Rockies", "Ikon", 2530),
        Place("Eldora", "CO", 39.9381, -105.5847, "Rockies", "Ikon", 1600),
        Place("Vail", "CO", 39.6403, -106.3742, "Rockies", "Epic", 3450),
        Place("Breckenridge", "CO", 39.4817, -106.0384, "Rockies", "Epic", 3398),
        Place("Beaver Creek", "CO", 39.6042, -106.5167, "Rockies", "Epic", 3340),
        Place("Keystone", "CO", 39.5792, -105.9347, "Rockies", "Epic", 3128),
        Place("Crested Butte", "CO", 38.8995, -106.9658, "Rockies", "Epic", 3062),
        Place("Telluride", "CO", 37.9367, -107.8468, "Rockies", "Epic", 4425),
        Place("Monarch", "CO", 38.5120, -106.3328, "Rockies", "Independent", 1162),
        Place("Loveland", "CO", 39.6809, -105.8976, "Rockies", "Independent", 2210),
        Place("Purgatory", "CO", 37.6291, -107.8140, "Rockies", "Independent", 2029),
        Place("Wolf Creek", "CO", 37.4739, -106.7930, "Rockies", "Independent", 1604),
        Place("Sunlight", "CO", 39.3990, -107.3383, "Rockies", "Independent", 2010),
        Place("Powderhorn", "CO", 39.0697, -108.1508, "Rockies", "Independent", 1650),
        Place("Park City", "UT", 40.6514, -111.5079, "Rockies", "Epic", 3190),
        Place("Deer Valley", "UT", 40.6193, -111.4782, "Rockies", "Ikon", 3000),
        Place("Alta", "UT", 40.5883, -111.6377, "Rockies", "Ikon", 2538),
        Place("Snowbird", "UT", 40.5819, -111.6555, "Rockies", "Ikon", 3240),
        Place("Brighton", "UT", 40.61914, -111.78638, "Rockies", "Ikon", 1745),
        Place("Solitude", "UT", 40.61914, -111.78638, "Rockies", "Ikon", 2494),
        Place("Snowbasin", "UT", 41.2147, -111.8563, "Rockies", "Ikon", 2903),
        Place("Powder Mountain", "UT", 41.3792, -111.7817, "Rockies", "Independent", 3300),
        Place("Sundance", "UT", 40.3928, -111.5798, "Rockies", "Independent", 2150),
        Place("Brian Head", "UT", 37.6995, -112.8505, "Rockies", "Independent", 1320),
        Place("Grand Targhee", "WY", 43.7854, -110.9280, "Rockies", "Ikon", 2270),
        Place("Snow King", "WY", 43.4672, -110.7633, "Rockies", "Independent", 1571),
        Place("Targhee", "ID", 43.7854, -110.9280, "Rockies", "Ikon", 2270),
        Place("Sun Valley", "ID", 43.6970, -114.3513, "West", "Epic", 3400),
        Place("Schweitzer", "ID", 48.3695, -116.6233, "West", "Ikon", 2400),
        Place("Brundage", "ID", 45.0050, -116.1547, "West", "Independent", 1921),
        Place("Bogus Basin", "ID", 43.7641, -116.1024, "West", "Independent", 1800),
        Place("Silver Mountain", "ID", 47.4568, -115.7010, "West", "Independent", 2200),
        Place("Tamarack", "ID", 44.6696, -116.1159, "West", "Independent", 2800),
        Place("Pebble Creek", "ID", 42.7882, -112.1007, "West", "Independent", 2200),
        Place("Jackson Creek Summit", "NM", 36.3914, -105.4534, "Rockies", "Independent", 1700),
        Place("Taos", "NM", 36.5945, -105.4547, "Rockies", "Ikon", 3288),
        Place("Angel Fire", "NM", 36.3945, -105.2851, "Rockies", "Independent", 2077),
        Place("Ski Santa Fe", "NM", 35.7965, -105.7715, "Rockies", "Independent", 1725),
        Place("Sipapu", "NM", 36.1533, -105.5486, "Rockies", "Independent", 1055),
        Place("Pajarito", "NM", 35.8914, -106.3900, "Rockies", "Independent", 1410),
        Place("Lost Trail", "MT", 45.69240, -113.95188, "Rockies", "Independent", 1800),
        Place("Montana Snowbowl", "MT", 47.01375, -113.99969, "Rockies", "Independent", 2600),
        Place("Great Divide", "MT", 46.75271, -112.31335, "Rockies", "Independent", 1500),
        Place("Maverick Mountain", "MT", 45.43358, -113.12813, "Rockies", "Independent", 2020),
        Place("Red Lodge", "MT", 45.19085, -109.33536, "Rockies", "Independent", 2400),
        Place("Lookout Pass", "ID", 47.45652, -115.69688, "Rockies", "Independent", 1650),

        # West Coast / Sierra / PNW / Alaska
        Place("Palisades Tahoe", "CA", 39.1970, -120.2357, "West", "Ikon", 2850),
        Place("Mammoth Mountain", "CA", 37.6308, -119.0326, "West", "Ikon", 3100),
        Place("Heavenly", "CA", 38.9355, -119.9397, "West", "Epic", 3500),
        Place("Northstar", "CA", 39.2744, -120.1215, "West", "Epic", 2280),
        Place("Kirkwood", "CA", 38.6844, -120.0658, "West", "Epic", 2000),
        Place("June Mountain", "CA", 37.7663, -119.0756, "West", "Ikon", 2590),
        Place("Bear Mountain", "CA", 34.2300, -116.8608, "West", "Ikon", 1665),
        Place("Snow Summit", "CA", 34.2361, -116.8899, "West", "Ikon", 1209),
        Place("Alpine Meadows", "CA", 39.1653, -120.2388, "West", "Ikon", 1802),
        Place("Sierra-at-Tahoe", "CA", 38.8007, -120.0790, "West", "Independent", 2212),
        Place("Sugar Bowl", "CA", 39.3040, -120.3356, "West", "Independent", 1500),
        Place("Homewood", "CA", 39.0843, -120.1607, "West", "Independent", 1650),
        Place("Mt. Rose", "NV", 39.3281, -119.8856, "West", "Independent", 1800),
        Place("Diamond Peak", "NV", 39.2536, -119.9220, "West", "Independent", 1840),
        Place("Lee Canyon", "NV", 36.3034, -115.6769, "West", "Independent", 860),
        Place("Crystal Mountain", "WA", 46.9282, -121.4741, "West", "Ikon", 3100),
        Place("Stevens Pass", "WA", 47.7456, -121.0894, "West", "Epic", 1800),
        Place("Mt. Baker", "WA", 48.8577, -121.6642, "West", "Independent", 1500),
        Place("Mission Ridge", "WA", 47.2923, -120.3996, "West", "Independent", 2250),
        Place("49 Degrees North", "WA", 48.3017, -117.5555, "West", "Independent", 1851),
        Place("White Pass", "WA", 46.6375, -121.3916, "West", "Independent", 2050),
        Place("Mt. Spokane", "WA", 47.9213, -117.0966, "West", "Independent", 2000),
        Place("Mt. Hood Meadows", "OR", 45.3312, -121.6643, "West", "Independent", 2777),
        Place("Timberline", "OR", 45.3317, -121.7113, "West", "Ikon", 3690),
        Place("Skibowl", "OR", 45.3019, -121.7245, "West", "Independent", 1500),
        Place("Mt. Bachelor", "OR", 44.00338, -121.67853, "West", "Ikon", 3365),
        Place("Anthony Lakes", "OR", 44.9557, -118.2271, "West", "Independent", 900),
        Place("Bogus Basin", "OR", 43.7641, -116.1024, "West", "Independent", 1800),
        Place("Alyeska", "AK", 60.9604, -149.0962, "West", "Ikon", 2500),
    ]
    return pd.DataFrame([r.__dict__ for r in resorts])


def ors_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": api_key,
        "Accept": "application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8",
        "Content-Type": "application/json; charset=utf-8",
    }


def geocode_place(api_key: str, query: str) -> Tuple[float, float, str]:
    url = f"{ORS_BASE_URL}/geocode/search"
    params = {"api_key": api_key, "text": query, "size": 1}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    feats = data.get("features", [])
    if not feats:
        raise ValueError(f"Could not geocode '{query}'.")
    feat = feats[0]
    lon, lat = feat["geometry"]["coordinates"]
    label = feat["properties"].get("label", query)
    return lat, lon, label


def get_matrix(api_key: str, locations: List[List[float]], profile: str = DEFAULT_PROFILE) -> Dict:
    url = f"{ORS_BASE_URL}/v2/matrix/{profile}"
    payload = {"locations": locations, "metrics": ["distance", "duration"], "units": "mi"}
    resp = requests.post(url, headers=ors_headers(api_key), json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()


def get_directions(api_key: str, coordinates: List[List[float]], profile: str = DEFAULT_PROFILE) -> Dict:
    client = openrouteservice.Client(key=api_key)
    return client.directions(
        coordinates=coordinates,
        profile=profile,
        format="json",
        instructions=True,
        radiuses=[5000] * len(coordinates),
    )


def get_open_meteo_forecast(lat: float, lon: float) -> Dict[str, float]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "snowfall,temperature_2m,wind_speed_10m",
        "forecast_days": 3,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    hourly = data.get("hourly", {})
    snowfall = hourly.get("snowfall", []) or []
    temps = hourly.get("temperature_2m", []) or []
    winds = hourly.get("wind_speed_10m", []) or []

    snowfall_24h = round(sum(snowfall[:24]), 2) if snowfall else 0.0
    snowfall_48h = round(sum(snowfall[:48]), 2) if snowfall else 0.0
    avg_temp_24h = round(sum(temps[:24]) / min(len(temps), 24), 1) if temps else 32.0
    max_wind_24h = round(max(winds[:24]), 1) if winds else 0.0

    return {
        "snowfall_24h_in": snowfall_24h,
        "snowfall_48h_in": snowfall_48h,
        "avg_temp_24h_f": avg_temp_24h,
        "max_wind_24h_mph": max_wind_24h,
    }


def temp_score(temp_f: float) -> float:
    if temp_f <= 5:
        return 4.0
    if temp_f <= 15:
        return 8.0
    if temp_f <= 28:
        return 10.0
    if temp_f <= 34:
        return 7.0
    if temp_f <= 40:
        return 4.0
    return 1.0


def wind_penalty(wind_mph: float) -> float:
    if wind_mph <= 10:
        return 0.0
    if wind_mph <= 20:
        return 1.0
    if wind_mph <= 30:
        return 3.0
    if wind_mph <= 40:
        return 6.0
    return 10.0


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def trim_resorts_for_matrix(filtered: pd.DataFrame, start_lat: float, start_lon: float, max_candidates: int = 55) -> pd.DataFrame:
    trimmed = filtered.copy()
    trimmed["air_miles_from_start"] = trimmed.apply(
        lambda r: round(haversine_miles(start_lat, start_lon, r["lat"], r["lon"]), 1),
        axis=1,
    )
    trimmed = trimmed.sort_values(["air_miles_from_start", "vertical_ft"], ascending=[True, False]).reset_index(drop=True)
    if len(trimmed) > max_candidates:
        removed = trimmed.iloc[max_candidates:].copy()
        kept = trimmed.iloc[:max_candidates].copy()
        st.warning(
            f"Too many candidate resorts for the OpenRouteService matrix limit. Keeping the {max_candidates} closest resorts by straight-line distance and dropping {len(removed)} others."
        )
        with st.expander("Dropped resorts due to matrix-size limit"):
            st.dataframe(
                removed[["name", "state", "region", "pass_type", "air_miles_from_start"]],
                width="stretch",
                hide_index=True,
            )
        return kept
    return trimmed


def compute_resort_scores(filtered: pd.DataFrame, durations: List[List[float]]) -> pd.DataFrame:
    scored = filtered.copy().reset_index(drop=True)
    drive_hours = []
    is_routable = []
    unroutable_names = []

    for i in range(len(scored)):
        seconds = durations[0][i + 1]
        if seconds is None:
            drive_hours.append(None)
            is_routable.append(False)
            unroutable_names.append(scored.iloc[i]["name"])
        else:
            drive_hours.append(round(seconds / 3600.0, 2))
            is_routable.append(True)

    if unroutable_names:
        st.warning(f"Unroutable resorts removed ({len(unroutable_names)}):")
        st.write(sorted(unroutable_names))

    scored["drive_hours_from_start"] = drive_hours
    scored["is_routable"] = is_routable
    scored = scored[scored["is_routable"]].copy()

    scored["trip_score"] = (
        4.0 * scored["snowfall_48h_in"]
        + 1.5 * scored["snowfall_24h_in"]
        + 0.004 * scored["vertical_ft"]
        + scored["temp_component"]
        - 2.0 * scored["drive_hours_from_start"]
        - scored["wind_penalty"]
    )
    scored["trip_score"] = scored["trip_score"].round(2)
    return scored.sort_values(["trip_score", "snowfall_48h_in", "vertical_ft"], ascending=[False, False, False]).reset_index(drop=True)


def get_available_solver() -> str:
    for name in ["appsi_highs", "highs", "cbc", "glpk"]:
        try:
            solver = pyo.SolverFactory(name)
            if solver is not None and solver.available(exception_flag=False):
                return name
        except Exception:
            pass
    raise RuntimeError("No MILP solver found. Install one with: pip install pyomo highspy")


def solve_itinerary_pyomo(
    filtered: pd.DataFrame,
    durations: List[List[float]],
    max_stops: int,
    max_daily_drive_hours: float,
    include_return_home: bool,
) -> Tuple[List[int], bool]:
    n = len(filtered)
    if n == 0:
        return [0], False

    days = list(range(1, max_stops + 1))
    resorts = list(range(1, n + 1))
    transition_days = list(range(2, max_stops + 1))
    max_daily_seconds = max_daily_drive_hours * 3600.0

    score = {i: float(filtered.iloc[i - 1]["trip_score"]) for i in resorts}
    start_drive = {i: durations[0][i] for i in resorts}
    return_drive = {i: durations[i][0] for i in resorts}

    allowed_start = [i for i in resorts if start_drive[i] is not None and start_drive[i] <= max_daily_seconds]
    allowed_pairs = [
        (i, j)
        for i in resorts
        for j in resorts
        if i != j and durations[i][j] is not None and durations[i][j] <= max_daily_seconds
    ]
    allowed_return = [i for i in resorts if return_drive[i] is not None and return_drive[i] <= max_daily_seconds]

    if not allowed_start:
        raise ValueError("No resort can be reached from the starting location within your daily drive limit.")
    if include_return_home and not allowed_return:
        raise ValueError("No resort can return home within your daily drive limit. Increase the limit or disable return home.")

    model = pyo.ConcreteModel()
    model.R = pyo.Set(initialize=resorts)
    model.D = pyo.Set(initialize=days)
    model.DT = pyo.Set(initialize=transition_days)
    model.S = pyo.Set(initialize=allowed_start)
    model.P = pyo.Set(initialize=allowed_pairs, dimen=2)
    model.RH = pyo.Set(initialize=allowed_return)

    model.z = pyo.Var(model.R, model.D, domain=pyo.Binary)
    model.a = pyo.Var(model.D, domain=pyo.Binary)
    model.x = pyo.Var(model.P, model.DT, domain=pyo.Binary)
    model.f = pyo.Var(model.D, domain=pyo.Binary)
    model.rf = pyo.Var(model.R, model.D, domain=pyo.Binary)

    def one_resort_per_day_rule(m, d):
        return sum(m.z[i, d] for i in m.R) == m.a[d]
    model.one_resort_per_day = pyo.Constraint(model.D, rule=one_resort_per_day_rule)

    def contiguous_days_rule(m, d):
        if d == max_stops:
            return pyo.Constraint.Skip
        return m.a[d] >= m.a[d + 1]
    model.contiguous_days = pyo.Constraint(model.D, rule=contiguous_days_rule)

    def each_resort_at_most_once_rule(m, i):
        return sum(m.z[i, d] for d in m.D) <= 1
    model.each_resort_at_most_once = pyo.Constraint(model.R, rule=each_resort_at_most_once_rule)

    def day1_allowed_rule(m):
        return sum(m.z[i, 1] for i in m.S) == m.a[1]
    model.day1_allowed = pyo.Constraint(rule=day1_allowed_rule)

    def day1_disallowed_rule(m, i):
        if i in allowed_start:
            return pyo.Constraint.Skip
        return m.z[i, 1] == 0
    model.day1_disallowed = pyo.Constraint(model.R, rule=day1_disallowed_rule)

    def transition_count_rule(m, d):
        return sum(m.x[i, j, d] for (i, j) in m.P) == m.a[d]
    model.transition_count = pyo.Constraint(model.DT, rule=transition_count_rule)

    def transition_from_prev_rule(m, i, d):
        outgoing = sum(m.x[i, j, d] for (ii, j) in m.P if ii == i)
        return outgoing <= m.z[i, d - 1]
    model.transition_from_prev = pyo.Constraint(model.R, model.DT, rule=transition_from_prev_rule)

    def transition_to_curr_rule(m, j, d):
        incoming = sum(m.x[i, j, d] for (i, jj) in m.P if jj == j)
        return incoming <= m.z[j, d]
    model.transition_to_curr = pyo.Constraint(model.R, model.DT, rule=transition_to_curr_rule)

    def transition_prev_exact_rule(m, i, d):
        outgoing = sum(m.x[i, j, d] for (ii, j) in m.P if ii == i)
        return outgoing == m.z[i, d - 1] + m.f[d - 1] - m.a[d - 1]
    model.transition_prev_exact = pyo.Constraint(model.R, model.DT, rule=transition_prev_exact_rule)

    def transition_curr_exact_rule(m, j, d):
        incoming = sum(m.x[i, j, d] for (i, jj) in m.P if jj == j)
        return incoming == m.z[j, d]
    model.transition_curr_exact = pyo.Constraint(model.R, model.DT, rule=transition_curr_exact_rule)

    def one_final_day_rule(m):
        return sum(m.f[d] for d in m.D) == sum(m.a[d] for d in m.D)
    model.one_final_day = pyo.Constraint(rule=one_final_day_rule)

    def final_day_only_if_active_rule(m, d):
        return m.f[d] <= m.a[d]
    model.final_day_only_if_active = pyo.Constraint(model.D, rule=final_day_only_if_active_rule)

    def final_day_matches_last_active_rule(m, d):
        if d == max_stops:
            return pyo.Constraint.Skip
        return m.f[d] >= m.a[d] - m.a[d + 1]
    model.final_day_matches_last_active = pyo.Constraint(model.D, rule=final_day_matches_last_active_rule)

    if include_return_home:
        def return_feasible_rule(m, d):
            return sum(m.z[i, d] for i in m.RH) >= m.f[d]
        model.return_feasible = pyo.Constraint(model.D, rule=return_feasible_rule)

        def final_resort_upper_z_rule(m, i, d):
            return m.rf[i, d] <= m.z[i, d]
        model.final_resort_upper_z = pyo.Constraint(model.R, model.D, rule=final_resort_upper_z_rule)

        def final_resort_upper_f_rule(m, i, d):
            return m.rf[i, d] <= m.f[d]
        model.final_resort_upper_f = pyo.Constraint(model.R, model.D, rule=final_resort_upper_f_rule)

        def final_resort_lower_rule(m, i, d):
            return m.rf[i, d] >= m.z[i, d] + m.f[d] - 1
        model.final_resort_lower = pyo.Constraint(model.R, model.D, rule=final_resort_lower_rule)

        def one_final_resort_rule(m):
            return sum(m.rf[i, d] for i in m.R for d in m.D) == sum(m.f[d] for d in m.D)
        model.one_final_resort = pyo.Constraint(rule=one_final_resort_rule)

    def objective_rule(m):
        resort_value = sum(score[i] * m.z[i, d] for i in m.R for d in m.D)
        start_penalty = sum((start_drive[i] / 3600.0) * m.z[i, 1] for i in m.S)
        transition_penalty = sum((durations[i][j] / 3600.0) * m.x[i, j, d] for (i, j) in m.P for d in m.DT)
        return_penalty = 0.0
        if include_return_home:
            return_penalty = sum((return_drive[i] / 3600.0) * m.rf[i, d] for i in m.RH for d in m.D)
        day_bonus = 0.25 * sum(m.a[d] for d in m.D)
        return resort_value - 1.75 * start_penalty - 1.75 * transition_penalty - 1.25 * return_penalty + day_bonus
    model.obj = pyo.Objective(rule=objective_rule, sense=pyo.maximize)

    solver_name = get_available_solver()
    solver = pyo.SolverFactory(solver_name)
    results = solver.solve(model, tee=False)

    status = results.solver.status
    termination = results.solver.termination_condition
    feasible_terminations = {
        pyo.TerminationCondition.optimal,
        pyo.TerminationCondition.feasible,
        pyo.TerminationCondition.locallyOptimal,
    }
    if status not in {pyo.SolverStatus.ok, pyo.SolverStatus.warning} or termination not in feasible_terminations:
        raise RuntimeError(f"MILP solve failed. Solver={solver_name}, status={status}, termination={termination}")

    visit_order = [0]
    used_return_day = False
    for d in days:
        if pyo.value(model.a[d]) < 0.5:
            continue
        chosen = [i for i in resorts if pyo.value(model.z[i, d]) > 0.5]
        if chosen:
            visit_order.append(chosen[0])
        if include_return_home and pyo.value(model.f[d]) > 0.5:
            used_return_day = True
    return visit_order, used_return_day


def build_line_layer(route_segments_df: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "PathLayer",
        data=route_segments_df,
        get_path="path",
        get_width=8,
        width_min_pixels=3,
        get_color="color",
        pickable=True,
    )


def build_scatter_layer(points_df: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "ScatterplotLayer",
        data=points_df,
        get_position="[lon, lat]",
        get_radius="radius",
        radius_min_pixels=2,
        radius_max_pixels=8,
        get_fill_color="color",
        get_line_color=[40, 40, 40],
        get_line_width=1,
        stroked=True,
        pickable=True,
        auto_highlight=True,
    )


def point_tooltip_html(row: pd.Series) -> str:
    parts = [
        f"<b>{row.get('name', '')}</b>",
        f"Type: {row.get('kind', '')}",
    ]
    if pd.notna(row.get("state")) and row.get("state") != "":
        parts.append(f"State/Province: {row.get('state')}")
    if pd.notna(row.get("pass_type")) and row.get("pass_type") != "":
        parts.append(f"Pass: {row.get('pass_type')}")
    if pd.notna(row.get("vertical_ft")):
        parts.append(f"Vertical: {int(row.get('vertical_ft'))} ft")
    if pd.notna(row.get("snowfall_24h_in")):
        parts.append(f"Snow next 24h: {float(row.get('snowfall_24h_in')):.1f} in")
    if pd.notna(row.get("snowfall_48h_in")):
        parts.append(f"Snow next 48h: {float(row.get('snowfall_48h_in')):.1f} in")
    if pd.notna(row.get("avg_temp_24h_f")):
        parts.append(f"Avg temp next 24h: {float(row.get('avg_temp_24h_f')):.1f} F")
    if pd.notna(row.get("trip_score")):
        parts.append(f"Trip score: {float(row.get('trip_score')):.2f}")
    return "<br/>".join(parts)


def build_points_for_map(ordered_points: List[Dict], start_label: str, start_lat: float, start_lon: float, include_return_home: bool) -> pd.DataFrame:
    points_for_map = pd.DataFrame(ordered_points)
    if include_return_home:
        return_row = pd.DataFrame([
            {
                "name": start_label,
                "lat": start_lat,
                "lon": start_lon,
                "kind": "Return",
                "state": "",
                "pass_type": "",
                "vertical_ft": None,
                "snowfall_24h_in": None,
                "snowfall_48h_in": None,
                "avg_temp_24h_f": None,
                "trip_score": None,
                "radius": 2500,
                "color": [220, 80, 80],
            }
        ])
        return_row["tooltip_html"] = return_row.apply(point_tooltip_html, axis=1)
        points_for_map = pd.concat([points_for_map, return_row], ignore_index=True)

    points_for_map["tooltip_html"] = points_for_map.apply(point_tooltip_html, axis=1)
    return points_for_map


def build_route_segments_from_directions(api_key: str, legs: List[Dict], trip_coordinates: List[List[float]], profile: str = DEFAULT_PROFILE) -> pd.DataFrame:
    segments = []
    for i, leg in enumerate(legs):
        if i + 1 >= len(trip_coordinates):
            continue
        pair_coords = [trip_coordinates[i], trip_coordinates[i + 1]]
        try:
            leg_directions = get_directions(api_key, pair_coords, profile=profile)
            leg_route = leg_directions["routes"][0]
            decoded = convert.decode_polyline(leg_route["geometry"])
            path = decoded["coordinates"]
        except Exception:
            path = pair_coords

        tooltip_parts = [
            f"<b>Day {leg['day']}</b>",
            f"Leg: {leg['from']} → {leg['to']}",
            f"Drive time: {leg['drive_hours']} h",
            f"Distance: {leg['miles']} mi",
        ]
        if leg.get("snowfall_24h_in") is not None:
            tooltip_parts.append(f"Snow next 24h: {float(leg['snowfall_24h_in']):.1f} in")
        if leg.get("snowfall_48h_in") is not None:
            tooltip_parts.append(f"Snow next 48h: {float(leg['snowfall_48h_in']):.1f} in")
        if leg.get("avg_temp_24h_f") is not None:
            tooltip_parts.append(f"Avg temp next 24h: {float(leg['avg_temp_24h_f']):.1f} F")
        if leg.get("trip_score") is not None:
            tooltip_parts.append(f"Trip score: {float(leg['trip_score']):.2f}")

        segments.append(
            {
                "path": path,
                "day": leg["day"],
                "from": leg["from"],
                "to": leg["to"],
                "drive_hours": leg["drive_hours"],
                "miles": leg["miles"],
                "snowfall_24h_in": leg.get("snowfall_24h_in"),
                "snowfall_48h_in": leg.get("snowfall_48h_in"),
                "avg_temp_24h_f": leg.get("avg_temp_24h_f"),
                "trip_score": leg.get("trip_score"),
                "tooltip_html": "<br/>".join(tooltip_parts),
                "color": [40, 110, 240],
            }
        )
    return pd.DataFrame(segments)


def main() -> None:
    st.set_page_config(page_title="Ski Road Trip Planner", layout="wide")
    st.title("Ski Road Trip Planner")
    st.caption("Plan multi-stop ski trips with routing, snowfall forecasts, and a Pyomo MILP itinerary model")

    api_key = ORS_API_KEY
    if not api_key or api_key == "your_openrouteservice_key":
        st.warning("Set ORS_API_KEY to your real openrouteservice key before using this app.")

    resorts_df = load_resorts()

    with st.sidebar:
        st.header("Trip inputs")
        start_location = st.text_input("Starting location", value="Boston, MA")
        region = st.multiselect("Regions", sorted(resorts_df["region"].unique().tolist()), default=["Northeast"])
        pass_filter = st.multiselect(
            "Pass type",
            sorted(resorts_df["pass_type"].unique().tolist()),
            default=sorted(resorts_df["pass_type"].unique().tolist()),
        )
        max_stops = st.slider("Number of ski days", min_value=1, max_value=8, value=4)
        max_daily_drive_hours = st.slider("Max daily drive hours", min_value=2.0, max_value=12.0, value=5.0, step=0.5)
        min_vertical = st.slider("Minimum vertical drop (ft)", min_value=1000, max_value=4500, value=1500, step=100)
        include_return_home = st.checkbox("Include drive back to start", value=True)
        plan_button = st.button("Plan trip", type="primary")

    filtered = resorts_df[
        resorts_df["region"].isin(region)
        & resorts_df["pass_type"].isin(pass_filter)
        & (resorts_df["vertical_ft"] >= min_vertical)
    ].copy().reset_index(drop=True)

    st.subheader("Candidate resorts")
    st.dataframe(
        filtered[["name", "state", "region", "pass_type", "vertical_ft"]].sort_values(["region", "vertical_ft"], ascending=[True, False]),
        width="stretch",
        hide_index=True,
    )

    if not plan_button:
        st.info("Choose filters on the left, then click Plan trip.")
        return

    if not api_key or api_key == "your_openrouteservice_key":
        st.error("Missing valid ORS_API_KEY. Set your real API key and restart the app.")
        st.stop()

    if filtered.empty:
        st.error("No resorts match your filters.")
        st.stop()

    try:
        with st.spinner("Geocoding start location..."):
            start_lat, start_lon, start_label = geocode_place(api_key, start_location)

        filtered = trim_resorts_for_matrix(filtered, start_lat, start_lon, max_candidates=55)

        with st.spinner("Pulling snowfall forecast data..."):
            weather_rows = []
            for _, row in filtered.iterrows():
                weather_rows.append(get_open_meteo_forecast(row["lat"], row["lon"]))
            weather_df = pd.DataFrame(weather_rows)
            filtered = pd.concat([filtered.reset_index(drop=True), weather_df], axis=1)
            filtered["temp_component"] = filtered["avg_temp_24h_f"].apply(temp_score)
            filtered["wind_penalty"] = filtered["max_wind_24h_mph"].apply(wind_penalty)

        matrix_locs = [[start_lon, start_lat]] + filtered[["lon", "lat"]].apply(lambda r: [r["lon"], r["lat"]], axis=1).tolist()
        with st.spinner("Computing drive matrix..."):
            matrix = get_matrix(api_key, matrix_locs, profile=DEFAULT_PROFILE)
        durations = matrix["durations"]
        distances = matrix["distances"]

        filtered = compute_resort_scores(filtered, durations)
        if filtered.empty:
            st.error("No routable resorts were found from your starting location with the current filters.")
            st.stop()

        matrix_locs = [[start_lon, start_lat]] + filtered[["lon", "lat"]].apply(lambda r: [r["lon"], r["lat"]], axis=1).tolist()
        matrix = get_matrix(api_key, matrix_locs, profile=DEFAULT_PROFILE)
        durations = matrix["durations"]
        distances = matrix["distances"]

        with st.spinner("Solving itinerary MILP..."):
            visit_order, used_return_day = solve_itinerary_pyomo(
                filtered,
                durations,
                max_stops=max_stops,
                max_daily_drive_hours=max_daily_drive_hours,
                include_return_home=include_return_home,
            )

        if len(visit_order) <= 1:
            st.error("The MILP solver did not find a feasible ski itinerary with the current settings.")
            st.stop()

        ordered_points = [{
            "name": start_label,
            "lat": start_lat,
            "lon": start_lon,
            "kind": "Start",
            "state": "",
            "pass_type": "",
            "vertical_ft": None,
            "snowfall_24h_in": None,
            "snowfall_48h_in": None,
            "avg_temp_24h_f": None,
            "trip_score": None,
            "radius": 3200,
            "color": [30, 180, 30],
        }]

        for idx in visit_order[1:]:
            row = filtered.iloc[idx - 1]
            ordered_points.append({
                "name": row["name"],
                "lat": row["lat"],
                "lon": row["lon"],
                "kind": "Selected Resort",
                "state": row["state"],
                "pass_type": row["pass_type"],
                "vertical_ft": row["vertical_ft"],
                "snowfall_24h_in": row["snowfall_24h_in"],
                "snowfall_48h_in": row["snowfall_48h_in"],
                "avg_temp_24h_f": row["avg_temp_24h_f"],
                "trip_score": row["trip_score"],
                "radius": 2200,
                "color": [30, 30, 200],
            })

        trip_coordinates = [[pt["lon"], pt["lat"]] for pt in ordered_points]
        if include_return_home:
            trip_coordinates.append([start_lon, start_lat])

        legs = []
        for day_num in range(1, len(visit_order)):
            from_idx = visit_order[day_num - 1]
            to_idx = visit_order[day_num]
            from_name = start_label if from_idx == 0 else filtered.iloc[from_idx - 1]["name"]
            to_row = filtered.iloc[to_idx - 1]
            to_name = to_row["name"]
            leg_seconds = durations[from_idx][to_idx]
            leg_miles = distances[from_idx][to_idx]
            legs.append({
                "day": day_num,
                "from": from_name,
                "to": to_name,
                "drive_hours": round(leg_seconds / 3600.0, 2),
                "miles": round(leg_miles, 1),
                "snowfall_24h_in": round(float(to_row["snowfall_24h_in"]), 2),
                "snowfall_48h_in": round(float(to_row["snowfall_48h_in"]), 2),
                "avg_temp_24h_f": round(float(to_row["avg_temp_24h_f"]), 1),
                "trip_score": round(float(to_row["trip_score"]), 2),
            })

        if include_return_home:
            last_idx = visit_order[-1]
            return_seconds = durations[last_idx][0]
            return_miles = distances[last_idx][0]
            if return_seconds is not None:
                return_hours = return_seconds / 3600.0
                return_day = (legs[-1]["day"] + 1) if used_return_day and legs else 1
                legs.append({
                    "day": return_day,
                    "from": filtered.iloc[last_idx - 1]["name"],
                    "to": start_label,
                    "drive_hours": round(return_hours, 2),
                    "miles": round(return_miles, 1),
                    "snowfall_24h_in": None,
                    "snowfall_48h_in": None,
                    "avg_temp_24h_f": None,
                    "trip_score": None,
                })

        with st.spinner("Fetching route geometry..."):
            directions = get_directions(api_key, trip_coordinates, profile=DEFAULT_PROFILE)
        route = directions["routes"][0]
        summary = route["summary"]
        decoded = convert.decode_polyline(route["geometry"])
        route_coords = decoded["coordinates"]

    except requests.exceptions.HTTPError as e:
        detail = ""
        if getattr(e, "response", None) is not None:
            try:
                detail = e.response.text[:700]
            except Exception:
                detail = str(e)
        st.error(f"Request failed: {e}")
        if detail:
            st.code(detail)
        st.stop()
    except openrouteservice.exceptions.ApiError as e:
        st.error(f"OpenRouteService directions failed: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Trip planning failed: {e}")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Planned ski resorts", len(visit_order) - 1)
    c2.metric("Total drive hours", f"{summary['duration'] / 3600:.1f}")
    c3.metric("Total miles", f"{summary['distance'] / 1609.344:.0f}")
    c4.metric("Top resort score", f"{filtered.iloc[0]['trip_score']:.1f}")

    st.subheader("Best resorts right now")
    resort_rank_df = filtered[[
        "name", "state", "pass_type", "vertical_ft", "snowfall_24h_in", "snowfall_48h_in",
        "avg_temp_24h_f", "max_wind_24h_mph", "drive_hours_from_start", "trip_score"
    ]].copy()
    st.dataframe(resort_rank_df, width="stretch", hide_index=True)

    st.subheader("Recommended itinerary")
    itinerary_df = pd.DataFrame(legs)
    st.dataframe(itinerary_df, width="stretch", hide_index=True)

    st.subheader("Day-by-day itinerary")
    st.caption("At most one ski resort is scheduled per day. When return home is enabled, the model requires the final resort to have a feasible drive home within your daily limit, and the app always places that return on its own extra day.")
    for day in sorted(itinerary_df["day"].unique().tolist()):
        day_legs = itinerary_df[itinerary_df["day"] == day]
        day_drive = day_legs["drive_hours"].sum()
        with st.expander(f"Day {day} - {day_drive:.1f} drive hours", expanded=(day == 1)):
            for _, leg in day_legs.iterrows():
                if leg["to"] == start_label:
                    st.markdown(f"- Drive **{leg['drive_hours']:.1f}h** / **{leg['miles']:.0f} mi** back to **{leg['to']}**")
                else:
                    st.markdown(
                        f"- Drive **{leg['drive_hours']:.1f}h** / **{leg['miles']:.0f} mi** to **{leg['to']}**  \n"
                        f"  Forecast: **{leg['snowfall_24h_in']:.1f}\"** next 24h, **{leg['snowfall_48h_in']:.1f}\"** next 48h, avg **{leg['avg_temp_24h_f']:.0f}F**, score **{leg['trip_score']:.1f}**"
                    )

    points_for_map = build_points_for_map(ordered_points, start_label, start_lat, start_lon, include_return_home)
    route_segments_df = build_route_segments_from_directions(api_key, legs, trip_coordinates, profile=DEFAULT_PROFILE)
    considered_points = filtered.copy()
    selected_names = set([pt["name"] for pt in ordered_points if pt["kind"] == "Selected Resort"])
    considered_points["kind"] = considered_points["name"].apply(lambda n: "Selected Resort" if n in selected_names else "Candidate Resort")
    considered_points["radius"] = considered_points["name"].apply(lambda n: 2200 if n in selected_names else 1200)
    considered_points["color"] = considered_points["name"].apply(lambda n: [30, 30, 200] if n in selected_names else [130, 130, 130])

    def considered_point_tooltip_html(row: pd.Series) -> str:
        parts = [
            f"<b>{row.get('name', '')}</b>",
            f"Type: {row.get('kind', '')}",
            f"State/Province: {row.get('state', '')}",
            f"Pass: {row.get('pass_type', '')}",
            f"Vertical: {int(row.get('vertical_ft'))} ft" if pd.notna(row.get('vertical_ft')) else None,
            f"Snow next 24h: {float(row.get('snowfall_24h_in')):.1f} in" if pd.notna(row.get('snowfall_24h_in')) else None,
            f"Snow next 48h: {float(row.get('snowfall_48h_in')):.1f} in" if pd.notna(row.get('snowfall_48h_in')) else None,
            f"Avg temp next 24h: {float(row.get('avg_temp_24h_f')):.1f} F" if pd.notna(row.get('avg_temp_24h_f')) else None,
            f"Trip score: {float(row.get('trip_score')):.2f}" if pd.notna(row.get('trip_score')) else None,
        ]
        return "<br/>".join([p for p in parts if p])

    considered_points["tooltip_html"] = considered_points.apply(considered_point_tooltip_html, axis=1)

    def align_map_columns(df: pd.DataFrame) -> pd.DataFrame:
        cols = [
            "name", "lat", "lon", "kind", "state", "pass_type", "vertical_ft",
            "snowfall_24h_in", "snowfall_48h_in", "avg_temp_24h_f", "trip_score",
            "radius", "color", "tooltip_html",
        ]
        out = df.copy()
        for c in cols:
            if c not in out.columns:
                out[c] = None
        out = out[cols]
        numeric_cols = ["lat", "lon", "vertical_ft", "snowfall_24h_in", "snowfall_48h_in", "avg_temp_24h_f", "trip_score", "radius"]
        for c in numeric_cols:
            out[c] = pd.to_numeric(out[c], errors="coerce")
        out["state"] = out["state"].fillna("")
        out["pass_type"] = out["pass_type"].fillna("")
        out["kind"] = out["kind"].fillna("")
        out["tooltip_html"] = out["tooltip_html"].fillna("")
        return out

    map_points = pd.concat(
        [align_map_columns(considered_points), align_map_columns(points_for_map)],
        ignore_index=True,
    ).drop_duplicates(subset=["name", "kind", "lat", "lon"])

    avg_lat = map_points["lat"].mean()
    avg_lon = map_points["lon"].mean()

    st.subheader("Map")
    st.caption("Blue nodes are selected resorts. Gray nodes are other candidate resorts that were considered.")
    deck = pdk.Deck(
        map_provider="carto",
        map_style="light",
        initial_view_state=pdk.ViewState(latitude=avg_lat, longitude=avg_lon, zoom=5, pitch=0),
        layers=[build_line_layer(route_segments_df), build_scatter_layer(map_points)],
        tooltip={
            "html": "{tooltip_html}",
            "style": {"backgroundColor": "white", "color": "black", "fontSize": "12px"},
        },
    )
    st.pydeck_chart(deck, width="stretch")

    st.subheader("How the model works")
    st.markdown(
        """
        Resorts are scored using forecast snowfall, temperature, wind, vertical drop, and drive time from the start.

        After scoring, the app keeps at most the nearest 55 resorts and solves a day-indexed Pyomo MILP:
        - each day can have at most one ski resort
        - each resort can be visited at most once
        - days are contiguous from day 1 onward
        - day 1 drive must fit the max daily drive limit
        - each inter-day resort-to-resort drive must fit the max daily drive limit
        - if return home is enabled, the final chosen resort must also be able to return home within the max daily drive limit
        - the return drive is placed on its own extra day after the final ski day
        - the objective maximizes total resort score minus driving penalties

        """
    )


if __name__ == "__main__":
    main()
