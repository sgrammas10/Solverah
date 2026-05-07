"""Geographic utility helpers (currently stubbed).

These functions were used for geocoding city strings to (lat, lon) coordinates
and computing straight-line distances via the Haversine formula.  They are
commented out pending a decision on which geocoder provider to use in production
(Nominatim has rate-limit / ToS constraints for commercial services; alternatives
include the Google Maps Geocoding API or Mapbox).

To re-enable:
  1. Install geopy: ``pip install geopy``
  2. Choose a production-safe geocoder backend.
  3. Uncomment the implementations below.
  4. Import and call from app.py where location-based filtering is needed.
"""

# from geopy.geocoders import Nominatim

# _geolocator = Nominatim(user_agent="solverah-app")

# def geocode_city(city_string: str):
#   """
#   city_string like 'Annapolis, MD' -> (lat, lon) or None
#   """
#   loc = _geolocator.geocode(city_string)
#   if not loc:
#     return None
#   return (loc.latitude, loc.longitude)

# import math

# def haversine_miles(lat1, lon1, lat2, lon2):
#     R = 3958.8  # radius of Earth in miles
#     phi1 = math.radians(lat1)
#     phi2 = math.radians(lat2)
#     dphi = math.radians(lat2 - lat1)
#     dlambda = math.radians(lon2 - lon1)

#     a = math.sin(dphi / 2.0) ** 2 + \
#         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2

#     c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
#     return R * c