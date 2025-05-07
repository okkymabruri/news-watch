from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="news-watch",
    version="0.2.2",
    author="Okky Mabruri",
    author_email="okkymbrur@gmail.com",
    description="news-watch is a Python package that scrapes structured news data from Indonesia's top news websites, offering keyword and date filtering queries for targeted research.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/okkymabruri/news-watch",
    packages=find_packages(),
    install_requires=[
        "aiohttp==3.11.18",
        "beautifulsoup4==4.13.4",
        "dateparser==1.2.1",
        "openpyxl==3.1.5",
        "pandas==2.2.2",
        "requests==2.32.3",
    ],
    entry_points={
        "console_scripts": [
            "newswatch=newswatch.cli:cli",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
)
