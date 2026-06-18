# -*- coding: utf-8 -*-
"""Day 3a - manpower / barricade allocation across predicted hotspots.

Allocates a limited number of officers to the highest-risk sites to maximise
covered risk, with diminishing returns per extra officer. Uses Google OR-Tools
(CP-SAT); falls back to a greedy allocator if OR-Tools is unavailable.
"""
import pandas as pd
from . import config

try:
    from ortools.sat.python import cp_model
    _HAS_ORTOOLS = True
except Exception:                      # pragma: no cover
    _HAS_ORTOOLS = False


def _greedy(weights, budget, max_per_site, decay):
    """Marginal-benefit greedy: always give the next officer to the slot with
    the highest remaining marginal value."""
    alloc = [0] * len(weights)
    import heapq
    heap = [(-w, i) for i, w in enumerate(weights)]   # marginal value of 1st officer
    heapq.heapify(heap)
    for _ in range(budget):
        if not heap:
            break
        neg, i = heapq.heappop(heap)
        if alloc[i] >= max_per_site:
            continue
        alloc[i] += 1
        if alloc[i] < max_per_site:
            marg = weights[i] * (decay ** alloc[i])
            heapq.heappush(heap, (-marg, i))
    return alloc


def _cpsat(weights, budget, max_per_site, decay):
    m = cp_model.CpModel()
    n = len(weights)
    # slot booleans: s[i][k] == site i has at least (k+1) officers
    s = [[m.NewBoolVar(f"s_{i}_{k}") for k in range(max_per_site)] for i in range(n)]
    for i in range(n):
        for k in range(1, max_per_site):
            m.Add(s[i][k] <= s[i][k - 1])          # ordering: need slot k-1 before k
    m.Add(sum(s[i][k] for i in range(n) for k in range(max_per_site)) <= budget)
    # integer objective (scale weights to ints)
    obj = []
    for i in range(n):
        for k in range(max_per_site):
            marg = int(round(weights[i] * (decay ** k) * 100))
            obj.append(marg * s[i][k])
    m.Maximize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    solver.Solve(m)
    return [sum(int(solver.Value(s[i][k])) for k in range(max_per_site)) for i in range(n)]


def allocate(sites: pd.DataFrame, budget: int = 20, max_per_site: int = 3,
             decay: float = 0.5, weight_col: str = "incidents") -> pd.DataFrame:
    """sites: dataframe of hotspots with a weight column. Returns allocation."""
    sites = sites.copy().reset_index(drop=True)
    weights = sites[weight_col].astype(float).tolist()
    if _HAS_ORTOOLS:
        alloc = _cpsat(weights, budget, max_per_site, decay)
        engine = "OR-Tools CP-SAT"
    else:
        alloc = _greedy(weights, budget, max_per_site, decay)
        engine = "greedy"
    sites["officers"] = alloc
    sites["barricade"] = sites["officers"] >= max_per_site   # saturate -> recommend barricade
    sites["_engine"] = engine
    out = sites[sites["officers"] > 0].sort_values("officers", ascending=False)
    out.to_csv(config.REPORT_DIR / "manpower_allocation.csv", index=False)
    return out


def run(budget: int = 20) -> dict:
    bs_path = config.REPORT_DIR / "blackspots.csv"
    if not bs_path.exists():
        return {"status": "skipped", "reason": "run Day 2 first (blackspots.csv missing)"}
    sites = pd.read_csv(bs_path).head(15)          # top 15 hotspots
    alloc = allocate(sites, budget=budget)
    return {"status": "ok", "engine": alloc["_engine"].iat[0] if len(alloc) else "n/a",
            "sites_covered": int(len(alloc)), "officers_used": int(alloc["officers"].sum()),
            "barricades": int(alloc["barricade"].sum())}
