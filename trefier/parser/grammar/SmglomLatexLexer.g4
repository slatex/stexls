lexer grammar SmglomLatexLexer;

WS: [ \t\r\n]+ -> skip;

COMMENT: '%' .*? '\r'?'\n' -> skip;

OPEN_BRACKET: '[';
CLOSED_BRACKET: ']';
OPEN_BRACE: '{';
CLOSED_BRACE: '}';

MATH_ENV
    : '$$'.+?'$$'
    | '$'.+?'$'
    | '\\['.*?'\\]'
    | '\\(' .*? '\\)'
    | '\\begin' WS? '{' WS? 'math' WS? '}' .*? '\\end' WS? '{' WS? 'math' WS? '}'
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
    ;

BEGIN: '\\begin';

END: '\\end';

INLINE_ENV_NAME: '\\' [a-zA-Z_]+ '*'?;

TOKEN: (~('$'|'['|'{'|'%'|'}'|']'|'\\') | '\\' ('$'|'{'|'%'|'}'|'\\'|'!'|'@'|'#'|'^'|'&'|'*'|'_'|'+'|'-'|'\''|'|'|';'|':'|'"'|'<'|'>'|'?'|','|'.'|'/'|[rnt]))+;
