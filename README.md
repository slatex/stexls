# Introduction

This is the language server for stex, implemented in python.

# Python 3.7

Python 3.7 (or higher) is required because the application is large and I needed the type annotations.
I testet it with 3.7, 3.8 and 3.9-dev.

# Installation

1. Download this repository: `git clone --depth=1 https://gl.kwarc.info/Marian6814/stexls.git`
2. Then simply install with pip: `pip install stexls/` (Note: This is an installation from local files and not from the official pip distribution.)
3. Verify installation with `python -m stexls --version`
4. Optional: Delete the downloaded repository.

# Uninstallation

1. Uninstall using pip: `pip uninstall stexls`

# Features

## Language Server

The main feature of this python module is, that it implements the language server protocol
and can be used by any edior that implements the language server client protocol.

The command that the client needs to run, in order to start the server is:

`python -m stexls lsp`


This will run the server using IPC as it's message transport kind.
If the client requires a tcp server you can also provide the `--transport-kind` argument to change it.

`python -m stexls lsp --transport-kind tcp --host localhost --port <port>`


This will run it in tcp mode and bind it to localhost at some port.


Nothing else is required to use the server as the protocol will do everything else.


## Linter


The extension also supports a lightweight "linter" mode, which takes
the root path of imports as well as file (or list of files) as input.

`python -m stexls linter --root ~/MathHub ${file}`


If you do not run this in an editor who parses the output to generate
in-editor error annotations you should always use the `--progress-indicator` or `-p`
flag to visualize the progress, as linting may take a long time if you input a lot of files.


Diagnostics are printed only for the files given as arguments.
You do not need to provide the files imported or otherwise related to the file you are interested in.
Imports and dependencies are automatically resolved relative to the value of the `--root` argument.


So the basic command from the command line should be something like the following if you want information
about the whole workspace.

`python -m stexls linter --progress-indicator --root ~/MathHub **/*.tex`


# Cache


Cached data is stored in `root`/.stexls/objects and can be deleted
at any time.

