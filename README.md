# Introduction

This is the language server for stex, implemented in python.

# Installation

1. Download this repository: `git clone --depth=1 https://github.com/slatex/stexls`
2. Then simply install with pip: `pip install stexls/` (Note: This is an installation from local files and not from the official pip distribution.)
3. Verify installation with `python -m stexls --version`
4. Optional: Delete the downloaded repository.

## Update & Upgrade

Update by doing the installation instructions again, but add the `--upgrade` flag to the pip install command:

`pip install stexls/ --upgrade`

Then remove old cached files located in the directory you opened with VSCode by running `rm -r <root directory>/.stexls`.

## Install with extra packages

In order to use the trefier you need to specify that you want to download more dependencies:

Add `[ml]` to the directory path: `pip install stexls[ml]` or `pip install stexls[ml] --upgrade` if you want to upgrade.

# Uninstallation

Uninstall using pip: `pip uninstall stexls`

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

## Help

All commands also support help if needed:

`python -m stexls --help`

`python -m stexls linter --help`

`python -m stexls lsp --help`


# Cache

Cached data is stored in `<root>/.stexls/objects` and can be deleted
at any time.

Delete the cache everytime you update.
