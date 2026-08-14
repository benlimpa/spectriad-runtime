# Generated from PgenParser.g4 by ANTLR 4.13.1
# encoding: utf-8
from antlr4 import *
from io import StringIO
import sys
if sys.version_info[1] > 5:
	from typing import TextIO
else:
	from typing.io import TextIO

def serializedATN():
    return [
        4,1,27,177,2,0,7,0,2,1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,2,5,7,5,2,6,7,
        6,2,7,7,7,2,8,7,8,2,9,7,9,2,10,7,10,2,11,7,11,2,12,7,12,2,13,7,13,
        2,14,7,14,2,15,7,15,2,16,7,16,2,17,7,17,2,18,7,18,2,19,7,19,1,0,
        1,0,1,0,1,1,5,1,45,8,1,10,1,12,1,48,9,1,1,2,1,2,1,2,1,2,1,2,1,3,
        1,3,1,3,5,3,58,8,3,10,3,12,3,61,9,3,1,4,3,4,64,8,4,1,4,3,4,67,8,
        4,1,4,1,4,1,5,5,5,72,8,5,10,5,12,5,75,9,5,1,5,1,5,1,5,5,5,80,8,5,
        10,5,12,5,83,9,5,1,6,1,6,1,6,3,6,88,8,6,1,7,1,7,1,8,3,8,93,8,8,1,
        8,1,8,1,8,1,8,1,9,1,9,1,10,1,10,1,11,1,11,1,11,1,11,1,12,1,12,3,
        12,109,8,12,1,13,1,13,1,13,1,13,1,14,1,14,1,14,1,14,1,15,1,15,1,
        15,5,15,122,8,15,10,15,12,15,125,9,15,1,16,1,16,3,16,129,8,16,1,
        17,1,17,3,17,133,8,17,1,18,1,18,1,19,1,19,3,19,139,8,19,1,19,1,19,
        3,19,143,8,19,1,19,1,19,3,19,147,8,19,1,19,1,19,3,19,151,8,19,1,
        19,1,19,3,19,155,8,19,1,19,1,19,3,19,159,8,19,1,19,1,19,1,19,3,19,
        164,8,19,1,19,1,19,1,19,3,19,169,8,19,1,19,1,19,3,19,173,8,19,3,
        19,175,8,19,1,19,0,0,20,0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,
        30,32,34,36,38,0,0,184,0,40,1,0,0,0,2,46,1,0,0,0,4,49,1,0,0,0,6,
        54,1,0,0,0,8,63,1,0,0,0,10,73,1,0,0,0,12,87,1,0,0,0,14,89,1,0,0,
        0,16,92,1,0,0,0,18,98,1,0,0,0,20,100,1,0,0,0,22,102,1,0,0,0,24,106,
        1,0,0,0,26,110,1,0,0,0,28,114,1,0,0,0,30,118,1,0,0,0,32,128,1,0,
        0,0,34,130,1,0,0,0,36,134,1,0,0,0,38,174,1,0,0,0,40,41,3,2,1,0,41,
        42,5,0,0,1,42,1,1,0,0,0,43,45,3,4,2,0,44,43,1,0,0,0,45,48,1,0,0,
        0,46,44,1,0,0,0,46,47,1,0,0,0,47,3,1,0,0,0,48,46,1,0,0,0,49,50,3,
        20,10,0,50,51,5,7,0,0,51,52,3,6,3,0,52,53,5,6,0,0,53,5,1,0,0,0,54,
        59,3,8,4,0,55,56,5,8,0,0,56,58,3,8,4,0,57,55,1,0,0,0,58,61,1,0,0,
        0,59,57,1,0,0,0,59,60,1,0,0,0,60,7,1,0,0,0,61,59,1,0,0,0,62,64,3,
        26,13,0,63,62,1,0,0,0,63,64,1,0,0,0,64,66,1,0,0,0,65,67,3,28,14,
        0,66,65,1,0,0,0,66,67,1,0,0,0,67,68,1,0,0,0,68,69,3,10,5,0,69,9,
        1,0,0,0,70,72,3,22,11,0,71,70,1,0,0,0,72,75,1,0,0,0,73,71,1,0,0,
        0,73,74,1,0,0,0,74,76,1,0,0,0,75,73,1,0,0,0,76,81,3,12,6,0,77,80,
        3,12,6,0,78,80,3,22,11,0,79,77,1,0,0,0,79,78,1,0,0,0,80,83,1,0,0,
        0,81,79,1,0,0,0,81,82,1,0,0,0,82,11,1,0,0,0,83,81,1,0,0,0,84,88,
        3,14,7,0,85,88,3,16,8,0,86,88,3,24,12,0,87,84,1,0,0,0,87,85,1,0,
        0,0,87,86,1,0,0,0,88,13,1,0,0,0,89,90,5,11,0,0,90,15,1,0,0,0,91,
        93,3,18,9,0,92,91,1,0,0,0,92,93,1,0,0,0,93,94,1,0,0,0,94,95,5,3,
        0,0,95,96,3,38,19,0,96,97,5,23,0,0,97,17,1,0,0,0,98,99,5,9,0,0,99,
        19,1,0,0,0,100,101,5,9,0,0,101,21,1,0,0,0,102,103,5,2,0,0,103,104,
        3,30,15,0,104,105,5,22,0,0,105,23,1,0,0,0,106,108,3,20,10,0,107,
        109,3,26,13,0,108,107,1,0,0,0,108,109,1,0,0,0,109,25,1,0,0,0,110,
        111,5,1,0,0,111,112,3,38,19,0,112,113,5,21,0,0,113,27,1,0,0,0,114,
        115,5,4,0,0,115,116,5,10,0,0,116,117,5,5,0,0,117,29,1,0,0,0,118,
        123,3,32,16,0,119,120,5,20,0,0,120,122,3,32,16,0,121,119,1,0,0,0,
        122,125,1,0,0,0,123,121,1,0,0,0,123,124,1,0,0,0,124,31,1,0,0,0,125,
        123,1,0,0,0,126,129,3,34,17,0,127,129,3,36,18,0,128,126,1,0,0,0,
        128,127,1,0,0,0,129,33,1,0,0,0,130,132,5,24,0,0,131,133,3,38,19,
        0,132,131,1,0,0,0,132,133,1,0,0,0,133,35,1,0,0,0,134,135,3,38,19,
        0,135,37,1,0,0,0,136,138,5,15,0,0,137,139,3,38,19,0,138,137,1,0,
        0,0,138,139,1,0,0,0,139,140,1,0,0,0,140,142,5,21,0,0,141,143,3,38,
        19,0,142,141,1,0,0,0,142,143,1,0,0,0,143,175,1,0,0,0,144,146,5,16,
        0,0,145,147,3,38,19,0,146,145,1,0,0,0,146,147,1,0,0,0,147,148,1,
        0,0,0,148,150,5,22,0,0,149,151,3,38,19,0,150,149,1,0,0,0,150,151,
        1,0,0,0,151,175,1,0,0,0,152,154,5,17,0,0,153,155,3,38,19,0,154,153,
        1,0,0,0,154,155,1,0,0,0,155,156,1,0,0,0,156,158,5,23,0,0,157,159,
        3,38,19,0,158,157,1,0,0,0,158,159,1,0,0,0,159,175,1,0,0,0,160,161,
        5,18,0,0,161,163,5,26,0,0,162,164,3,38,19,0,163,162,1,0,0,0,163,
        164,1,0,0,0,164,175,1,0,0,0,165,166,5,19,0,0,166,168,5,27,0,0,167,
        169,3,38,19,0,168,167,1,0,0,0,168,169,1,0,0,0,169,175,1,0,0,0,170,
        172,5,25,0,0,171,173,3,38,19,0,172,171,1,0,0,0,172,173,1,0,0,0,173,
        175,1,0,0,0,174,136,1,0,0,0,174,144,1,0,0,0,174,152,1,0,0,0,174,
        160,1,0,0,0,174,165,1,0,0,0,174,170,1,0,0,0,175,39,1,0,0,0,23,46,
        59,63,66,73,79,81,87,92,108,123,128,132,138,142,146,150,154,158,
        163,168,172,174
    ]

class PgenParser ( Parser ):

    grammarFileName = "PgenParser.g4"

    atn = ATNDeserializer().deserialize(serializedATN())

    decisionsToDFA = [ DFA(ds, i) for i, ds in enumerate(atn.decisionToState) ]

    sharedContextCache = PredictionContextCache()

    literalNames = [ "<INVALID>", "<INVALID>", "<INVALID>", "<INVALID>", 
                     "'<'", "'>'", "<INVALID>", "':'", "'|'", "<INVALID>", 
                     "<INVALID>", "<INVALID>", "'?'", "<INVALID>", "<INVALID>", 
                     "<INVALID>", "<INVALID>", "<INVALID>", "'''", "'\"'", 
                     "<INVALID>", "')'", "'}'", "']'" ]

    symbolicNames = [ "<INVALID>", "LPAR", "LBRACE", "LBRACK", "LANGLEBRAC", 
                      "RANGLEBRAC", "SEMI", "COLON", "PIPE", "ID", "FLOAT", 
                      "STRING", "TODO", "WHITESPACE", "COMMENT", "CODE_LPAR", 
                      "CODE_LBRACE", "CODE_LBRACK", "CODE_SINGLE_QUOTE_OPEN", 
                      "CODE_DOUBLE_QUOTE_OPEN", "CODE_SEMI", "RPAR", "RBRACE", 
                      "RBRACK", "CODE_INIT_NO_PAIRS", "CODE_NO_PAIRS", "CODE_SINGLE_QUOTE_STRING", 
                      "CODE_DOUBLE_QUOTE_STRING" ]

    RULE_start = 0
    RULE_nt_defn_list = 1
    RULE_nt_defn = 2
    RULE_expansion_list = 3
    RULE_expansion = 4
    RULE_term_list = 5
    RULE_term = 6
    RULE_terminal = 7
    RULE_expression = 8
    RULE_variable = 9
    RULE_nonterminal_variable = 10
    RULE_stateful_block = 11
    RULE_nonterminal_term = 12
    RULE_constraints = 13
    RULE_weight = 14
    RULE_function_list = 15
    RULE_init_or_update = 16
    RULE_init = 17
    RULE_update = 18
    RULE_code = 19

    ruleNames =  [ "start", "nt_defn_list", "nt_defn", "expansion_list", 
                   "expansion", "term_list", "term", "terminal", "expression", 
                   "variable", "nonterminal_variable", "stateful_block", 
                   "nonterminal_term", "constraints", "weight", "function_list", 
                   "init_or_update", "init", "update", "code" ]

    EOF = Token.EOF
    LPAR=1
    LBRACE=2
    LBRACK=3
    LANGLEBRAC=4
    RANGLEBRAC=5
    SEMI=6
    COLON=7
    PIPE=8
    ID=9
    FLOAT=10
    STRING=11
    TODO=12
    WHITESPACE=13
    COMMENT=14
    CODE_LPAR=15
    CODE_LBRACE=16
    CODE_LBRACK=17
    CODE_SINGLE_QUOTE_OPEN=18
    CODE_DOUBLE_QUOTE_OPEN=19
    CODE_SEMI=20
    RPAR=21
    RBRACE=22
    RBRACK=23
    CODE_INIT_NO_PAIRS=24
    CODE_NO_PAIRS=25
    CODE_SINGLE_QUOTE_STRING=26
    CODE_DOUBLE_QUOTE_STRING=27

    def __init__(self, input:TokenStream, output:TextIO = sys.stdout):
        super().__init__(input, output)
        self.checkVersion("4.13.1")
        self._interp = ParserATNSimulator(self, self.atn, self.decisionsToDFA, self.sharedContextCache)
        self._predicates = None




    class StartContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def nt_defn_list(self):
            return self.getTypedRuleContext(PgenParser.Nt_defn_listContext,0)


        def EOF(self):
            return self.getToken(PgenParser.EOF, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_start

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterStart" ):
                listener.enterStart(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitStart" ):
                listener.exitStart(self)




    def start(self):

        localctx = PgenParser.StartContext(self, self._ctx, self.state)
        self.enterRule(localctx, 0, self.RULE_start)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 40
            self.nt_defn_list()
            self.state = 41
            self.match(PgenParser.EOF)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Nt_defn_listContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def nt_defn(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(PgenParser.Nt_defnContext)
            else:
                return self.getTypedRuleContext(PgenParser.Nt_defnContext,i)


        def getRuleIndex(self):
            return PgenParser.RULE_nt_defn_list

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterNt_defn_list" ):
                listener.enterNt_defn_list(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitNt_defn_list" ):
                listener.exitNt_defn_list(self)




    def nt_defn_list(self):

        localctx = PgenParser.Nt_defn_listContext(self, self._ctx, self.state)
        self.enterRule(localctx, 2, self.RULE_nt_defn_list)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 46
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==9:
                self.state = 43
                self.nt_defn()
                self.state = 48
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Nt_defnContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def nonterminal_variable(self):
            return self.getTypedRuleContext(PgenParser.Nonterminal_variableContext,0)


        def COLON(self):
            return self.getToken(PgenParser.COLON, 0)

        def expansion_list(self):
            return self.getTypedRuleContext(PgenParser.Expansion_listContext,0)


        def SEMI(self):
            return self.getToken(PgenParser.SEMI, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_nt_defn

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterNt_defn" ):
                listener.enterNt_defn(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitNt_defn" ):
                listener.exitNt_defn(self)




    def nt_defn(self):

        localctx = PgenParser.Nt_defnContext(self, self._ctx, self.state)
        self.enterRule(localctx, 4, self.RULE_nt_defn)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 49
            self.nonterminal_variable()
            self.state = 50
            self.match(PgenParser.COLON)
            self.state = 51
            self.expansion_list()
            self.state = 52
            self.match(PgenParser.SEMI)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Expansion_listContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def expansion(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(PgenParser.ExpansionContext)
            else:
                return self.getTypedRuleContext(PgenParser.ExpansionContext,i)


        def PIPE(self, i:int=None):
            if i is None:
                return self.getTokens(PgenParser.PIPE)
            else:
                return self.getToken(PgenParser.PIPE, i)

        def getRuleIndex(self):
            return PgenParser.RULE_expansion_list

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterExpansion_list" ):
                listener.enterExpansion_list(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitExpansion_list" ):
                listener.exitExpansion_list(self)




    def expansion_list(self):

        localctx = PgenParser.Expansion_listContext(self, self._ctx, self.state)
        self.enterRule(localctx, 6, self.RULE_expansion_list)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 54
            self.expansion()
            self.state = 59
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==8:
                self.state = 55
                self.match(PgenParser.PIPE)
                self.state = 56
                self.expansion()
                self.state = 61
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ExpansionContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def term_list(self):
            return self.getTypedRuleContext(PgenParser.Term_listContext,0)


        def constraints(self):
            return self.getTypedRuleContext(PgenParser.ConstraintsContext,0)


        def weight(self):
            return self.getTypedRuleContext(PgenParser.WeightContext,0)


        def getRuleIndex(self):
            return PgenParser.RULE_expansion

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterExpansion" ):
                listener.enterExpansion(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitExpansion" ):
                listener.exitExpansion(self)




    def expansion(self):

        localctx = PgenParser.ExpansionContext(self, self._ctx, self.state)
        self.enterRule(localctx, 8, self.RULE_expansion)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 63
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if _la==1:
                self.state = 62
                self.constraints()


            self.state = 66
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if _la==4:
                self.state = 65
                self.weight()


            self.state = 68
            self.term_list()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Term_listContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def term(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(PgenParser.TermContext)
            else:
                return self.getTypedRuleContext(PgenParser.TermContext,i)


        def stateful_block(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(PgenParser.Stateful_blockContext)
            else:
                return self.getTypedRuleContext(PgenParser.Stateful_blockContext,i)


        def getRuleIndex(self):
            return PgenParser.RULE_term_list

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTerm_list" ):
                listener.enterTerm_list(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTerm_list" ):
                listener.exitTerm_list(self)




    def term_list(self):

        localctx = PgenParser.Term_listContext(self, self._ctx, self.state)
        self.enterRule(localctx, 10, self.RULE_term_list)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 73
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==2:
                self.state = 70
                self.stateful_block()
                self.state = 75
                self._errHandler.sync(self)
                _la = self._input.LA(1)

            self.state = 76
            self.term()
            self.state = 81
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while (((_la) & ~0x3f) == 0 and ((1 << _la) & 2572) != 0):
                self.state = 79
                self._errHandler.sync(self)
                token = self._input.LA(1)
                if token in [3, 9, 11]:
                    self.state = 77
                    self.term()
                    pass
                elif token in [2]:
                    self.state = 78
                    self.stateful_block()
                    pass
                else:
                    raise NoViableAltException(self)

                self.state = 83
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class TermContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def terminal(self):
            return self.getTypedRuleContext(PgenParser.TerminalContext,0)


        def expression(self):
            return self.getTypedRuleContext(PgenParser.ExpressionContext,0)


        def nonterminal_term(self):
            return self.getTypedRuleContext(PgenParser.Nonterminal_termContext,0)


        def getRuleIndex(self):
            return PgenParser.RULE_term

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTerm" ):
                listener.enterTerm(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTerm" ):
                listener.exitTerm(self)




    def term(self):

        localctx = PgenParser.TermContext(self, self._ctx, self.state)
        self.enterRule(localctx, 12, self.RULE_term)
        try:
            self.state = 87
            self._errHandler.sync(self)
            la_ = self._interp.adaptivePredict(self._input,7,self._ctx)
            if la_ == 1:
                self.enterOuterAlt(localctx, 1)
                self.state = 84
                self.terminal()
                pass

            elif la_ == 2:
                self.enterOuterAlt(localctx, 2)
                self.state = 85
                self.expression()
                pass

            elif la_ == 3:
                self.enterOuterAlt(localctx, 3)
                self.state = 86
                self.nonterminal_term()
                pass


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class TerminalContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def STRING(self):
            return self.getToken(PgenParser.STRING, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_terminal

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTerminal" ):
                listener.enterTerminal(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTerminal" ):
                listener.exitTerminal(self)




    def terminal(self):

        localctx = PgenParser.TerminalContext(self, self._ctx, self.state)
        self.enterRule(localctx, 14, self.RULE_terminal)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 89
            self.match(PgenParser.STRING)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ExpressionContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def LBRACK(self):
            return self.getToken(PgenParser.LBRACK, 0)

        def code(self):
            return self.getTypedRuleContext(PgenParser.CodeContext,0)


        def RBRACK(self):
            return self.getToken(PgenParser.RBRACK, 0)

        def variable(self):
            return self.getTypedRuleContext(PgenParser.VariableContext,0)


        def getRuleIndex(self):
            return PgenParser.RULE_expression

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterExpression" ):
                listener.enterExpression(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitExpression" ):
                listener.exitExpression(self)




    def expression(self):

        localctx = PgenParser.ExpressionContext(self, self._ctx, self.state)
        self.enterRule(localctx, 16, self.RULE_expression)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 92
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if _la==9:
                self.state = 91
                self.variable()


            self.state = 94
            self.match(PgenParser.LBRACK)
            self.state = 95
            self.code()
            self.state = 96
            self.match(PgenParser.RBRACK)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class VariableContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def ID(self):
            return self.getToken(PgenParser.ID, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_variable

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterVariable" ):
                listener.enterVariable(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitVariable" ):
                listener.exitVariable(self)




    def variable(self):

        localctx = PgenParser.VariableContext(self, self._ctx, self.state)
        self.enterRule(localctx, 18, self.RULE_variable)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 98
            self.match(PgenParser.ID)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Nonterminal_variableContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def ID(self):
            return self.getToken(PgenParser.ID, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_nonterminal_variable

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterNonterminal_variable" ):
                listener.enterNonterminal_variable(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitNonterminal_variable" ):
                listener.exitNonterminal_variable(self)




    def nonterminal_variable(self):

        localctx = PgenParser.Nonterminal_variableContext(self, self._ctx, self.state)
        self.enterRule(localctx, 20, self.RULE_nonterminal_variable)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 100
            self.match(PgenParser.ID)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Stateful_blockContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def LBRACE(self):
            return self.getToken(PgenParser.LBRACE, 0)

        def function_list(self):
            return self.getTypedRuleContext(PgenParser.Function_listContext,0)


        def RBRACE(self):
            return self.getToken(PgenParser.RBRACE, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_stateful_block

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterStateful_block" ):
                listener.enterStateful_block(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitStateful_block" ):
                listener.exitStateful_block(self)




    def stateful_block(self):

        localctx = PgenParser.Stateful_blockContext(self, self._ctx, self.state)
        self.enterRule(localctx, 22, self.RULE_stateful_block)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 102
            self.match(PgenParser.LBRACE)
            self.state = 103
            self.function_list()
            self.state = 104
            self.match(PgenParser.RBRACE)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Nonterminal_termContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def nonterminal_variable(self):
            return self.getTypedRuleContext(PgenParser.Nonterminal_variableContext,0)


        def constraints(self):
            return self.getTypedRuleContext(PgenParser.ConstraintsContext,0)


        def getRuleIndex(self):
            return PgenParser.RULE_nonterminal_term

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterNonterminal_term" ):
                listener.enterNonterminal_term(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitNonterminal_term" ):
                listener.exitNonterminal_term(self)




    def nonterminal_term(self):

        localctx = PgenParser.Nonterminal_termContext(self, self._ctx, self.state)
        self.enterRule(localctx, 24, self.RULE_nonterminal_term)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 106
            self.nonterminal_variable()
            self.state = 108
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if _la==1:
                self.state = 107
                self.constraints()


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ConstraintsContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def LPAR(self):
            return self.getToken(PgenParser.LPAR, 0)

        def code(self):
            return self.getTypedRuleContext(PgenParser.CodeContext,0)


        def RPAR(self):
            return self.getToken(PgenParser.RPAR, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_constraints

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterConstraints" ):
                listener.enterConstraints(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitConstraints" ):
                listener.exitConstraints(self)




    def constraints(self):

        localctx = PgenParser.ConstraintsContext(self, self._ctx, self.state)
        self.enterRule(localctx, 26, self.RULE_constraints)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 110
            self.match(PgenParser.LPAR)
            self.state = 111
            self.code()
            self.state = 112
            self.match(PgenParser.RPAR)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class WeightContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def LANGLEBRAC(self):
            return self.getToken(PgenParser.LANGLEBRAC, 0)

        def FLOAT(self):
            return self.getToken(PgenParser.FLOAT, 0)

        def RANGLEBRAC(self):
            return self.getToken(PgenParser.RANGLEBRAC, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_weight

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterWeight" ):
                listener.enterWeight(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitWeight" ):
                listener.exitWeight(self)




    def weight(self):

        localctx = PgenParser.WeightContext(self, self._ctx, self.state)
        self.enterRule(localctx, 28, self.RULE_weight)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 114
            self.match(PgenParser.LANGLEBRAC)
            self.state = 115
            self.match(PgenParser.FLOAT)
            self.state = 116
            self.match(PgenParser.RANGLEBRAC)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Function_listContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def init_or_update(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(PgenParser.Init_or_updateContext)
            else:
                return self.getTypedRuleContext(PgenParser.Init_or_updateContext,i)


        def CODE_SEMI(self, i:int=None):
            if i is None:
                return self.getTokens(PgenParser.CODE_SEMI)
            else:
                return self.getToken(PgenParser.CODE_SEMI, i)

        def getRuleIndex(self):
            return PgenParser.RULE_function_list

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterFunction_list" ):
                listener.enterFunction_list(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitFunction_list" ):
                listener.exitFunction_list(self)




    def function_list(self):

        localctx = PgenParser.Function_listContext(self, self._ctx, self.state)
        self.enterRule(localctx, 30, self.RULE_function_list)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 118
            self.init_or_update()
            self.state = 123
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==20:
                self.state = 119
                self.match(PgenParser.CODE_SEMI)
                self.state = 120
                self.init_or_update()
                self.state = 125
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class Init_or_updateContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def init(self):
            return self.getTypedRuleContext(PgenParser.InitContext,0)


        def update(self):
            return self.getTypedRuleContext(PgenParser.UpdateContext,0)


        def getRuleIndex(self):
            return PgenParser.RULE_init_or_update

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterInit_or_update" ):
                listener.enterInit_or_update(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitInit_or_update" ):
                listener.exitInit_or_update(self)




    def init_or_update(self):

        localctx = PgenParser.Init_or_updateContext(self, self._ctx, self.state)
        self.enterRule(localctx, 32, self.RULE_init_or_update)
        try:
            self.state = 128
            self._errHandler.sync(self)
            token = self._input.LA(1)
            if token in [24]:
                self.enterOuterAlt(localctx, 1)
                self.state = 126
                self.init()
                pass
            elif token in [15, 16, 17, 18, 19, 25]:
                self.enterOuterAlt(localctx, 2)
                self.state = 127
                self.update()
                pass
            else:
                raise NoViableAltException(self)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class InitContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def CODE_INIT_NO_PAIRS(self):
            return self.getToken(PgenParser.CODE_INIT_NO_PAIRS, 0)

        def code(self):
            return self.getTypedRuleContext(PgenParser.CodeContext,0)


        def getRuleIndex(self):
            return PgenParser.RULE_init

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterInit" ):
                listener.enterInit(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitInit" ):
                listener.exitInit(self)




    def init(self):

        localctx = PgenParser.InitContext(self, self._ctx, self.state)
        self.enterRule(localctx, 34, self.RULE_init)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 130
            self.match(PgenParser.CODE_INIT_NO_PAIRS)
            self.state = 132
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                self.state = 131
                self.code()


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class UpdateContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def code(self):
            return self.getTypedRuleContext(PgenParser.CodeContext,0)


        def getRuleIndex(self):
            return PgenParser.RULE_update

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterUpdate" ):
                listener.enterUpdate(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitUpdate" ):
                listener.exitUpdate(self)




    def update(self):

        localctx = PgenParser.UpdateContext(self, self._ctx, self.state)
        self.enterRule(localctx, 36, self.RULE_update)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 134
            self.code()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class CodeContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def CODE_LPAR(self):
            return self.getToken(PgenParser.CODE_LPAR, 0)

        def RPAR(self):
            return self.getToken(PgenParser.RPAR, 0)

        def code(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(PgenParser.CodeContext)
            else:
                return self.getTypedRuleContext(PgenParser.CodeContext,i)


        def CODE_LBRACE(self):
            return self.getToken(PgenParser.CODE_LBRACE, 0)

        def RBRACE(self):
            return self.getToken(PgenParser.RBRACE, 0)

        def CODE_LBRACK(self):
            return self.getToken(PgenParser.CODE_LBRACK, 0)

        def RBRACK(self):
            return self.getToken(PgenParser.RBRACK, 0)

        def CODE_SINGLE_QUOTE_OPEN(self):
            return self.getToken(PgenParser.CODE_SINGLE_QUOTE_OPEN, 0)

        def CODE_SINGLE_QUOTE_STRING(self):
            return self.getToken(PgenParser.CODE_SINGLE_QUOTE_STRING, 0)

        def CODE_DOUBLE_QUOTE_OPEN(self):
            return self.getToken(PgenParser.CODE_DOUBLE_QUOTE_OPEN, 0)

        def CODE_DOUBLE_QUOTE_STRING(self):
            return self.getToken(PgenParser.CODE_DOUBLE_QUOTE_STRING, 0)

        def CODE_NO_PAIRS(self):
            return self.getToken(PgenParser.CODE_NO_PAIRS, 0)

        def getRuleIndex(self):
            return PgenParser.RULE_code

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterCode" ):
                listener.enterCode(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitCode" ):
                listener.exitCode(self)




    def code(self):

        localctx = PgenParser.CodeContext(self, self._ctx, self.state)
        self.enterRule(localctx, 38, self.RULE_code)
        self._la = 0 # Token type
        try:
            self.state = 174
            self._errHandler.sync(self)
            token = self._input.LA(1)
            if token in [15]:
                self.enterOuterAlt(localctx, 1)
                self.state = 136
                self.match(PgenParser.CODE_LPAR)
                self.state = 138
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 137
                    self.code()


                self.state = 140
                self.match(PgenParser.RPAR)
                self.state = 142
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 141
                    self.code()


                pass
            elif token in [16]:
                self.enterOuterAlt(localctx, 2)
                self.state = 144
                self.match(PgenParser.CODE_LBRACE)
                self.state = 146
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 145
                    self.code()


                self.state = 148
                self.match(PgenParser.RBRACE)
                self.state = 150
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 149
                    self.code()


                pass
            elif token in [17]:
                self.enterOuterAlt(localctx, 3)
                self.state = 152
                self.match(PgenParser.CODE_LBRACK)
                self.state = 154
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 153
                    self.code()


                self.state = 156
                self.match(PgenParser.RBRACK)
                self.state = 158
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 157
                    self.code()


                pass
            elif token in [18]:
                self.enterOuterAlt(localctx, 4)
                self.state = 160
                self.match(PgenParser.CODE_SINGLE_QUOTE_OPEN)
                self.state = 161
                self.match(PgenParser.CODE_SINGLE_QUOTE_STRING)
                self.state = 163
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 162
                    self.code()


                pass
            elif token in [19]:
                self.enterOuterAlt(localctx, 5)
                self.state = 165
                self.match(PgenParser.CODE_DOUBLE_QUOTE_OPEN)
                self.state = 166
                self.match(PgenParser.CODE_DOUBLE_QUOTE_STRING)
                self.state = 168
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 167
                    self.code()


                pass
            elif token in [25]:
                self.enterOuterAlt(localctx, 6)
                self.state = 170
                self.match(PgenParser.CODE_NO_PAIRS)
                self.state = 172
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if (((_la) & ~0x3f) == 0 and ((1 << _la) & 34570240) != 0):
                    self.state = 171
                    self.code()


                pass
            else:
                raise NoViableAltException(self)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx





