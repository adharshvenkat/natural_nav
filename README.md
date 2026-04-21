# NaturalNav

**LLM-orchestrated semantic navigation for multi-robot fleets.**

> "Inspect shelf row 7, deliver any flagged item to workstation 3, and alert me if the path is blocked."

NaturalNav accepts natural language commands and autonomously decomposes them into a dynamic multi-robot task graph. Tasks are allocated based on robot availability and proximity — not fixed roles. If a robot fails, the LLM replans in real time. All running in a single `docker compose up`.

---

## Architecture

```
Natural Language Command
        │
        ▼
┌─────────────────────┐
│     LLM Planner     │  command → structured task graph
│                     │  considers robot state + proximity
└────────┬────────────┘
         │ /natural_nav/task_graph
         ▼
┌──────────────────────┐
│  Fleet Orchestrator  │  Dispatches Nav2 goals per robot
│                      │  Tracks availability + task state
│                      │  LLM replanner on failure
└────────┬─────────────┘
         │ Nav2 actions
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│robot_1 │ │robot_2 │  TurtleBot3 (full capability)
│        │ │        │  Camera + Nav2 per robot
└───┬────┘ └───┬────┘
    │           │
    └─────┬─────┘
          ▼
┌──────────────────────┐
│  Semantic Detector   │  CLIP + GroundingDINO
│                      │  Subscribes to both robot cameras
│                      │  Builds open-vocabulary semantic map
└──────────────────────┘
```

## Tech Stack

| Component | Tool |
|-----------|------|
| Simulation | Gazebo Harmonic (via ros:jazzy-desktop) |
| Robot model | TurtleBot3 (camera + Nav2, x2) |
| Navigation | Nav2 (binary, ros-jazzy) |
| Semantic perception | CLIP + GroundingDINO (CPU) |
| LLM planner + replanner | Configurable (OpenAI / Anthropic / local) |
| Containerization | Docker + Docker Compose (multi-stage build) |
| ROS2 distribution | Jazzy |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- An LLM API key (see Configuration)

### Run

```bash
git clone https://github.com/adharshvenkat/natural_nav.git
cd natural_nav

export LLM_API_KEY=your-api-key-here
export LLM_PROVIDER=anthropic   # or: openai
docker compose up
```

### Send a command

```bash
# In a new terminal
docker compose exec naturalnav \
  ros2 topic pub --once /natural_nav/command std_msgs/msg/String \
  '{"data": "Inspect shelf row 7 and deliver any flagged items to workstation 3"}'
```

### Watch the fleet status

```bash
docker compose exec naturalnav \
  ros2 topic echo /natural_nav/fleet_status
```

---

## Package Structure

```
src/natural_nav/
├── natural_nav/
│   ├── llm_planner.py        # LLM task decomposition node
│   ├── semantic_detector.py  # CLIP + GroundingDINO perception node
│   └── fleet_orchestrator.py # Nav2 dispatch + LLM failure recovery
├── launch/
│   └── naturalnav.launch.py  # Bringup launch file
└── config/
    └── naturalnav_params.yaml
docker/
└── entrypoint.sh             # Sources ROS2 before every container command
```

---

## ROS2 Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/natural_nav/command` | `std_msgs/String` | Natural language input |
| `/natural_nav/task_graph` | `std_msgs/String` | JSON task graph from LLM |
| `/natural_nav/fleet_status` | `std_msgs/String` | JSON per-robot task status |
| `/natural_nav/detections` | `std_msgs/String` | JSON semantic detections |
| `/natural_nav/semantic_map` | `std_msgs/String` | JSON open-vocab semantic map |
| `/natural_nav/planner_status` | `std_msgs/String` | Human-readable planner log |
| `/robot_1/navigate_to_pose` | Nav2 action | Robot 1 navigation goal |
| `/robot_2/navigate_to_pose` | Nav2 action | Robot 2 navigation goal |
| `/robot_1/camera/image_raw` | `sensor_msgs/Image` | Robot 1 camera feed |
| `/robot_2/camera/image_raw` | `sensor_msgs/Image` | Robot 2 camera feed |

---

## Configuration

LLM provider is configurable via environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_PROVIDER` | Provider name | `anthropic`, `openai` |
| `LLM_API_KEY` | API key | `sk-ant-...` |
| `LLM_MODEL` | Model name | `claude-sonnet-4-6`, `gpt-4o` |

---

## Demo

<!-- TODO: insert GIF here -->

---

## Development

### Build locally (without Docker)

```bash
source /opt/ros/jazzy/setup.bash
cd /path/to/natural_nav_ws
colcon build --symlink-install --packages-select natural_nav
source install/setup.bash
ros2 launch natural_nav naturalnav.launch.py
```

---

## Roadmap

- [x] LLM task decomposition
- [x] Dynamic task allocation (availability + proximity)
- [x] Fleet orchestration with Nav2 action clients
- [x] LLM-driven failure recovery / replanning
- [x] CLIP + GroundingDINO semantic detector
- [x] Multi-stage Docker build
- [ ] Gazebo warehouse world with 2x TurtleBot3
- [ ] Live semantic map visualization in RViz
- [ ] GroundingDINO model weight download script
- [ ] Demo video / GIF

---

## License

Apache 2.0
