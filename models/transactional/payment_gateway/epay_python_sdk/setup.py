import os
from setuptools import setup, find_packages

env = os.environ.get("ENV", "dev")

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="epay_python_sdk",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Python SDK for SBI ePay Payment Gateway",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/epay_python_sdk",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/epay_python_sdk/issues",
        "Source": "https://github.com/yourusername/epay_python_sdk",
        "Documentation": "https://github.com/yourusername/epay_python_sdk#readme",
    },
    packages=find_packages(where=".", include=["epay_python_sdk*"]),
    package_dir={"": "."},
    include_package_data=True,
    package_data={
        "epay_python_sdk": ["py.typed"],
    },
    keywords=["sbi", "epay", "payment", "gateway", "sdk", "fintech"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Office/Business :: Financial :: Point-Of-Sale",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Typing :: Typed",
    ],
    python_requires=">=3.7",
    install_requires=[
        "requests>=2.25.0",
        "cryptography>=3.4.0",
        "typing-extensions>=4.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.8",
            "mypy>=0.800",
            "responses>=0.18.0",
            "build>=0.7.0",
            "twine>=3.4.0",
            "tox>=3.20.0",
            "pre-commit>=2.15.0",
        ],
        "test": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "responses>=0.18.0",
            "pytest-mock>=3.6.0",
        ],
        "docs": [
            "sphinx>=4.0.0",
            "sphinx-rtd-theme>=1.0.0",
        ],
    },
    zip_safe=False,
)