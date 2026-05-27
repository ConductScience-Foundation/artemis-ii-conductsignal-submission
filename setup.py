"""Setup metadata for the ConductSignal Artemis II public demo."""

from setuptools import setup, find_packages

setup(
    name="conductsignal-artemis-public-demo",
    version="0.2.4",
    description="Public proxy-data demo for Artemis II-style individual health-change review",
    author="ConductScience",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[],
    extras_require={
        "rebuild": [
            "pandas>=2.0",
            "openpyxl>=3.1",
        ],
        "qa": [
            "pytest>=8.0",
        ],
    },
)
