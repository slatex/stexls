import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="stexls",
    version="0.0.1",
    author="Marian Plivelic",
    author_email="MarianPlivelic@gmail.com",
    description="Language server and other utilities for STex.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gl.kwarc.info/Marian6814/trefier-backend",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
    install_requires=[
        'numpy',
        'scikit-learn',
        'antlr4-python3-runtime',
        'nltk',
        'tqdm',
        #'tensorflow-gpu >= 1.15',
    ]
)
