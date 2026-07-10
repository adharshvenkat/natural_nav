# NaturalNav

[![CI](https://github.com/adharshvenkat/natural_nav/actions/workflows/ci.yml/badge.svg)](https://github.com/adharshvenkat/natural_nav/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![ROS 2 Jazzy](https://img.shields.io/badge/ROS%202-Jazzy-blue.svg)](https://docs.ros.org/en/jazzy/)

**Turns plain-English commands into robot navigation via open-vocabulary perception and LLM-driven replanning.**

> *"Go check the pallet, then head to the forklift."*

NaturalNav takes a natural-language command, decomposes it with an LLM into a structured task graph, and dispatches Nav2 navigation goals. Task targets aren't hardcoded coordinates: they're resolved through an **open-vocabulary semantic map** the robot builds online from its RGBD camera using GroundingDINO. The stack is Nav2-based and platform-agnostic in principle; today it's validated against a TurtleBot4 in a Gazebo warehouse, fully Dockerized with GPU passthrough.

---

## Status

| Layer | State |
|-------|-------|
| Containerized stack (Docker + GPU, multi-stage build) | ✅ working |
| Gazebo warehouse + TurtleBot4 + Nav2 + RViz | ✅ working |
| LLM planner (xAI Grok / Ollama / Anthropic / OpenAI) | ✅ working |
| Task executor (Nav2 action client + DAG + replan requests) | ✅ working |
| In-memory semantic map (label → pose, JSON snapshots) | ✅ data structure ready |
| Semantic detector (GroundingDINO + depth → map projection) | ✅ code complete, geometry unit-tested; ⏳ GPU-sim validation |
| Replan loop wired end-to-end (executor ↔ planner) | ✅ wired in code; ⏳ sim validation |
| Demo video / GIF | ⏳ pending |

---

## Architecture

Full system diagram, component breakdown, interfaces, assumptions, and known failure modes: [`docs/architecture.md`](docs/architecture.md)

![System architecture overview](docs/assets/architecture-overview.svg)

Sim, Nav2, and RViz come from Nav2's `tb4_simulation_launch.py`. The perception and LLM nodes are layered on top.

---

## Tech Stack

| Component | Tool |
|-----------|------|
| Simulator | Gazebo Sim (Harmonic) via `nav2_minimal_tb4_sim` warehouse |
| Robot | TurtleBot4 (OAK-D Pro RGBD camera + RPLidar) |
| Navigation | Nav2 (AMCL + planner + controller + behavior tree) on pre-built warehouse map |
| Perception | GroundingDINO (open-vocab detection) + CLIP (reserved for disambiguation) |
| LLM | Provider-agnostic: Ollama qwen2.5:3b (local default), xAI Grok, Anthropic, OpenAI |
| Containerization | Docker + Docker Compose, multi-stage build, NVIDIA Container Toolkit for sim rendering |
| ROS 2 | Jazzy |

---

## Quick Start

### Prerequisites
- Linux host with an NVIDIA GPU (Gazebo sensor rendering uses it)
- Docker + Docker Compose + NVIDIA Container Toolkit
- An LLM API key (or use the bundled local Ollama)

### Run

```bash
git clone https://github.com/adharshvenkat/natural_nav.git
cd natural_nav

cp .env.example .env
# edit .env: pick LLM_PROVIDER, paste your API key, etc. (defaults to local Ollama)

xhost +local:docker              # let the container draw on your X display
docker compose up -d ollama      # start local LLM (skip if using a cloud provider)
./scripts/setup_ollama.sh        # pull qwen2.5:3b into the ollama volume (one-time)
./scripts/setup_groundingdino.sh # pull GroundingDINO weights into the volume (one-time)

# Terminal 1: Gazebo + Nav2 + RViz
docker compose run --rm --name nn naturalnav \
  ros2 launch natural_nav simulation.launch.py
```

Gazebo + RViz will open. In RViz, click **2D Pose Estimate** and place the robot pose roughly where it sits in Gazebo so AMCL localizes.

Then start the NaturalNav nodes (planner, executor, semantic detector). The `simulation.launch.py` above only brings up the sim and Nav2:

```bash
# Terminal 2: LLM planner + task executor + semantic detector
docker exec -it nn /entrypoint.sh \
  ros2 launch natural_nav naturalnav.launch.py
```

### Send a command

In another terminal:

```bash
docker exec -it nn bash -c "source /opt/ros/jazzy/setup.bash && \
  ros2 topic pub --once /natural_nav/command std_msgs/msg/String \
  '{data: \"Go to the pallet, then navigate to the forklift\"}'"
```

This decomposes into a two-task DAG (`navigate → pallet`, then `navigate → forklift` with `depends_on` the first), showcasing the executor's dependency-ordered dispatch rather than a single flat goal.

### Watch what's happening

```bash
docker exec -it nn bash -c "source /opt/ros/jazzy/setup.bash && \
  ros2 topic echo /natural_nav/fleet_status"
```

---

## Repository Layout

```
natural_nav/
├── Dockerfile                 # Multi-stage: builder + runtime
├── docker-compose.yml         # naturalnav + ollama services, GPU + X11
├── .env.example               # LLM provider / model / API key template
├── scripts/setup_ollama.sh    # Pull the local LLM into the ollama volume
├── docker/entrypoint.sh       # Sources ROS2 + workspace on container start
├── docs/
│   ├── architecture.md        # System design: components, interfaces, assumptions, failure modes
│   └── assets/                # Diagram source (.excalidraw) + exported SVG
└── src/natural_nav/
    ├── natural_nav/
    │   ├── llm_client.py          # Provider-agnostic LLM factory (xai/ollama/anthropic/openai)
    │   ├── llm_planner.py         # Command → task graph
    │   ├── fleet_orchestrator.py  # Task executor (Nav2 dispatch + DAG walk)
    │   ├── semantic_map.py        # In-memory label → pose store
    │   ├── projection.py          # Pixel→3D geometry (pure numpy, unit-tested)
    │   └── semantic_detector.py   # GroundingDINO + depth projection → map
    ├── launch/
    │   ├── simulation.launch.py   # Wraps nav2_bringup tb4_simulation_launch
    │   └── naturalnav.launch.py   # Brings up perception + planner + executor
    └── worlds/naturalnav.world    # (legacy custom world, retained as fallback)
```

---

## ROS 2 Topics & Actions

| Name | Type | Direction | Purpose |
|------|------|-----------|---------|
| `/natural_nav/command` | `std_msgs/String` | in | Natural-language command from user |
| `/natural_nav/task_graph` | `std_msgs/String` (JSON) | planner → executor | Decomposed task DAG |
| `/natural_nav/semantic_map` | `std_msgs/String` (JSON) | detector → executor | Snapshot of label → pose map |
| `/natural_nav/detections` | `std_msgs/String` (JSON) | detector → * | Per-frame raw detections (label, score, bbox) |
| `/natural_nav/fleet_status` | `std_msgs/String` (JSON) | executor → user | Mission + per-task status |
| `/natural_nav/planner_status` | `std_msgs/String` | planner → user | Human-readable planner status |
| `/natural_nav/replan_request` | `std_msgs/String` (JSON) | executor → planner | Context for LLM replan on failure |
| `/rgbd_camera/image` | `sensor_msgs/Image` | sim → detector | TB4 OAK-D RGB at ~10 Hz |
| `/rgbd_camera/depth_image` | `sensor_msgs/Image` | sim → detector | Depth, same rate |
| `/rgbd_camera/camera_info` | `sensor_msgs/CameraInfo` | sim → detector | Intrinsics for 3D unprojection |
| `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | executor → Nav2 | Goal dispatch |

---

## Configuration

`.env` (gitignored, copy from `.env.example`):

```bash
LLM_PROVIDER=ollama         # ollama | anthropic | openai | xai
LLM_MODEL=qwen2.5:3b        # match the provider (e.g. claude-opus-4-8 for anthropic)
LLM_API_KEY=                # leave blank for ollama; required for cloud providers
OLLAMA_HOST=http://localhost:11434
LLM_BASE_URL=               # only needed to override the OpenAI-compatible endpoint
```

The `llm_client.py` factory picks the right client + auto-defaults the base URL for `xai`.

---

## Design Notes

- **TurtleBot4 in the Nav2 warehouse sim.** The work here is on the perception and LLM layers, not the navigation stack. Using the upstream sim keeps the navigation layer reproducible and out of scope.
- **Semantic map instead of fixed waypoints.** Language-conditioned navigation requires that LLM-named targets resolve through perception, not a hardcoded `label → (x, y)` table. This is the VLMaps-family approach.
- **Provider-agnostic LLM.** Switching between local (Ollama) and cloud (xAI / Anthropic / OpenAI) is a one-line `.env` change. No code path differs between modes.
- **GPU passthrough.** Gazebo's `ogre2` sensor system needs a render context. Without a GPU exposed to the container, the camera sensor registers its topic but never publishes frames. The compose file enables the NVIDIA runtime.

---

## Roadmap

**Built and wired end-to-end:** containerized GPU stack, Gazebo/TB4/Nav2 warehouse sim, provider-agnostic LLM planner, task executor (Nav2 dispatch + DAG walk + replan requests), in-memory semantic map, GroundingDINO-based semantic detector with depth-to-map projection, and the planner ↔ executor replan loop.

Open work, known gaps, and planned improvements are tracked in [GitHub Issues](https://github.com/adharshvenkat/natural_nav/issues).

---

## License

Apache 2.0
