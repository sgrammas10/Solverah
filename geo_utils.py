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