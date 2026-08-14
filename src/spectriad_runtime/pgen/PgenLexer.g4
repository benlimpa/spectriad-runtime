lexer grammar PgenLexer;

LPAR: '(' -> pushMode(CODE);
LBRACE: '{' -> pushMode(CODE);
LBRACK: '[' -> pushMode(CODE);
LANGLEBRAC: '<';
RANGLEBRAC: '>';
SEMI: ';';
COLON: ':';
PIPE: '|';
// THIS: 'this'; // postprocessed
ID: [a-zA-Z][a-zA-Z0-9_]*;
FLOAT: ([1-9][0-9]* | '0') ('.' [0-9]*)? | '.' [0-9]+;
STRING: '\'' ( ~[\r\n\\'] | '\\' . )* '\'';
TODO: '?';

WHITESPACE: [ \t\r\n]+ -> channel(HIDDEN);
COMMENT: '//' ~[\r\n]* -> channel(HIDDEN);

mode CODE;
    CODE_LPAR: '(' -> pushMode(CODE);
    CODE_LBRACE: '{' -> pushMode(CODE);
    CODE_LBRACK: '[' -> pushMode(CODE);
    CODE_SINGLE_QUOTE_OPEN: '\'' -> pushMode(CODE_SINGLE_QUOTE);
    CODE_DOUBLE_QUOTE_OPEN: '"' -> pushMode(CODE_DOUBLE_QUOTE);
    CODE_SEMI: ';';
    RPAR: ')' -> popMode;
    RBRACE: '}' -> popMode;
    RBRACK: ']' -> popMode;

    CODE_INIT_NO_PAIRS: ' '* 'new' ' '+ [A-Z][A-Z_]* (' '* '=' ~[{}[\]()'";=]+)?;
    CODE_NO_PAIRS: ~[{}[\]()'";]+;

mode CODE_SINGLE_QUOTE;
    CODE_SINGLE_QUOTE_STRING: ( ~[\r\n\\'] | '\\' . )* '\'' -> popMode;

mode CODE_DOUBLE_QUOTE;
    CODE_DOUBLE_QUOTE_STRING: ( ~[\r\n\\"] | '\\' . )* '"' -> popMode;
