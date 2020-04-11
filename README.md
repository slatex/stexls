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

To view the current progress, you can also specify the `--progress-indicator` argument.
This will display three loading bars. First for parsing, second for compiling and the
third is for linking.

Use `--view-graph` in junction with `--file` to view the import-graph of that file,
in case you want to debug something.

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

# Quirks and Bugs

1. Calling stexls again after some changes always parses and compiles the files changed from the last call, but files that depend on the changed files
are only relinked if the set of generated or imported symbols change. This may cause some location data to be messed up, but can be easily fixed by
writing to the file where the data is wrong.
2. Nested inline environments are not parsed properly. This causes symbols to not be parsed properly: For example `symbol` in `\\inlinedef{... \\defi{symbol} ...}` will not be added to the exported symbols.
3. If a module is already imported indirectly by another import it will only display the *module that can be removed beginning at <location>*, follwed by
where the module is already imported (example: `<location> - LinkWarning - Module "function-properties/MODULE" previously imported at "MathHub/MiKoMH/GenCS/source/dmath/en/cardinality.tex:3:1"`). This makes it difficult to verify the error but the import stack is not tracked properly. Use `--file {file} --view-graph` to
get an overview of the import graph in case you want to verify the decision to remove the reported location.
4. Import statements are only local to the module they are in. But there are some imports that should be local to {omdoc} and {definition} environments.
These environments are not tracked, which is why there are some false positives like: `LinkWarning - Multiple imports of module "peano-axioms/MODULE", first imported in line 28, column 6.`
5. Noverbs are tracked but not handled yet.
6. Some argument given over the cli are bound to the cache. To change them you have to delete the cache.
