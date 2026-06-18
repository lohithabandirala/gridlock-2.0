# -*- coding: utf-8 -*-
"""Day 4a - lightweight 'what-if' traffic simulator (free, offline).

A full SUMO microsimulation needs the SUMO binary; to stay zero-install we use
the standard BPR (Bureau of Public Roads) volume-delay function plus an emission
factor. This gives a defensible estimate of extra delay and CO2 for a closure
and its diversion - the same KPIs (delay, emissions) the SUMO paper reports.
Swap in SUMO later behind the same run() API if desired.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import math
import shutil

from . import config

# BPR: t = t0 * (1 + alpha * (V/C)^beta)
ALPHA, BETA = 0.15, 4.0
CO2_G_PER_KM = 180.0          # avg mixed-fleet grams CO2 per vehicle-km (free public estimate)
IDLE_CO2_G_PER_MIN = 25.0     # grams CO2 per vehicle-minute idling


@dataclass
class Segment:
    name: str
    length_km: float
    free_flow_min: float
    capacity_vph: float        # vehicles per hour
    volume_vph: float


def bpr_time(seg: Segment, volume=None) -> float:
    v = seg.volume_vph if volume is None else volume
    return seg.free_flow_min * (1 + ALPHA * (v / max(seg.capacity_vph, 1)) ** BETA)


def what_if(main: Segment, detour: Segment, closure_fraction: float = 1.0,
            duration_min: float = 60.0) -> dict:
    """Compare 'do nothing' vs 'divert' when `closure_fraction` of the main road
    is lost for `duration_min` minutes. Uses a deterministic point-queue model
    for the over-saturated 'do nothing' case (so a full closure -> gridlock)."""
    hours = duration_min / 60.0
    n_main = main.volume_vph * hours                         # vehicles arriving during event

    # --- scenario A: no diversion -> capacity drops on the main road ---
    eff_cap = main.capacity_vph * (1 - closure_fraction)     # veh/hr still getting through
    if eff_cap >= main.volume_vph:
        # still under capacity: ordinary BPR congestion delay
        t_nodiv = bpr_time(main, volume=main.volume_vph)
        delay_nodiv = (t_nodiv - main.free_flow_min) * n_main
    else:
        # over-saturated: a queue builds. Deterministic point-queue total delay
        # = area of the triangular queue = 0.5 * (arrivals - served) * duration.
        served = eff_cap * hours
        queue = max(n_main - served, 0)
        delay_nodiv = 0.5 * queue * duration_min             # veh-minutes of waiting
        delay_nodiv += (bpr_time(main, volume=main.volume_vph) - main.free_flow_min) * n_main

    # --- scenario B: divert traffic onto the detour ---
    detour_vol = detour.volume_vph + main.volume_vph * closure_fraction
    t_detour = bpr_time(detour, volume=detour_vol)
    extra_per_veh = (t_detour - main.free_flow_min)          # min lost per diverted vehicle
    delay_div = max(extra_per_veh, 0) * n_main * closure_fraction

    saved_min = delay_nodiv - delay_div
    # emissions: extra distance on detour + idling delay
    extra_km = (detour.length_km - main.length_km) * n_main * closure_fraction
    co2_nodiv = delay_nodiv * IDLE_CO2_G_PER_MIN
    co2_div = delay_div * IDLE_CO2_G_PER_MIN + max(extra_km, 0) * CO2_G_PER_KM
    co2_saved_kg = (co2_nodiv - co2_div) / 1000.0

    return {
        "vehicles_affected": int(n_main),
        "delay_no_diversion_vehhr": round(delay_nodiv / 60, 1),
        "delay_with_diversion_vehhr": round(delay_div / 60, 1),
        "delay_saved_vehhr": round(saved_min / 60, 1),
        "co2_saved_kg": round(co2_saved_kg, 1),
        "recommend_diversion": bool(saved_min > 0),
    }


def micro_simulate(main: Segment, detour: Segment, closure_fraction: float = 1.0,
                   duration_min: float = 60.0, step_min: float = 1.0) -> dict:
    """Minute-by-minute queue propagation with basic spillback dynamics.

    This is a higher-fidelity deterministic substitute for a microsimulation:
    arrivals, queue growth, service rate and diversion are tracked in discrete
    time, rather than using a single closed-form BPR snapshot.
    """
    steps = max(1, int(math.ceil(duration_min / step_min)))
    main_arrival = main.volume_vph / 60.0 * step_min
    main_service = main.capacity_vph * (1 - closure_fraction) / 60.0 * step_min
    detour_service = detour.capacity_vph / 60.0 * step_min
    diverted_arrival = main_arrival * closure_fraction

    queue_main = 0.0
    queue_detour = 0.0
    total_delay_main = 0.0
    total_delay_detour = 0.0
    max_queue = 0.0

    for _ in range(steps):
        queue_main += main_arrival
        served_main = min(queue_main, main_service)
        queue_main -= served_main
        total_delay_main += queue_main * step_min
        max_queue = max(max_queue, queue_main)

        queue_detour += diverted_arrival + detour.volume_vph / 60.0 * step_min
        served_detour = min(queue_detour, detour_service)
        queue_detour -= served_detour
        total_delay_detour += queue_detour * step_min

    vehicles_affected = int(round(main.volume_vph * duration_min / 60.0))
    delay_no_diversion = total_delay_main + (main_arrival * steps - main_service * steps) * step_min
    delay_with_diversion = total_delay_detour
    detour_km_extra = max(detour.length_km - main.length_km, 0.0)
    co2_no_div = delay_no_diversion * IDLE_CO2_G_PER_MIN
    co2_div = delay_with_diversion * IDLE_CO2_G_PER_MIN + detour_km_extra * vehicles_affected * CO2_G_PER_KM
    saved_min = delay_no_diversion - delay_with_diversion

    return {
        "mode": "micro_sim",
        "vehicles_affected": vehicles_affected,
        "max_queue_veh": round(max_queue, 1),
        "delay_no_diversion_vehhr": round(delay_no_diversion / 60.0, 1),
        "delay_with_diversion_vehhr": round(delay_with_diversion / 60.0, 1),
        "delay_saved_vehhr": round(saved_min / 60.0, 1),
        "co2_saved_kg": round((co2_no_div - co2_div) / 1000.0, 1),
        "recommend_diversion": bool(saved_min > 0),
    }


def prepare_sumo_case(main: Segment, detour: Segment, output_dir: str | Path | None = None) -> dict:
    """Write a SUMO-ready scenario bundle when SUMO is installed.

    This creates a compact JSON manifest plus the demand parameters needed to
    wire a proper SUMO network/route file later. If SUMO is not installed, the
    bundle still documents the exact scenario that the deterministic simulator
    used.
    """
    out_dir = Path(output_dir) if output_dir else (config.REPORT_DIR.parent / "sumo")
    scenario_dir = out_dir / "outer_ring_road_closure"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    # A compact, portable SUMO scenario skeleton. The geometry is intentionally
    # schematic; it is meant to be replaced by a real OSMnx-exported network
    # when SUMO is available in the deployment environment.
    nodes_xml = """<nodes>
    <node id="n0" x="0" y="0" type="priority"/>
    <node id="n1" x="3000" y="0" type="priority"/>
    <node id="n2" x="4200" y="1200" type="priority"/>
    </nodes>
    """
    edges_xml = f"""<edges>
    <edge id="main" from="n0" to="n1" priority="2" numLanes="2" speed="{max(main.length_km / max(main.free_flow_min, 0.1) * 60, 30):.2f}"/>
    <edge id="detour" from="n1" to="n2" priority="1" numLanes="1" speed="{max(detour.length_km / max(detour.free_flow_min, 0.1) * 60, 20):.2f}"/>
    <edge id="merge" from="n2" to="n0" priority="1" numLanes="1" speed="30.00"/>
    </edges>
    """
    routes_xml = f"""<routes>
    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="5.0" maxSpeed="16.7"/>
    <route id="main_route" edges="main"/>
    <route id="diversion_route" edges="detour merge"/>
    <flow id="main_flow" type="car" route="main_route" begin="0" end="5400" vehsPerHour="{main.volume_vph:.0f}"/>
    <flow id="detour_flow" type="car" route="diversion_route" begin="0" end="5400" vehsPerHour="{detour.volume_vph:.0f}"/>
    </routes>
    """
    additional_xml = """<additional>
    <laneAreaDetector id="det_main" lane="main_0" pos="50" endPos="150" freq="60"/>
    </additional>
    """
    net_xml = """<net version="1.9">
    <!-- Placeholder network file.
         Replace with a real OSMnx/SUMO-generated network when SUMO is available. -->
    </net>
    """
    sumocfg = """<configuration>
    <input>
        <net-file value="scenario.net.xml"/>
        <route-files value="scenario.rou.xml"/>
        <additional-files value="scenario.add.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="5400"/>
    </time>
    </configuration>
    """
    readme = """SUMO scenario bundle for the Bengaluru incident closure demo.

Files:
- scenario.net.xml: placeholder network input to be generated from OSMnx or a
  manual SUMO network build.
- scenario.rou.xml: demand definition for the main corridor and diversion.
- scenario.add.xml: detector placeholder.
- scenario.sumocfg: SUMO configuration that ties the bundle together.

Use the JSON manifest to map this scenario back to the deterministic
micro-simulation if SUMO is unavailable.
"""
    manifest = {
        "sumo_available": bool(shutil.which("sumo")),
        "main": main.__dict__,
        "detour": detour.__dict__,
        "notes": "Use the manifest to generate a SUMO network, route and config file.",
    }
    (scenario_dir / "scenario_manifest.json").write_text(json.dumps(manifest, indent=2))
    (scenario_dir / "scenario.nod.xml").write_text(nodes_xml)
    (scenario_dir / "scenario.edg.xml").write_text(edges_xml)
    (scenario_dir / "scenario.rou.xml").write_text(routes_xml)
    (scenario_dir / "scenario.add.xml").write_text(additional_xml)
    (scenario_dir / "scenario.net.xml").write_text(net_xml)
    (scenario_dir / "scenario.sumocfg").write_text(sumocfg)
    (scenario_dir / "README.md").write_text(readme)
    return {
        "status": "ok",
        "output_dir": str(out_dir),
        "scenario_dir": str(scenario_dir),
        "sumo_available": manifest["sumo_available"],
    }


def demo() -> dict:
    """A representative Bengaluru corridor closure scenario."""
    main = Segment("Outer Ring Road (blocked)", length_km=3.0, free_flow_min=4.0,
                   capacity_vph=2400, volume_vph=2100)
    detour = Segment("Service-road detour", length_km=4.2, free_flow_min=7.0,
                     capacity_vph=1500, volume_vph=600)
    res = micro_simulate(main, detour, closure_fraction=1.0, duration_min=90)
    prepare_sumo_case(main, detour)
    import json
    (config.REPORT_DIR / "whatif_demo.json").write_text(json.dumps(res, indent=2))
    return res
