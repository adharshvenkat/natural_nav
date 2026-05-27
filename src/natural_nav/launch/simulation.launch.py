"""
NaturalNav simulation: TurtleBot4 (OAK-D RGBD camera + lidar) in the official
Nav2 warehouse world. Thin wrapper around nav2_minimal_tb4_sim so we track the
maintained reference sim and only layer our perception/LLM nodes on top.

Camera topics (verified): /rgbd_camera/image, /rgbd_camera/depth_image,
/rgbd_camera/camera_info  (all ~10 Hz).
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    tb4_sim = get_package_share_directory('nav2_minimal_tb4_sim')

    default_world = os.path.join(tb4_sim, 'worlds', 'warehouse.sdf')

    declare_world = DeclareLaunchArgument(
        'world',
        default_value=default_world,
        description='Full path to the Gazebo world file (default: warehouse)',
    )
    declare_headless = DeclareLaunchArgument(
        'headless',
        default_value='False',
        description='Run Gazebo without the GUI client if True',
    )

    tb4_simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb4_sim, 'launch', 'simulation.launch.py')
        ),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'headless': LaunchConfiguration('headless'),
        }.items(),
    )

    return LaunchDescription([
        declare_world,
        declare_headless,
        tb4_simulation,
    ])
