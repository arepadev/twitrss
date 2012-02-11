#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

LONG_DESCRIPTION = """
Twitter bot based on libturpial that reads RSS feeds and tweet them on 
configured accounts.
"""

data_files=[
    ('./', ['README', 'COPYING']),
]

setup(name="twitrss",
    version='0.9',
    description="RSS Twitter bot",
    long_description=LONG_DESCRIPTION,
    author="Wil Alvarez",
    author_email="wil.alejandro@gmail.com",
    maintainer="Wil Alvarez",
    maintainer_email="wil.alejandro@gmail.com",
    url="http://github.com/arepadev/twitrss",
    download_url="http://github.com/arepadev/twitrss",
    license="GPLv3",
    keywords='twitter identi.ca microblogging rss bot',
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2.5",
        "Topic :: Communications",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules"
    ],
    entry_points={
        'console_scripts': [
            'twitrss = twitrss:TwitRss',
        ],
      },
    packages=find_packages(),
    data_files=data_files,
)
