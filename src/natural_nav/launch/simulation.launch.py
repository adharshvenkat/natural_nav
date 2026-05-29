"""
NaturalNav simulation + navigation: TurtleBot4 (OAK-D RGBD camera + lidar) in the
official Nav2 warehouse world, with the full Nav2 stack (localization on a
pre-built warehouse map, planner, controller, RViz).

Thin wrapper around nav2_bringup's tb4_simulation_launch.py so we ride the
maintained reference stack and only layer our perception/LLM nodes on top.

Camera topics (verified ~10 Hz): /rgbd_camera/image, /rgbd_camera/depth_image,
/rgbd_camera/camera_info
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    nav2_bringup = get_package_share_directory('nav2_bringup')
    tb4_sim = get_package_share_directory('nav2_minimal_tb4_sim')

    default_world = os.path.join(tb4_sim, 'worlds', 'warehouse.sdf')
    default_map = os.path.join(nav2_bringup, 'maps', 'warehouse.yaml')

    declare_world = DeclareLaunchArgument(
        'world', default_value=default_world,
        description='Gazebo world file (default: warehouse)',
    )
    declare_map = DeclareLaunchArgument(
        'map', default_value=default_map,
        description='Nav2 map yaml (default: warehouse)',
    )
    declare_headless = DeclareLaunchArgument(
        'headless', default_value='False',
        description='Run Gazebo without GUI if True',
    )
    declare_rviz = DeclareLaunchArgument(
        'use_rviz', default_value='True',
        description='Start RViz if True',
    )

    # Full reference stack: Gazebo + TB4 + Nav2 + localization + RViz
    tb4_full = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup, 'launch', 'tb4_simulation_launch.py')
        ),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'map': LaunchConfiguration('map'),
            'headless': LaunchConfiguration('headless'),
            'use_rviz': LaunchConfiguration('use_rviz'),
        }.items(),
    )

    return LaunchDescription([
        declare_world,
        declare_map,
        declare_headless,
        declare_rviz,
        tb4_full,
    ])
