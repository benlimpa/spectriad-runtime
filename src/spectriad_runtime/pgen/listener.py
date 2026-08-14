from antlr4 import CommonTokenStream
from .PgenParser import PgenParser
from .PgenParserListener import PgenParserListener
from .node_manager import *
import re


class CustomListener(PgenParserListener):
    def __init__(self, token_stream: CommonTokenStream, output_file: str):
        self.node_manager = NodeManager(output_file)
        self.token_stream = token_stream

    def exitStart(self, ctx: PgenParser.StartContext):
        self.node_manager.write_to_file()

    def enterNt_defn(self, ctx: PgenParser.Nt_defnContext):
        nonterminal = ctx.nonterminal_variable().getText()
        self.node_manager.add_nonterminal(nonterminal)

    def enterExpansion(self, ctx: PgenParser.ExpansionContext):
        self.node_manager.add_expansion()

    def enterTerminal(self, ctx: PgenParser.TerminalContext):
        terminal_string = ctx.getText()
        self.node_manager.add_terminal(terminal_string)

    # I'm doing this terrible thing to tokenize 'new ID = ...' all as one token
    # Unfortunately otherwise the token for arbitrary code would be longer than the tokens 'new' 'ID' '=' '...'
    # So now I have to parse the token to extract ID and if its initialized to anything
    # And handle the case where the arbitrary code is split between the initialization token and code token
    # 😭
    def enterInit(self, ctx: PgenParser.InitContext):
        code = ctx.CODE_INIT_NO_PAIRS().getText()
        pattern = r"^\s*new\s+([A-Z][A-Z_]*)\s*(?:=\s*(.+))?"
        match = re.search(pattern, code)
        assert match
        state_variable = match.group(1)
        initialize_start = match.group(2).strip() if match.group(2) else ""
        initialize_remaining = ctx.code().getText() if ctx.code() else ""
        init_code = initialize_start + initialize_remaining
        self.node_manager.add_initialize(state_variable, init_code)

    def enterUpdate(self, ctx: PgenParser.UpdateContext):
        code = ctx.getText().strip()
        self.node_manager.add_update_state(code)

    def enterExpression(self, ctx: PgenParser.ExpressionContext):
        variable = ctx.variable().getText() if ctx.variable() else None
        expression = ctx.code().getText().strip()
        self.node_manager.add_expression(variable, expression)

    # If it's a nonterminal outside a code block without args, assume no args
    def enterNonterminal_term(self, ctx: PgenParser.Nonterminal_termContext):
        nonterminal_variable = ctx.nonterminal_variable().getText()
        self.node_manager.add_nonterminal_term(nonterminal_variable)

    def enterConstraints(self, ctx: PgenParser.ConstraintsContext):
        constraints = ctx.code().getText()
        self.node_manager.add_constraints(constraints)

    def enterWeight(self, ctx: PgenParser.WeightContext):
        weight = ctx.FLOAT().getText()
        self.node_manager.add_weight(weight)
