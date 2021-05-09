parser grammar LatexParser;
options {
	tokenVocab = LatexLexer;
}

main: body* EOF;

body: math | env | inlineEnv | text | '{' body* '}';

math: MATH_ENV;

env: envBegin body* envEnd;

envBegin: BEGIN args+;

envEnd: END '{' TEXT '}';

inlineEnv: INLINE_ENV_NAME args?;

args: (rarg | oarg)+;

text: TEXT | '[' | ']' | '=' | ',';

rarg: '{' body* '}';

oarg: '[' arglist ']';

arglist: argument (',' argument)*;

argument: argumentName argumentValue? | argumentValue;

argumentName: name = TEXT '=';

argumentValue: body;
