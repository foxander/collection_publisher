import os

from setuptools import find_packages, setup

readme = open("README.rst").read()

history = open("CHANGES.rst").read()

install_requires = ["Shapely==1.8.5.post1",
                    "pandas==1.5.3",
                    "geopandas==0.12.2",
                    "pyproject==1.3.1",
                    "filelock==3.13.1",
                    "rasterio==1.3.9",
                    "netCDF4==1.6.5',
                    "bdc-catalog @ git+https://github.com/brazil-data-cube/bdc-catalog.git@v1.0.2#egg=bdc-catalog"
                    ]

packages = find_packages()

g = {}
with open(os.path.join("collection_publisher", "version.py"), "rt") as fp:
    exec(fp.read(), g)
    version = g["__version__"]

setup(
    name="collection-publisher",
    version=version,
    packages=packages,
    zip_safe=False,
    include_package_data=True,
    platforms="any",
    entry_points={
        'console_scripts': [
            'collection-publisher = collection_publisher.cli:cli',
        ],
    },
    install_requires=install_requires,
    classifiers=[
        "Development Status :: Alpha",
        "Environment :: Console",
        "Intended Audience :: Education",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: GIS",
   ]
)
