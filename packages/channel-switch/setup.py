from setuptools import setup, find_packages
import os

def create_init_file(package_dir):
    init_file = os.path.join(package_dir, '__init__.py')
    if not os.path.exists(init_file):
        with open(init_file, 'w') as f:
            f.write("# This file was created by setup.py to mark the directory as a package.\n")

package_dir = "./src"

create_init_file(package_dir)

setup(
    name="channel-switch",
    version="1.0.0",
    author="Roopa Shanmugam",
    author_email="roopa.shanmugam@tii.ae",
    description="Resilient Mesh Automatic Channel Selection",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'channel-switch=src.rmacs_manager:main',
            'rmacs_server=src.rmacs_server_fsm:main',
            'rmacs_client=src.rmacs_client_fsm:main',
        ],
    },
    install_requires=[
        "pyyaml",  # For configuration handling
        "systemd", # For system logging integration
        "msgpack"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.8",
    include_package_data=True,
)
