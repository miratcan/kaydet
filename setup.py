from setuptools import setup
from src.kaydet import __author__, __version__, __description__


with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="kaydet",
    version=__version__,
    author=__author__,
    description=__description__,
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="diary tui",
    url="https://github.com/miratcan/logme",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Information Technology",
        "Natural Language :: English",
        "Topic :: Utilities",
        "Topic :: Utilities",
        "Topic :: Utilities",
        "Topic :: Utilities"
    ],
    python_requires=">=3.4",
    entry_points={"console_scripts": ["kaydet=kaydet:main"]},
)
