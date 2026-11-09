"""Template for /secrets.py on the board flash — copy, fill in, upload, delete.

    cp secrets.example.py secrets.py   # edit secrets.py with real values
    mpremote cp secrets.py :secrets.py  # host -> board ONLY
    rm secrets.py                      # keep the board as the only copy

secrets.py is gitignored: never commit it, never read or print it, and never
`mpremote cp :secrets.py ...` it back off the board.
"""

# WiFi (the Pico W is 2.4 GHz only)
WIFI_SSID = "your-ssid"
WIFI_PASSWORD = "your-password"

# Location for the open-meteo forecast, decimal degrees
LOCATION_LAT = 52.2297
LOCATION_LON = 21.0122

# open-meteo timezone name, e.g. "Europe/Warsaw". The clock applies EU DST
# rules only to "Europe/*" names (src/tz.py); anything else shows UTC.
TZ = "Europe/Warsaw"

# Optional: SCD41 altitude in meters, used for CO2 pressure compensation.
# Omit the line (or set 0) to disable compensation.
SCD41_ALTITUDE_M = 470

# Optional: Spotify now-playing screen. Fill both (or omit both to disable
# the screen -- main.py sets SPOTIFY_ENABLED=False). SPOTIFY_REFRESH_TOKEN is
# the long-lived token minted once on a PC (README "Spotify now-playing"); the
# board mints a fresh 1h access token from it via the refresh grant. The
# Spotify app is a public (no client secret) client, so only the client id and
# the refresh token are needed on the board.
SPOTIFY_CLIENT_ID = "your-client-id"
SPOTIFY_REFRESH_TOKEN = "your-refresh-token"
