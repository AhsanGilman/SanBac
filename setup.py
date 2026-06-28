from setuptools import setup, find_packages

setup(
    name="sanbac",
    version="1.3",
    description="SanBac: A modular, multithreaded bacterial genomics analysis pipeline",
    author="Antigravity",
    packages=find_packages(),
    install_requires=[
        "click>=8.0.0",
        "requests>=2.25.0",
        "packaging>=21.0",
        "cgecore>=1.5.5",
        "tabulate>=0.7.7",
    ],
    entry_points={
        "console_scripts": [
            "sanbac=sanbac.main:main",
        ],
    },
    python_requires=">=3.9",
)
