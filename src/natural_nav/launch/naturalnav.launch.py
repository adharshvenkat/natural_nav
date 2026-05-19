import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('llm_provider', default_value=os.environ.get('LLM_PROVIDER', 'anthropic')),
        DeclareLaunchArgument('llm_api_key', default_value=os.environ.get('LLM_API_KEY', '')),
        DeclareLaunchArgument('llm_model', default_value=os.environ.get('LLM_MODEL', 'claude-sonnet-4-6')),

        Node(
            package='natural_nav',
            executable='llm_planner',
            name='llm_planner',
            parameters=[{
                'llm_provider': LaunchConfiguration('llm_provider'),
                'llm_api_key': LaunchConfiguration('llm_api_key'),
                'llm_model': LaunchConfiguration('llm_model'),
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
            }],
            output='screen',
        ),
        Node(
            package='natural_nav',
            executable='semantic_detector',
            name='semantic_detector',
            output='screen',
        ),
    ])
