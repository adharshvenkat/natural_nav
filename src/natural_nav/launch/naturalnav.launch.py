import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Everything here rides Gazebo's /clock. semantic_detector in particular
    # needs sim time so its TF lookups share the sim timebase with Nav2 and
    # robot_state_publisher; without it the transform buffer and the sim drift
    # apart and projections land in the wrong place (or fail to look up).
    use_sim_time = LaunchConfiguration('use_sim_time')

    return LaunchDescription([
        # Defaults match docker-compose / .env (local Ollama, zero-key). Set
        # LLM_PROVIDER / LLM_MODEL in .env to switch to a cloud provider.
        DeclareLaunchArgument('llm_provider', default_value=os.environ.get('LLM_PROVIDER', 'ollama')),
        DeclareLaunchArgument('llm_api_key', default_value=os.environ.get('LLM_API_KEY', '')),
        DeclareLaunchArgument('llm_model', default_value=os.environ.get('LLM_MODEL', 'qwen2.5:3b')),
        DeclareLaunchArgument('use_sim_time', default_value='true'),

        Node(
            package='natural_nav',
            executable='llm_planner',
            name='llm_planner',
            parameters=[{
                'llm_provider': LaunchConfiguration('llm_provider'),
                'llm_api_key': LaunchConfiguration('llm_api_key'),
                'llm_model': LaunchConfiguration('llm_model'),
                'use_sim_time': use_sim_time,
            }],
            output='screen',
        ),
        Node(
            package='natural_nav',
            executable='fleet_orchestrator',
            name='fleet_orchestrator',
            parameters=[{
                'llm_provider': LaunchConfiguration('llm_provider'),
                'llm_api_key': LaunchConfiguration('llm_api_key'),
                'llm_model': LaunchConfiguration('llm_model'),
                'use_sim_time': use_sim_time,
            }],
            output='screen',
        ),
        Node(
            package='natural_nav',
            executable='semantic_detector',
            name='semantic_detector',
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen',
        ),
    ])
