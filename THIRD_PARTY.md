# Third-party data and code

## Milan civic address index

`casa_watch/assets/milan-addresses.json` is a transformed, reduced index of the Comune di Milano dataset **Numeri civici con coordinate geografiche**, dated 2026-09-01. It contains street-address coordinates, not property listings or personal details.

- Publisher: Comune di Milano, Unità Analytics e Open Data
- Dataset: https://dati.comune.milano.it/dataset/ds634-numeri-civici-coordinate
- Resource: https://dati.comune.milano.it/dataset/ds634-numeri-civici-coordinate/resource/533b4e63-3d78-4bb5-aeb4-6c5f648f7f21
- Licence: Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/
- Modifications: retain active residential civic numbers; remove unrelated fields; normalize street aliases; retain WGS84 latitude/longitude. Ambiguous aliases are discarded. Rebuild with `python tools/build_address_index.py downloaded.zip`.

Location matching is inferred from an address in the opening advert text. It is not a property survey. No street centroids or city-centre fallback pins are used; ambiguous, missing or unmatched addresses stay unlocated. Radius/polygon filters exclude them.

## Leaflet 1.9.4

Vendored in `casa_watch/web/vendor`, from the official Leaflet npm distribution. BSD 2-Clause licence: see `LEAFLET-LICENSE.txt`. Project: https://leafletjs.com/

## OpenStreetMap

Map tiles load from `https://tile.openstreetmap.org/{z}/{x}/{y}.png` for the visible viewport only. Attribution appears on the map. Map data © OpenStreetMap contributors, https://www.openstreetmap.org/copyright. Usage policy: https://operations.osmfoundation.org/policies/tiles/

The map uses the local HTTP app so the browser sends its normal referrer and honours tile caching. No bulk tile downloads, prefetching, or geocoding requests are performed. The tile service has no uptime guarantee. Internet access is required for tiles.

## Google Fonts

Inter loads from Google Fonts, with a sans-serif fallback if unavailable. The supplied background PNG is copied unchanged. All user-provided image rights remain with their respective owners; the code's MIT licence does not change them.
