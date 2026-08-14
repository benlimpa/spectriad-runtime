parser grammar PgenParser;

options {
    tokenVocab=PgenLexer;
}

start: nt_defn_list EOF;

nt_defn_list: (nt_defn)*;

nt_defn: nonterminal_variable COLON expansion_list SEMI
    ;

expansion_list: expansion (PIPE expansion)*
    ;

expansion: constraints? weight? term_list
    ;

term_list: stateful_block* term (term | stateful_block)*
    ;

term: terminal
    |   expression
    |   nonterminal_term
    ;

terminal: STRING
    ;

// must be above nonterminal_variable or else variable gets parsed by it
expression: variable? LBRACK code RBRACK
    ;

variable: ID
    ;

nonterminal_variable: ID
    ;

stateful_block: LBRACE function_list RBRACE
    ;

nonterminal_term: nonterminal_variable(constraints)?
    ;

constraints: LPAR code RPAR
    ;

weight: LANGLEBRAC FLOAT RANGLEBRAC
    ;

function_list: init_or_update (CODE_SEMI init_or_update)*
    ;

init_or_update: init
    | update
    ;

init: CODE_INIT_NO_PAIRS code?
    ;

update: code;

code:
    CODE_LPAR code? RPAR code?
    | CODE_LBRACE code? RBRACE code?
    | CODE_LBRACK code? RBRACK code?
    | CODE_SINGLE_QUOTE_OPEN CODE_SINGLE_QUOTE_STRING code?
    | CODE_DOUBLE_QUOTE_OPEN CODE_DOUBLE_QUOTE_STRING code?
    | CODE_NO_PAIRS code?
    ;
