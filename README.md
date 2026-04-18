# NaturalNav

**LLM-orchestrated semantic navigation for multi-robot fleets.**

> "Inspect shelf row 7, deliver any flagged item to workstation 3, and alert the fleet if the path is blocked."

NaturalNav accepts natural language commands and autonomously decomposes them into a multi-robot task graph, dispatches robots via Nav2, and recovers from failures using LLM replanning — all running in a single `docker compose up`.

---

## Architecture

```
Natural Language Command
        │
        ▼
┌─────────────────┐
│   LLM Planner   │  GPT-4o decomposes command → structured task graph
│  (llm_planner)  │
└────────┬────────┘
         │ /natural_nav/task_graph
         ▼
┌──────────────────────┐
│  Fleet Orchestrator  │  Dispatches tasks to robots, handles failure recovery
│ (fleet_orchestrator) │◄─── LLM replanner on failure
└────────┬─────────────┘
         │ /robot_N/navigate_to_pose (Nav2 action)
         ▼
┌─────────────────┐     ┌──────────────────────┐
│    Robot 1      │     │  Semantic Detector    │
│    Robot 2      │     │ (semantic_detector)   │
│    Robot 3      │     │  CLIP + GroundingDINO │
└─────────────────┘     └──────────────────────┘
     Nav2 / Gazebo           Camera topics
```

## Tech Stack

| Component | Tool |
|-----------|------|
| Simulation | Gazebo Harmonic |
| Navigation | Nav2 (binary, ros-jazzy) |
| Fleet management | Open-RMF (binary, ros-jazzy) |
| Semantic perception | CLIP + GroundingDINO |
| LLM planner | OpenAI GPT-4o |
| Containerization | Docker + Docker Compose |
| ROS2 distribution | Jazzy |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- An OpenAI API key

### Run

```bash
git clone https://github.com/YOUR_USERNAME/natural_nav.git
cd natural_nav

export OPENAI_API_KEY=sk-...
docker compose up
```

### Send a command

```bash
# In a new terminal
docker compose exec naturalnav \
  ros2 topic pub --once /natural_nav/command std_msgs/msg/String \
  '{"data": "Inspect shelf row 7 and deliver flagged items to workstation 3"}'
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
│   ├── llm_planner.py        # GPT-4o task decomposition node
│   ├── semantic_detector.py  # CLIP + GroundingDINO perception node
│   └── fleet_orchestrator.py # RMF dispatch + LLM failure recovery node
├── launch/
│   └── naturalnav.launch.py  # Bringup launch file
├── config/
│   └── naturalnav_params.yaml
└── worlds/                   # Gazebo warehouse world (coming soon)
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
| `/robot_N/navigate_to_pose` | Nav2 action | Per-robot navigation goal |

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

- [x] LLM task decomposition (GPT-4o)
- [x] Fleet orchestration with Nav2 action clients
- [x] LLM-driven failure recovery / replanning
- [x] CLIP + GroundingDINO semantic detector
- [x] Docker containerization
- [ ] Gazebo warehouse world with 3 robots
- [ ] Live semantic map visualization in RViz
- [ ] Demo video / GIF

---

## License

Apache 2.0
