from setuptools import find_packages, setup

with open('README.md', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='octodns-xserver',
    version='0.0.1',
    description='XServer DNS provider for octoDNS',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='hosting-memo',
    url='https://github.com/hosting-memo/octodns-xserver',
    license='MIT',
    packages=find_packages(),
    python_requires='>=3.9',
    install_requires=[
        'octodns>=1.9.0',
        'requests>=2.28.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.0',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Topic :: Internet :: Name Service (DNS)',
    ],
    keywords='octodns dns xserver',
)
