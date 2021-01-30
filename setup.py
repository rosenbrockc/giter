#!/usr/bin/env python
try:
    from setuptools import setup
    args = {}
except ImportError:
    from distutils.core import setup
    print("""\
*** WARNING: setuptools is not found.  Using distutils...
""")

from setuptools import setup
setup(name='giter',
      version='0.0.2',
      description='Wrapper functions to help with branches and submodules in `happyai`.',
      author='Happy Health',
      author_email='developer@happy.ai',
      url='',
      #license='GPL-3.0',
      packages=['giter'],
      classifiers=[
          'Development Status :: 2 - Pre-Alpha',
          'Natural Language :: English',
          'Operating System :: MacOS',
          'Operating System :: Unix',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.7'
      ],
     )
