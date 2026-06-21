"""Spatial logic engine for dynamic deployment and resource routing."""

import math
import uuid
import networkx as nx
from dataclasses import dataclass, field
from datetime import datetime, timezone
import pandas as pd

from .config import CITY_HUBS, ROAD_LIBRARY

R = 6371.0

def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two points."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def move_towards(lat, lon, target_lat, target_lon, distance_km):
    dist_total = haversine(lat, lon, target_lat, target_lon)
    if dist_total <= distance_km:
        return target_lat, target_lon, distance_km - dist_total
    
    ratio = distance_km / dist_total
    new_lat = lat + (target_lat - lat) * ratio
    new_lon = lon + (target_lon - lon) * ratio
    return new_lat, new_lon, 0.0

@dataclass
class Incident:
    id: str
    lat: float
    lon: float
    severity: str
    created_at: float

@dataclass
class Unit:
    id: str
    type: str
    lat: float
    lon: float
    speed_kmh: float
    color: list
    status: str
    target_id: str = None
    target_lat: float = None
    target_lon: float = None
    state_timer: float = 0.0
    home_lat: float = 0.0
    home_lon: float = 0.0

class SpatialEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SpatialEngine, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        
        self.incidents = []
        self.units = []
        self.graph = nx.Graph()
        self.base_hubs = [(h["lat"], h["lon"]) for h in CITY_HUBS.values()]
        
        # Build network graph of corridors
        for h_name, h_data in CITY_HUBS.items():
            self.graph.add_node(h_name, lat=h_data["lat"], lon=h_data["lon"])
        
        for r_name, r_data in ROAD_LIBRARY.items():
            self.graph.add_node(r_name, lat=r_data["lat"], lon=r_data["lon"])
            
        # Connect nearby nodes
        nodes = list(self.graph.nodes(data=True))
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                n1, n2 = nodes[i], nodes[j]
                dist = haversine(n1[1]["lat"], n1[1]["lon"], n2[1]["lat"], n2[1]["lon"])
                if dist < 6.0:
                    self.graph.add_edge(n1[0], n2[0], weight=dist)

        self.last_tick = datetime.now(timezone.utc).timestamp()
        self.initialized = True

    def _get_nearest_node(self, lat, lon):
        nodes = list(self.graph.nodes(data=True))
        return min(nodes, key=lambda n: haversine(lat, lon, n[1]["lat"], n[1]["lon"]))[0]

    def _spawn_or_despawn_units(self, required_police: int, required_ambulances: int):
        current_police = sum(1 for u in self.units if u.type == "Police")
        current_ambulance = sum(1 for u in self.units if u.type == "Ambulance")
        
        target_police = max(required_police, 10)
        target_ambulance = max(required_ambulances, 5)
        
        # Spawn deterministically at bases based on load
        if current_police < target_police:
            for i in range(target_police - current_police):
                # Cycle through hubs for deterministic spread
                hub = self.base_hubs[len(self.units) % len(self.base_hubs)]
                self.units.append(Unit(
                    id=f"BLR-POL-{100 + len(self.units)}",
                    type="Police",
                    lat=hub[0],
                    lon=hub[1],
                    home_lat=hub[0],
                    home_lon=hub[1],
                    speed_kmh=45.0,
                    color=[0, 207, 163],
                    status="Available"
                ))
                
        if current_ambulance < target_ambulance:
            for i in range(target_ambulance - current_ambulance):
                hub = self.base_hubs[len(self.units) % len(self.base_hubs)]
                self.units.append(Unit(
                    id=f"KA-AMB-{200 + len(self.units)}",
                    type="Ambulance",
                    lat=hub[0],
                    lon=hub[1],
                    home_lat=hub[0],
                    home_lon=hub[1],
                    speed_kmh=60.0,
                    color=[255, 107, 107],
                    status="Available"
                ))

    def update_incidents(self, snapshot_df, required_police=0, required_ambulances=0):
        # Update incidents deterministically based on real dataframe threshold
        self.incidents.clear()
        for _, row in snapshot_df.iterrows():
            if row['severity'] in ('Critical', 'Red', 'Closed'):
                # Deterministic hash ID based on lat/lon
                inc_id = f"INC-{abs(hash(str(row['lat'])+str(row['lon']))) % 100000}"
                self.incidents.append(Incident(
                    id=inc_id,
                    lat=row['lat'],
                    lon=row['lon'],
                    severity=row['severity'],
                    created_at=datetime.now(timezone.utc).timestamp()
                ))
        
        self._spawn_or_despawn_units(required_police, required_ambulances)
        self._dispatch_units()

    def _dispatch_units(self):
        # Map units to incidents deterministically
        for incident in self.incidents:
            assigned = sum(1 for u in self.units if u.target_id == incident.id)
            needed = 3 if incident.severity == 'Closed' else (2 if incident.severity == 'Critical' else 1)
            
            while assigned < needed:
                # Find closest available unit
                available = [u for u in self.units if u.status in ("Available", "Reserve")]
                if not available:
                    break
                closest = min(available, key=lambda u: haversine(u.lat, u.lon, incident.lat, incident.lon))
                closest.target_id = incident.id
                closest.target_lat = incident.lat
                closest.target_lon = incident.lon
                closest.status = "En Route"
                assigned += 1

    def tick(self, time_delta_sec=30.0):
        # Move units deterministically
        for unit in self.units:
            if unit.status == "En Route":
                dist_to_move = (unit.speed_kmh / 3600.0) * time_delta_sec
                unit.lat, unit.lon, rem = move_towards(unit.lat, unit.lon, unit.target_lat, unit.target_lon, dist_to_move)
                
                if haversine(unit.lat, unit.lon, unit.target_lat, unit.target_lon) < 0.05:
                    unit.status = "Active"
                    unit.state_timer = 300.0 # Standard 5 minute hold time
                    
            elif unit.status == "Active":
                unit.state_timer -= time_delta_sec
                if unit.state_timer <= 0:
                    unit.status = "Returning"
                    unit.target_id = None
                    unit.target_lat = unit.home_lat
                    unit.target_lon = unit.home_lon
                    
            elif unit.status == "Returning":
                dist_to_move = (unit.speed_kmh / 3600.0) * time_delta_sec
                unit.lat, unit.lon, rem = move_towards(unit.lat, unit.lon, unit.target_lat, unit.target_lon, dist_to_move)
                
                if haversine(unit.lat, unit.lon, unit.target_lat, unit.target_lon) < 0.05:
                    # Put to reserve deterministically if volume is low, else Available
                    unit.status = "Available" if len(self.incidents) > 0 else "Reserve"
                    unit.target_lat = None
                    unit.target_lon = None

    def get_unit_dataframe(self) -> pd.DataFrame:
        if not self.units:
            return pd.DataFrame()
        return pd.DataFrame([{
            "id": u.id,
            "type": u.type,
            "lat": u.lat,
            "lon": u.lon,
            "status": u.status,
            "target_lat": u.target_lat,
            "target_lon": u.target_lon
        } for u in self.units])

    def get_incident_dataframe(self) -> pd.DataFrame:
        if not self.incidents:
            return pd.DataFrame()
        return pd.DataFrame([{
            "id": i.id,
            "lat": i.lat,
            "lon": i.lon,
            "severity": i.severity
        } for i in self.incidents])
