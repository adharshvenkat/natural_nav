# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder
# Installs build tools, compiles GroundingDINO C++ extensions, builds the
# natural_nav ROS2 package. Nothing from this stage leaks into runtime.
# ─────────────────────────────────────────────────────────────────────────────
FROM ros:jazzy-desktop AS builder

ENV DEBIAN_FRONTEND=noninteractive

# ROS binary deps + build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-turtlebot3 \
    ros-jazzy-turtlebot3-simulations \
    ros-jazzy-cv-bridge \
    ros-jazzy-sensor-msgs \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python ML dependencies
# numpy<2 required: system matplotlib compiled against NumPy 1.x
RUN pip install --no-cache-dir --break-system-packages \
    "numpy<2" \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    "git+https://github.com/openai/CLIP.git" \
    "git+https://github.com/IDEA-Research/GroundingDINO.git" \
    anthropic \
    openai

# Build the natural_nav ROS2 package
WORKDIR /naturalnav_ws
COPY src/ src/
RUN . /opt/ros/jazzy/setup.sh && \
    colcon build --symlink-install \
        --cmake-args -DCMAKE_BUILD_TYPE=Release \
        --packages-select natural_nav


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
# Clean base — copies only built artifacts from builder.
# No compilers, no pip cache, no build-essential.
# ─────────────────────────────────────────────────────────────────────────────
FROM ros:jazzy-desktop AS runtime

ENV DEBIAN_FRONTEND=noninteractive

# Runtime deps only (no build tools)
# ros:jazzy-desktop base already includes Gazebo — we add robot-specific pkgs
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-turtlebot3 \
    ros-jazzy-turtlebot3-simulations \
    ros-jazzy-cv-bridge \
    ros-jazzy-sensor-msgs \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled Python ML packages from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy built ROS workspace from builder
COPY --from=builder /naturalnav_ws/install /naturalnav_ws/install

WORKDIR /naturalnav_ws

# Source ROS and workspace on every shell invocation
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc && \
    echo "source /naturalnav_ws/install/setup.bash" >> /root/.bashrc

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

CMD ["ros2", "launch", "natural_nav", "naturalnav.launch.py"]
