SUMO scenario bundle for the Bengaluru incident closure demo.

Files:
- scenario.net.xml: placeholder network input to be generated from OSMnx or a
  manual SUMO network build.
- scenario.rou.xml: demand definition for the main corridor and diversion.
- scenario.add.xml: detector placeholder.
- scenario.sumocfg: SUMO configuration that ties the bundle together.

Use the JSON manifest to map this scenario back to the deterministic
micro-simulation if SUMO is unavailable.
