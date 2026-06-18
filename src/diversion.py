# -*- coding: utf-8 -*-
"""Day 3b - offline road-graph diversion planner.

OSMnx needs internet to download the real Bengaluru network. To keep the whole
project free AND offline, we build a proximity graph directly from the incident
GPS points: nodes = sampled incident locations, edges = links between nearby
points weighted by haversine distance. On a closure we drop the affected edge
and recompute the shortest alternate path with NetworkX. (Swap in OSMnx later
with one function if internet is available - same downstream API.)
"""
import math
import numpy as np
import pandas as pd
import networkx as nx
from . import config

try:
    import osmnx as ox
    _HAS_OSMNX = True
except Exception:  # pragma: no cover
    ox = None
    _HAS_OSMNX = False


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _nearest_node(G: nx.Graph, lat: float, lon: float):
    best = None
    best_d = float("inf")
    for n, data in G.nodes(data=True):
        nlat = data.get("y", data.get("lat"))
        nlon = data.get("x", data.get("lon"))
        if nlat is None or nlon is None:
            continue
        d = _haversine(lat, lon, float(nlat), float(nlon))
        if d < best_d:
            best = n
            best_d = d
    return best


def build_graph(df: pd.DataFrame, n_nodes: int = 200, k: int = 4) -> nx.Graph:
    """Road graph for diversion planning.

    Prefers a real OpenStreetMap road network via OSMnx when available. Falls
    back to the offline proximity graph so the pipeline still works without
    internet or optional dependencies.
    """
    if _HAS_OSMNX:
        try:
            center = config.CITY_CENTER
            G = ox.graph_from_point(center, dist=int(config.OSM_RADIUS_KM * 1000),
                                    network_type="drive", simplify=True)
            G = ox.distance.add_edge_lengths(G)
            return G
        except Exception:
            pass

    pts = df.dropna(subset=["latitude", "longitude"])[["latitude", "longitude"]]
    pts = pts.drop_duplicates().sample(min(n_nodes, len(pts)), random_state=42).reset_index(drop=True)
    G = nx.Graph()
    for i, r in pts.iterrows():
        G.add_node(int(i), lat=float(r["latitude"]), lon=float(r["longitude"]))
    coords = pts.values
    for i in range(len(coords)):
        dists = []
        for j in range(len(coords)):
            if i == j:
                continue
            d = _haversine(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
            dists.append((d, j))
        dists.sort()
        for d, j in dists[:k]:
            G.add_edge(int(i), int(j), weight=round(d, 4))
    # connect components so routing always succeeds
    comps = list(nx.connected_components(G))
    for a in range(len(comps) - 1):
        na, nb = next(iter(comps[a])), next(iter(comps[a + 1]))
        d = _haversine(G.nodes[na]["lat"], G.nodes[na]["lon"],
                       G.nodes[nb]["lat"], G.nodes[nb]["lon"])
        G.add_edge(na, nb, weight=round(d, 4))
    return G


def plan_diversion(G: nx.Graph, src: int, dst: int, block_edge=None) -> dict:
    """Return baseline route and (if an edge is blocked) the alternate route."""
    base = nx.shortest_path(G, src, dst, weight="weight")
    base_len = nx.shortest_path_length(G, src, dst, weight="weight")
    result = {"src": src, "dst": dst,
              "baseline_route": base, "baseline_km": round(base_len, 3)}
    if block_edge is None:
        # block the busiest edge on the baseline route as a demo
        block_edge = (base[len(base) // 2], base[len(base) // 2 + 1]) if len(base) > 2 else (base[0], base[1])
    H = G.copy()
    if H.has_edge(*block_edge):
        H.remove_edge(*block_edge)
    try:
        alt = nx.shortest_path(H, src, dst, weight="weight")
        alt_len = nx.shortest_path_length(H, src, dst, weight="weight")
        result.update({"blocked_edge": list(block_edge), "alt_route": alt,
                       "alt_km": round(alt_len, 3),
                       "detour_km": round(alt_len - base_len, 3)})
    except nx.NetworkXNoPath:
        result.update({"blocked_edge": list(block_edge), "alt_route": None,
                       "note": "no alternate path - isolated"})
    return result


def run(df: pd.DataFrame) -> dict:
    G = build_graph(df)
    nodes = list(G.nodes)
    if _HAS_OSMNX and len(df.dropna(subset=["latitude", "longitude"])) >= 2:
        coords = df.dropna(subset=["latitude", "longitude"])[["latitude", "longitude"]].drop_duplicates()
        src_lat, src_lon = coords.iloc[0]
        dst_lat, dst_lon = coords.iloc[min(len(coords) - 1, max(1, len(coords) // 2))]
        src = _nearest_node(G, float(src_lat), float(src_lon))
        dst = _nearest_node(G, float(dst_lat), float(dst_lon))
    else:
        src, dst = nodes[0], nodes[len(nodes) // 2]
    plan = plan_diversion(G, src, dst)
    # persist a compact summary
    summary = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
               **{k: v for k, v in plan.items() if k not in ("baseline_route", "alt_route")}}
    pd.DataFrame([summary]).to_csv(config.REPORT_DIR / "diversion_summary.csv", index=False)
    # also store the graph for the dashboard
    nx.write_gml(G, config.MODEL_DIR / "road_graph.gml")
    return {"status": "ok", **summary}
