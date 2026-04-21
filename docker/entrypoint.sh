#!/bin/bash
# Source ROS2 and the built workspace before executing the container command
set -e
source /opt/ros/jazzy/setup.bash
source /naturalnav_ws/install/setup.bash
exec "$@"
