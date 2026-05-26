"""Setup for Artemis II Modular Unsupervised Discovery Platform."""

from setuptools import setup, find_packages

setup(
    name="artemis-ii-platform",
    version="0.2.3",
    description="Modular Unsupervised Discovery Platform for NASA Artemis II Challenge",
    author="ConductScience",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.24",
        "pandas>=2.0",
        "scipy>=1.10",
        "scikit-learn>=1.3",
        "umap-learn>=0.5",
        "hdbscan>=0.8",
        "ruptures>=1.1",
        "pymc>=5.0",
        "arviz>=0.15",
        "matplotlib>=3.7",
        "seaborn>=0.12",
        "plotly>=5.15",
        "streamlit>=1.30",
        "pyarrow>=12.0",
        "pyyaml>=6.0",
    ],
)
