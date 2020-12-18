import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="stexls",
    version="4.4.0",
    author="Marian Plivelic",
    author_email="MarianPlivelic@gmail.com",
    description="Language server and other utilities for STex.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/slatex/stexls",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
    ],
    python_requires='>=3.7',
    install_requires=[
        'antlr4-python3-runtime>=4.8',
        'tqdm',
    ],
    extras_require = {
        'ml': ['numpy', 'scikit-learn', 'nltk', 'tensorflow'],
    },
    package_data = {
        'stexls': ['*.model']
    }
)
