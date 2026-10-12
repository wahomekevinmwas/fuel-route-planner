"""Pure geometry helpers (numpy only, no Django) so they can be unit tested in isolation."""
import numpy as np

EARTH_RADIUS_MI = 3958.7613
MI_PER_DEG_LAT = 69.0
MI_PER_DEG_LON_EQUATOR = 69.17


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a))


def resample(coords, step_miles=1.0):
    """Resample a [lon, lat] polyline to (almost) uniform spacing.

    Routing APIs return anywhere from a few hundred to tens of thousands of vertices.
    Uniform ~1-mile spacing makes later work predictable: both thinning dense geometry and
    filling gaps in sparse geometry. Returns (points (n,2) [lon,lat], cumulative_miles (n,)).
    """
    pts = np.asarray(coords, dtype=float)
    if len(pts) < 2:
        return pts, np.zeros(len(pts))
    seg = haversine_miles(pts[:-1, 1], pts[:-1, 0], pts[1:, 1], pts[1:, 0])
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    targets = np.append(np.arange(0.0, total, step_miles), total)
    lon = np.interp(targets, cum, pts[:, 0])
    lat = np.interp(targets, cum, pts[:, 1])
    return np.column_stack([lon, lat]), targets


def stations_near_route(route_pts, cum_miles, st_lat, st_lng, corridor_miles=10.0, chunk=400):
    """Find stations within corridor_miles of the route.

    Returns three arrays (station_index, mile_marker, offset_miles): for each qualifying
    station, the index into st_lat/st_lng, how far along the route its nearest point is,
    and how far off the route it sits.

    A bounding-box prefilter discards most stations before the (vectorised) distance
    matrix is computed, so this stays fast even for a cross-country route.
    """
    st_lat = np.asarray(st_lat, dtype=float)
    st_lng = np.asarray(st_lng, dtype=float)
    lat_r, lon_r = route_pts[:, 1], route_pts[:, 0]

    pad_lat = corridor_miles / MI_PER_DEG_LAT
    worst_lat = min(float(np.max(np.abs(lat_r))) + pad_lat, 89.0)
    pad_lon = corridor_miles / (MI_PER_DEG_LON_EQUATOR * np.cos(np.radians(worst_lat)))
    in_box = (
        (st_lat >= lat_r.min() - pad_lat) & (st_lat <= lat_r.max() + pad_lat)
        & (st_lng >= lon_r.min() - pad_lon) & (st_lng <= lon_r.max() + pad_lon)
    )
    candidates = np.nonzero(in_box)[0]

    # Stage 1: cheap coarse pass against every ~20th route point. A station further than
    # (corridor + half the coarse spacing) from all of them cannot be within the corridor.
    stride = 20
    coarse_lat, coarse_lon = lat_r[::stride], lon_r[::stride]
    margin = corridor_miles + 12.0
    survivors = []
    for start in range(0, len(candidates), 2000):
        ids = candidates[start:start + 2000]
        slat = st_lat[ids][:, None]
        slon = st_lng[ids][:, None]
        dy = (slat - coarse_lat[None, :]) * MI_PER_DEG_LAT
        dx = (slon - coarse_lon[None, :]) * (MI_PER_DEG_LON_EQUATOR * np.cos(np.radians(slat)))
        survivors.append(ids[(dx * dx + dy * dy).min(axis=1) <= margin * margin])
    candidates = np.concatenate(survivors) if survivors else candidates[:0]

    # Stage 2: exact nearest route point for the few survivors.
    keep_idx, keep_mile, keep_off = [], [], []
    for start in range(0, len(candidates), chunk):
        ids = candidates[start:start + chunk]
        slat = st_lat[ids][:, None]
        slon = st_lng[ids][:, None]
        dy = (slat - lat_r[None, :]) * MI_PER_DEG_LAT
        dx = (slon - lon_r[None, :]) * (MI_PER_DEG_LON_EQUATOR * np.cos(np.radians(slat)))
        d2 = dx * dx + dy * dy
        nearest = d2.argmin(axis=1)
        dist = np.sqrt(d2[np.arange(len(ids)), nearest])
        ok = dist <= corridor_miles
        keep_idx.append(ids[ok])
        keep_mile.append(cum_miles[nearest[ok]])
        keep_off.append(dist[ok])

    if not keep_idx:
        empty = np.array([])
        return empty.astype(int), empty, empty
    return np.concatenate(keep_idx), np.concatenate(keep_mile), np.concatenate(keep_off)
