import setuptools

with open('README.rst', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='mediaqueue',
    version='0.1.0',
    author='Niklas Graeber',
    author_email='dev@n1klas.net',
    description='Batch media downloader',
    url='https://github.com/ngdio/mediaqueue',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    packages=setuptools.find_packages(),
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Topic :: Internet',
        'Topic :: Multimedia',
    ],
    install_requires=[
        'click',
        'pillow',
        'pycountry',
        'youtube-dl',
    ],
    python_requires='>=3',
    entry_points={
        'console_scripts': [
            'mediaqueue=mediaqueue.core:main',
        ],
    },  
)