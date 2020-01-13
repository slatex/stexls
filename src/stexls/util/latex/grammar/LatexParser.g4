parser grammar LatexParser;
options { tokenVocab=LatexLexer; }

main: body EOF;

body: (math | env | inlineEnv | token | '{' body '}' | '[' body ']')*;

inlineEnv: INLINE_ENV_NAME args?;

env: envBegin args? body envEnd;

envBegin: BEGIN '{' TOKEN '}';

envEnd: END '{' TOKEN '}';

math: MATH_ENV;

token: TOKEN;

oarg: '[' body ']';

rarg: '{' body '}';

args: (rarg | oarg)+;

