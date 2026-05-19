"""
Launches Gazebo with a local world (no fuel downloads) + 2x TurtleBot3 Waffle
namespaced as robot_1 and robot_2, with robot_state_publisher, ROS-Gazebo
bridges, and camera image bridges per robot.
"""

import os
import tempfile
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

from natural_nav.spawn_helper import namespace_sdf


def generate_launch_description():
    tb3_gazebo = get_package_share_directory('turtlebot3_gazebo')
    natural_nav = get_package_share_directory('natural_nav')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')

    waffle_sdf = os.path.join(tb3_gazebo, 'models', 'turtlebot3_waffle', 'model.sdf')
    waffle_urdf = os.path.join(tb3_gazebo, 'urdf', 'turtlebot3_waffle.urdf')
    world = os.path.join(natural_nav, 'worlds', 'naturalnav.world')

    with open(waffle_urdf, 'r') as f:
        robot_desc = f.read()

    # Generate per-robot SDFs with namespaced sensor/plugin topics so two
    # identical robots don't collide on /camera/image_raw, /scan, etc.
    tmp_dir = tempfile.mkdtemp(prefix='naturalnav_sdf_')
    robot1_sdf = os.path.join(tmp_dir, 'robot_1.sdf')
    robot2_sdf = os.path.join(tmp_dir, 'robot_2.sdf')
    namespace_sdf(waffle_sdf, 'robot_1', robot1_sdf)
    namespace_sdf(waffle_sdf, 'robot_2', robot2_sdf)

    # ── Make Gazebo aware of TurtleBot3 models ────────────────────────────────
    set_model_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        os.path.join(tb3_gazebo, 'models'),
    )

    # ── Gazebo server + client ────────────────────────────────────────────────
    gz_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': f'-r -s -v2 {world}', 'on_exit_shutdown': 'true'}.items(),
    )

    gz_client = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': '-g -v2'}.items(),
    )

    # ── robot_state_publisher per robot (needed for TF + sensor activation) ──
    rsp_robot1 = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher_robot1',
        namespace='robot_1',
        parameters=[{
            'use_sim_time': True,
            'robot_description': robot_desc,
            'frame_prefix': 'robot_1/',
        }],
        output='screen',
    )

    rsp_robot2 = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher_robot2',
        namespace='robot_2',
        parameters=[{
            'use_sim_time': True,
            'robot_description': robot_desc,
            'frame_prefix': 'robot_2/',
        }],
        output='screen',
    )

    # ── Spawn robots (delayed to let Gazebo initialize) ───────────────────────
    spawn_robot1 = TimerAction(period=5.0, actions=[
        Node(
            package='ros_gz_sim',
            executable='create',
            arguments=['-name', 'robot_1', '-file', robot1_sdf,
                       '-x', '-1.0', '-y', '0.0', '-z', '0.01'],
            output='screen',
        )
    ])

    spawn_robot2 = TimerAction(period=5.0, actions=[
        Node(
            package='ros_gz_sim',
            executable='create',
            arguments=['-name', 'robot_2', '-file', robot2_sdf,
                       '-x', '1.0', '-y', '0.0', '-z', '0.01'],
            output='screen',
        )
    ])

    # ── ROS-Gazebo topic bridges ──────────────────────────────────────────────
    bridge_robot1 = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='bridge_robot1',
        arguments=['--ros-args', '-p',
                   f'config_file:={os.path.join(natural_nav, "config", "robot1_bridge.yaml")}'],
        output='screen',
    )

    bridge_robot2 = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='bridge_robot2',
        arguments=['--ros-args', '-p',
                   f'config_file:={os.path.join(natural_nav, "config", "robot2_bridge.yaml")}'],
        output='screen',
    )

    # ── Camera image bridges ──────────────────────────────────────────────────
    image_bridge_robot1 = Node(
        package='ros_gz_image',
        executable='image_bridge',
        name='image_bridge_robot1',
        arguments=['/robot_1/camera/image_raw'],
        output='screen',
    )

    image_bridge_robot2 = Node(
        package='ros_gz_image',
        executable='image_bridge',
        name='image_bridge_robot2',
        arguments=['/robot_2/camera/image_raw'],
        output='screen',
    )

    return LaunchDescription([
        set_model_path,
        gz_server,
        gz_client,
        rsp_robot1,
        rsp_robot2,
        spawn_robot1,
        spawn_robot2,
        bridge_robot1,
        bridge_robot2,
        image_bridge_robot1,
        image_bridge_robot2,
    ])
