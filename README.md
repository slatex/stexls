# Introduction

This is the language server for stex, implemented in python.

# Python 3.7

Python 3.7 (or higher) is required because the application is large and I needed the type annotations.
I testet it with 3.7, 3.8 and 3.9-dev.

# Installation

1. Download this repository: `git clone --depth=1 https://gl.kwarc.info/Marian6814/trefier-backend.git stexls`
2. Then simply install with pip: `pip install stexls/`
3. Verify installation with `python -m stexls --version`

Note: This is an installation from local files and not from the official pip distribution.

# Uninstallation

1. Uninstall using pip: `pip uninstall stexls`

# Features

Analyzes the whole workspace provided with the `--root` argument for stex symbols and
modules.


A list of errors will be printet to stdout, where by default the each line begins with
{filename}:{line}:{column}. This should be easily parsable by most editors.


You can additionally enable the `--tagfile [name]` flag to generate a file named `tags` (changeable)
with the definitions of all symbols and modules.
Symbols appear at least twice. Once with just the symbol name, and a second time prefixed with
the name of the module followed by a questionmark (?) and then the symbol name again.
For example: the symbol "balanced-prime" in the module "balancedprime" can be queried by
the "balanced-prime" tag, as well as the "balancedprime?balanced-prime" tag.


A full report of a single file can be created using the `--file` argument.
This will output a huge list of all imported files, dependencies, symbols, references and
errors related to only this file.
Use this in case you want to know why something doesn't work.

# Usage

This is a preview build and only has a small portion of commands available:

To use this program use: `python -m stexls`


The help dialog can guide you through what you can do if you forget.
The most common usage is probably the following:


`python -m stexls --cache /tmp/stexls.bin --root $MATH_HUB_DIR --tagfile`


This writes the full error report to stdout and generates the tagfile
in the root directory.

# Tips

Make an alias `alias stexls="python -m stexls"` or create an
executable script in your path containing the following lines:

> #!/bin/bash
> python -m stexls $@
