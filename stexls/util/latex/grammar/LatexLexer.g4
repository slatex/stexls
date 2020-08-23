lexer grammar LatexLexer;

WS: [ \t\r\n]+ -> skip;
COMMENT: '%' ~('\n')* -> skip;
OPEN_BRACE: '{';
CLOSED_BRACE: '}';
OPEN_BRACKET: '[';
CLOSED_BRACKET: ']';
EQUALS: '=';
COMMA: ',';

MATH_OPEN_1: '$' -> more, pushMode(MATH1);
MATH_OPEN_2: '$$' -> more, pushMode(MATH2);
MATH_OPEN_3: '\\(' -> more, pushMode(MATH3);
MATH_OPEN_4: '\\[' -> more, pushMode(MATH4);

MATH_ENV
    : '\\begin' WS? '{' WS? 'math' WS? '}' .*? '\\end' WS? '{' WS? 'math' WS? '}'
    | '\\begin' WS? '{' WS? 'math' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'math' WS? '*' WS? '}'
    | '\\begin' WS? '{' WS? 'displaymath' WS? '}' .*? '\\end' WS? '{' WS? 'displaymath' WS? '}'
    | '\\begin' WS? '{' WS? 'displaymath' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'displaymath' WS? '*' WS? '}'
    | '\\begin' WS? '{' WS? 'align' WS? '}' .*? '\\end' WS? '{' WS? 'align' WS? '}'
    | '\\begin' WS? '{' WS? 'align' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'align' WS? '*' WS? '}'
    | '\\begin' WS? '{' WS? 'flalign' WS? '}' .*? '\\end' WS? '{' WS? 'flalign' WS? '}'
    | '\\begin' WS? '{' WS? 'flalign' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'flalign' WS? '*' WS? '}'
    | '\\begin' WS? '{' WS? 'flmath' WS? '}' .*? '\\end' WS? '{' WS? 'flmath' WS? '}'
    | '\\begin' WS? '{' WS? 'flmath' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'flmath' WS? '*' WS? '}'
    | '\\begin' WS? '{' WS? 'equation' WS? '}' .*? '\\end' WS? '{' WS? 'equation' WS? '}'
    | '\\begin' WS? '{' WS? 'equation' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'equation' WS? '*' WS? '}'
    | '\\begin' WS? '{' WS? 'verbatim' WS? '}' .*? '\\end' WS? '{' WS? 'verbatim' WS? '}'
    | '\\begin' WS? '{' WS? 'verbatim' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'verbatim' WS? '*' WS? '}'
    | '\\begin' WS? '{' WS? 'lstlisting' WS? '}' .*? '\\end' WS? '{' WS? 'lstlisting' WS? '}'
    | '\\begin' WS? '{' WS? 'lstlisting' WS? '*' WS? '}' .*? '\\end' WS? '{' WS? 'lstlisting' WS? '*' WS? '}'
    ;

ESCAPE: '\\' -> skip, pushMode(ESCAPE_MODE);

TEXT: ~('$'|'['|'{'|'%'|'}'|']'|'\\'|','|'=')+;

mode MATH1;
MATH_CLOSE_1: '$' -> popMode, type(MATH_ENV);
MATH_TOKEN_1: '\\'? . -> more;

mode MATH2;
MATH_CLOSE_2: '$$' -> popMode, type(MATH_ENV);
MATH_TOKEN_2: '\\'? . -> more;

mode MATH3;
MATH_ESCAPE_3: '\\)' -> popMode, type(MATH_ENV);
MATH_TOKEN_3: '\\'? . -> more;

mode MATH4;
MATH_ESCAPE_4: '\\]' -> popMode, type(MATH_ENV);
MATH_TOKEN_4: '\\'? . -> more;

mode ESCAPE_MODE;
VERBATIM: ('newenvironment' | 'verbatim' | 'newcommand' | 'lstinline' | 'verb' | 'visible') '*'? -> skip, mode(INLINE_VERBATIM_MODE_WITH_SPECIAL);
BEGIN: 'begin' -> popMode;
END: 'end' -> popMode;
INLINE_ENV_NAME: [a-zA-Z_]+ '*'? -> popMode;
ESCAPED_TEXT: . -> popMode, type(TEXT);

mode INLINE_VERBATIM_MODE_WITH_SPECIAL;

INLINE_SPECIAL1: '!' ~('!')* '!' -> type(TEXT), popMode;
INLINE_SPECIAL2: '-' ~('-')* '-' -> type(TEXT), popMode;
INLINE_SPECIAL3: '|' ~('|')* '|' -> type(TEXT), popMode;
INLINE_SPECIAL4: '<' ~('>')* '>' -> skip, popMode;
INLINE_SPECIAL5: '+' ~('+')* '+' -> type(TEXT), popMode;

NO_SPECIAL_VERBATIM_FOUND: -> skip, mode(INLINE_VERBATIM_MODE);

mode INLINE_VERBATIM_MODE;

INLINE_VERBATIM_ENV: '\\' [a-zA-Z0-9_]+ -> skip;
INLINE_VERBATIM_RARG: '{' (INLINE_VERBATIM_RARG | INLINE_VERBATIM_OARG | .)*? '}' -> type(TEXT);
INLINE_VERBATIM_OARG: '[' (INLINE_VERBATIM_OARG | INLINE_VERBATIM_RARG | .)*? ']' -> skip;

INLINE_VERBATIM_END: -> skip, popMode;
