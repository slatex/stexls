#!/bin/bash

rm -rf out_test && antlr4 -o out_test *.g4 && \
    (cd out_test && javac *.java && grun Latex main -gui "$1")
