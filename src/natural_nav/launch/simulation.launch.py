"""
Launches Gazebo with the NaturalNav world + a single TurtleBot3 Waffle (RGBD
camera + lidar). No namespace — topics are flat (/scan, /odom, /cmd_vel,
/camera/image_raw) to match Nav2's default expectations.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    tb3_gazebo = get_package_share_directory('turtlebot3_gazebo')
    natural_nav = get_package_share_directory('natural_nav')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')

    waffle_sdf = os.path.join(tb3_gazebo, 'models', 'turtlebot3_waffle', 'model.sdf')
    waffle_urdf = os.path.join(tb3_gazebo, 'urdf', 'turtlebot3_waffle.urdf')
    world = os.path.join(natural_nav, 'worlds', 'naturalnav.world')

    with open(waffle_urdf, 'r') as f:
        robot_desc = f.read()

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

    # ── robot_state_publisher (TF tree + sensor activation) ───────────────────
    rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'use_sim_time': True,
            'robot_description': robot_desc,
        }],
        output='screen',
    )

    # ── Spawn the robot (delayed to let Gazebo initialize) ────────────────────
    spawn_robot = TimerAction(period=5.0, actions=[
        Node(
            package='ros_gz_sim',
            executable='create',
            arguments=['-name', 'waffle', '-file', waffle_sdf,
                       '-x', '0.0', '-y', '0.0', '-z', '0.01'],
            output='screen',
        )
    ])

    # ── ROS-Gazebo topic bridge ───────────────────────────────────────────────
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
        arguments=['--ros-args', '-p',
                   f'config_file:={os.path.join(natural_nav, "config", "waffle_bridge.yaml")}'],
        output='screen',
    )

    # ── Camera image bridge ───────────────────────────────────────────────────
    image_bridge = Node(
        package='ros_gz_image',
        executable='image_bridge',
        name='image_bridge',
        arguments=['/camera/image_raw'],
        output='screen',
    )

    return LaunchDescription([
        set_model_path,
        gz_server,
        gz_client,
        rsp,
        spawn_robot,
        bridge,
        image_bridge,
    ])
