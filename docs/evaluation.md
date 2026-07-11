# NaturalNav Evaluation

## Methodology

Evaluation runs against a fixed, repeatable set of scripted commands driven through the Gazebo warehouse world, so results are comparable across runs. Metrics are broken down per layer (Perception, Planning, Execution/System) rather than as a single number, since each layer fails in a different way and a system-level pass/fail alone hides which component is responsible.

## Metrics

### Perception

- **Detection correctness** - per scripted scene, whether the correct label was detected at all (presence/absence, not IoU-thresholded bounding-box precision/recall). See Known Gaps for a more rigorous version.
- **Position accuracy** - whether the semantic map's resolved pose for a label is close enough to the object's actual pose to be usable, using Nav2's own goal tolerance (from the wrapped 'nav2_bringup' stack's default params, not overridden in this repo) as the pass/fail threshold.

### Planning

- **Valid-schema rate** - does the LLM's output parse as valid JSON matching the task-graph schema.
- **Correct-target rate** - does the selected 'target' match a label actually in 'known_labels' for the command given.
- **Correct-dependency rate** - for commands that imply ordering (eg. "go to X, then Y"), are the 'depends_on' chains correct.

All three measured as pass/fail over a hand-written test set of commands, not a statistical/learned metric.

### Execution / System

- **Task success rate** - percentage of scripted end-to-end scenarios (command -> full task graph -> all Nav2 goals reached) that complete fully without human intervention.
- **Replan effectiveness** - of the scenarios that hit a failure (unresolvable target, Nav2 goal rejection, Nav2 non-success), percentage the replan loop actually recovers from vs. ones that fail again or stall.

Timing/latency (planning latency, detection latency, end-to-end mission completion time) is not currently measured; planned for later.

## Current Results

Not yet measured - these metrics are defined but no evaluation runs have been executed against them yet.

## Known Gaps

- Detection correctness is presence-based (yes/no per scene), not IoU-thresholded precision/recall. A more rigorous version is possible in sim by projecting each object's known 3D pose/extents (from the Gazebo world file) into the camera frame using the same intrinsics/TF the semantic detector already computes, then comparing against actual detections at IoU@0.5 - tracked in [#13](https://github.com/adharshvenkat/natural_nav/issues/13).
- No timing/latency metrics yet.
