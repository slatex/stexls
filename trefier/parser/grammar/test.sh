#!/bin/bash

rm -rf test_dir && antlr4 -o test_dir *.g4 && \
    (cd out_test && javac *.java && grun SmglomLatex main -gui "$1")
