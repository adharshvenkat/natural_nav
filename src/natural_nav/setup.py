from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'natural_nav'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'worlds'), glob('worlds/*.world')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Adharsh Venkat',
    maintainer_email='adharsh.venkat98@gmail.com',
    description='Language-conditioned semantic navigation: LLM task planning + open-vocabulary perception on a mobile robot',
    license='Apache-2.0',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'llm_planner = natural_nav.llm_planner:main',
            'semantic_detector = natural_nav.semantic_detector:main',
            'fleet_orchestrator = natural_nav.fleet_orchestrator:main',
        ],
    },
)
