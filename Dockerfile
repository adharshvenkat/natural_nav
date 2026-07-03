# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder
# Installs build tools, compiles GroundingDINO C++ extensions, builds the
# natural_nav ROS2 package. Nothing from this stage leaks into runtime.
# ─────────────────────────────────────────────────────────────────────────────
FROM osrf/ros:jazzy-desktop AS builder

ENV DEBIAN_FRONTEND=noninteractive

# ROS binary deps + build tools (CUDA toolkit needed for GroundingDINO's CUDA ops)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-nav2-minimal-tb4-sim \
    ros-jazzy-nav2-minimal-tb4-description \
    ros-jazzy-cv-bridge \
    ros-jazzy-sensor-msgs \
    build-essential \
    git \
    nvidia-cuda-toolkit \
    && rm -rf /var/lib/apt/lists/*

# CUDA env for GroundingDINO's setup.py to detect and compile its ms_deform_attn op
ENV CUDA_HOME=/usr
ENV FORCE_CUDA=1
# Target the GTX 1650 Ti's compute capability (7.5). Add more if you target other GPUs.
ENV TORCH_CUDA_ARCH_LIST="7.5"

# Step 1: torch must be installed before GroundingDINO, since its setup.py imports torch
RUN pip install --no-cache-dir --break-system-packages \
    --index-url https://download.pytorch.org/whl/cu124 \
    "torch==2.6.*" "torchvision==0.21.*"

# Step 2a: deps that may try to upgrade torch, installed with explicit cu124 index
# so any transitive torch reinstall keeps the matching CUDA wheel.
# --ignore-installed numpy: apt-managed numpy can't be removed by pip; install ours alongside.
RUN pip install --no-cache-dir --break-system-packages --ignore-installed numpy \
    --extra-index-url https://download.pytorch.org/whl/cu124 \
    "numpy<2" \
    "transformers<5" \
    "tokenizers<0.22" \
    "huggingface-hub<1.0" \
    anthropic openai ollama

# Step 2b: CLIP + GroundingDINO with --no-deps so their loose `torch` requirement
# doesn't pull cu130 from PyPI. Their transitive deps are already covered above
# (transformers, timm, opencv, etc) or installed explicitly here.
RUN pip install --no-cache-dir --break-system-packages --ignore-installed scipy \
    --extra-index-url https://download.pytorch.org/whl/cu124 \
    "torch==2.6.*" "torchvision==0.21.*" \
    "numpy<2" \
    "huggingface-hub<1.0" \
    "timm<=1.0.19" "addict" "yapf" "supervision" "pycocotools" "opencv-python" \
    "ftfy" "regex" "tqdm"
RUN pip install --no-cache-dir --break-system-packages --no-deps \
    "git+https://github.com/openai/CLIP.git"

# Clone GroundingDINO, patch the .cu file for torch 2.x ScalarType API, then install.
# Upstream still ships the deprecated tensor.type() call which fails to compile on torch 2.6.
RUN git clone --depth=1 https://github.com/IDEA-Research/GroundingDINO.git /tmp/gdino \
    && sed -i \
        -e 's/\([a-zA-Z_]\+\)\.type()\.is_cuda()/\1.is_cuda()/g' \
        -e 's/\([a-zA-Z_]\+\)\.type()/\1.scalar_type()/g' \
        /tmp/gdino/groundingdino/models/GroundingDINO/csrc/MsDeformAttn/ms_deform_attn_cuda.cu \
    && pip install --no-cache-dir --break-system-packages --no-deps /tmp/gdino \
    && rm -rf /tmp/gdino

# Build the natural_nav ROS2 package
WORKDIR /naturalnav_ws
COPY src/ src/
RUN . /opt/ros/jazzy/setup.sh && \
    colcon build \
        --cmake-args -DCMAKE_BUILD_TYPE=Release \
        --packages-select natural_nav


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
# Clean base: copies only built artifacts from builder.
# No compilers, no pip cache, no build-essential.
# ─────────────────────────────────────────────────────────────────────────────
FROM osrf/ros:jazzy-desktop AS runtime

ENV DEBIAN_FRONTEND=noninteractive

# Runtime deps only (no build tools)
# ros:jazzy-desktop base already includes Gazebo; we add robot-specific pkgs
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-nav2-minimal-tb4-sim \
    ros-jazzy-nav2-minimal-tb4-description \
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
