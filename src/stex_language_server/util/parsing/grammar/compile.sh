#!/bin/bash

rm -rf out && antlr4 -o out -Dlanguage=Python3 *.g4