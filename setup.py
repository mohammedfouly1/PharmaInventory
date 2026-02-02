#!/usr/bin/env python3
"""
Setup configuration for GS1 Barcode Parser
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="gs1-barcode-parser",
    version="1.0.0",
    author="GS1 Parser Team",
    author_email="",
    description="Production-grade GS1 barcode parser for strings without separators",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourrepo/gs1-barcode-parser",
    packages=find_packages(exclude=["tests", "tests.*", "docs", "examples", "scripts"]),
    package_data={
        "gs1_parser": [
            "data/*.json",
            "data/*.csv",
        ],
    },
    include_package_data=True,
    python_requires=">=3.7",
    install_requires=[
        # No external dependencies for core functionality
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "gs1-parse=cli.parse_barcode:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Healthcare Industry",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    keywords="gs1 barcode parser pharmaceutical gtin healthcare no-separator",
    project_urls={
        "Documentation": "https://github.com/yourrepo/gs1-barcode-parser/docs",
        "Source": "https://github.com/yourrepo/gs1-barcode-parser",
        "Tracker": "https://github.com/yourrepo/gs1-barcode-parser/issues",
    },
)
