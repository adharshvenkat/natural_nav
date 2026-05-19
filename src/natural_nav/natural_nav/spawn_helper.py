#!/usr/bin/env python3
"""
Generates a namespaced TurtleBot3 Waffle SDF by rewriting relative sensor/plugin
topics to be prefixed with the robot's namespace. This avoids topic collisions
when spawning multiple identical robots in one Gazebo world.

Usage: spawn_helper.py <source_sdf> <namespace> <output_sdf>
"""

import sys
import re


# Topics in the waffle SDF that must be namespaced to avoid multi-robot collision
TOPIC_TAGS = ['topic', 'odom_topic', 'camera_info_topic']


def namespace_sdf(source_path: str, namespace: str, output_path: str) -> None:
    with open(source_path, 'r') as f:
        sdf = f.read()

    def prefix(match: re.Match) -> str:
        tag, value = match.group(1), match.group(2).strip()
        # Already absolute and pointing at /tf — keep global so RViz/nav2 see one tree
        if value == '/tf':
            return match.group(0)
        value = value.lstrip('/')
        return f'<{tag}>/{namespace}/{value}</{tag}>'

    pattern = re.compile(r'<(' + '|'.join(TOPIC_TAGS) + r')>([^<]+)</\1>')
    sdf = pattern.sub(prefix, sdf)

    # Namespace the tf_topic explicitly so each robot has its own TF
    sdf = sdf.replace('<tf_topic>/tf</tf_topic>',
                       f'<tf_topic>/{namespace}/tf</tf_topic>')

    with open(output_path, 'w') as f:
        f.write(sdf)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    namespace_sdf(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f'Wrote namespaced SDF: {sys.argv[3]}')
