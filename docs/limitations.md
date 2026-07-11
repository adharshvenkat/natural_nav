# NaturalNav Limitations

## Assumptions

- Pre-built, Nav2-compatible map of the environment exists - no SLAM/online mapping; the robot localizes against a known warehouse map rather than building one.
- Detection vocabulary is fixed at launch (static prompt list: shelf, pallet, box, cardboard box, person, chair, table, forklift, door, barrel), not dynamically derived from the task command.
- Sim-only, no real-hardware validation performed or currently planned. Everything (perception, navigation, replanning) has only been exercised in Gazebo; real-world sensor noise, lighting, and localization behavior may differ meaningfully from sim.
- Single-robot only by design. The LLM planner's own system prompt states "you are a task planner for a single mobile robot in a warehouse"; the 'Task' schema has no 'robot_id' field; 'TaskExecutorNode' creates exactly one Nav2 'ActionClient' in '__init__'; and 'simulation.launch.py' wraps Nav2's single-robot 'tb4_simulation_launch.py'. Multi-robot support is architecturally possible (Nav2 itself supports namespaced multi-robot setups) but would require a task-to-robot allocation strategy in the planner, a 'robot_id' field threaded through the task schema, a per-robot executor/action-client, and a namespaced multi-robot launch file - not a config flag.

## Known Failure Modes

- Unresolved target has no reliable failure signal today. By design, the planner should return 'no matching target' ('replan_on_failure: false', no recovery attempted) when a command references a label outside 'known_labels'. In practice this isn't enforced in code - '_parse_json()' publishes whatever JSON the LLM returns with no validation against 'known_labels' - and the local model has been observed substituting a different, wrong-but-known label instead (see [#8](https://github.com/adharshvenkat/natural_nav/issues/8)). The robot can then confidently navigate to the wrong object with no visible error, which is worse than a clean failure.
- No active-search/exploration behavior exists. The semantic map is only populated by passive observation while driving; if a target hasn't been seen yet (or falls outside the static detection vocabulary, see Assumptions), there's no fallback to go look for it - the planner's own fallback message says "explore first" but no explore behavior is implemented. Fixing both of these (label validation + dynamic vocab + active search) is planned future work, tracked in [#8](https://github.com/adharshvenkat/natural_nav/issues/8) and [#12](https://github.com/adharshvenkat/natural_nav/issues/12).
