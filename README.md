# Introduction

This is an command line interface for the smglom glossary linter.

# Installation

## Python 3.7

Python 3.7 is required because the application is large and
I needed the type annotation

## Dependencies

Install the pip dependencies by running

> pip -r requirements.txt

That's it.

# Usage

## Start the linter by running:

> python -m trefier.app.linter

## For more information use:

> python -m trefier.app.linter --help

You can also get help on any command at any time during execution:

> help update

## Most important are

### Add watched files with:

> --root PATH

Path to a root folder from which recursively ALL \*\*/source/\*.tex files will be added to the internal file watcher.

### Enable tagging with:

> --tagger PATH

Allows to specify the path to a *.model and enables automated tagging. Tensorflow will automaticall use the Memory of your whole GPU if it can.

### Enable fast restarts with:

> --cache PATH

Automatically writes a cache binary file to the specified file on exit and loads on restart.

## Interact with the linter

The linter will do nothing after you start it.
You can interact with the linter by typing in commands.
Commands can be inspected by typing "help" at any time.
After the linter starts and if you specified a --root path, you
probably want to type "update" in order to initiate the first update.

# The "update" command:

The most important command while the linter is running.
Run it anytime a file was changed.
The linter will update all the files and generate a report of the added
files by simply printing a JSON object to stdout.

To run in just type

> update

# Other features:

There are a lot of commands the linter has.

## complete

Use for example complete FILE CONTEXT in order to generate autocompletions
using FILE as root. The printed JSON output are a list of strings that
would complete CONTEXT. For example:

> complete path/to/sets.en.tex "\trefi[?"

Will return something indicating that the symbol "set" would complete
this context.

## Definitions

Use:
> find-definitions FILE LINE COLUMN

To query the definitions of the symbol in given file
at the given line and column.

# Logs

Logs are always written to "~/.trefier/linter.log".
This file may get big and you should delete it sometimes.
It and the folder ("~/.trefier") will always be automatically recreated when running the linter.

