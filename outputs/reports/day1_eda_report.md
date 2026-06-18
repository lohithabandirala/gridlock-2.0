# Day 1 EDA Report - Astram Incident Data

- Total records: **8173**
- Columns: **73**
- Unplanned vs planned: **7706 unplanned** (94.3%) / 467 planned
- Require road closure: **676** (8.3%)
- Clearance time available for **3061** rows | median **57 min**, mean **552 min**

## Top causes
  - vehicle_breakdown: 4896
  - others: 638
  - pot_holes: 537
  - construction: 480
  - water_logging: 458
  - accident: 365
  - tree_fall: 284
  - road_conditions: 170

## Data completeness (non-null %) - key columns
  - start_datetime: 98.6%
  - latitude: 100.0%
  - junction: 30.7%
  - corridor: 99.8%
  - zone: 42.1%
  - clearance_min: 37.5%
  - veh_type: 59.8%
  - priority: 100.0%

## Engineered features added
  - hour
  - dow
  - is_weekend
  - month
  - is_monsoon
  - time_slot
  - clearance_min
  - junction_freq
  - corridor_freq
  - zone_freq
  - text_len
  - kw_breakdown
  - kw_water
  - kw_accident

## Figures generated
  - outputs/figures/cause.png
  - outputs/figures/zone.png
  - outputs/figures/corridor.png
  - outputs/figures/hour.png
  - outputs/figures/clearance.png