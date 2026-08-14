from .nodes import *


class NodeManager:
    def __init__(self, output_file: str):
        self.root: InitNode = InitNode()
        self.output_file = output_file

    # Parent getters

    def get_root(self) -> InitNode:
        return self.root

    def get_last_nonterminal(self) -> NonterminalNode:
        return self.root.get_last_child()

    def get_last_expansion(self) -> ExpansionNode:
        return self.get_last_nonterminal().get_last_child()

    def get_last_term(self) -> TerminalNode | NonterminalTermNode:
        return self.get_last_expansion().get_last_child()

    def get_constraint_parent(self) -> NonterminalTermNode | ExpansionNode:
        last_expansion = self.get_last_expansion()
        if last_expansion.is_empty_expansion():
            return last_expansion
        else:  # is a constraint for the last Nonterminal term
            n = self.get_last_term()
            assert type(n) == NonterminalTermNode
            return n

    # Node adding methods

    def add_node(self, parent_getter, Constructor, child_value):
        parent = parent_getter()
        child_node = Constructor(child_value, parent)
        parent.add_child(child_node)

    # Node adding methods

    def add_nonterminal(self, nonterminal_name):
        self.add_node(self.get_root, NonterminalNode, nonterminal_name)

    def add_expansion(self):
        self.add_node(self.get_last_nonterminal, ExpansionNode, None)

    def add_terminal(self, terminal_string):
        self.add_node(self.get_last_expansion, TerminalNode, terminal_string)

    def add_initialize(self, state_variable, initialized_value):
        initial_node_value = (state_variable, initialized_value)
        self.add_node(self.get_last_expansion, InitializeStateNode, initial_node_value)
        self.root.add_state_variable(state_variable)

    def add_update_state(self, code):
        self.add_node(self.get_last_expansion, UpdateStateNode, code)

    def add_expression(self, variable, expression):
        self.add_node(self.get_last_expansion, ExpressionNode, (variable, expression))

    def add_nonterminal_term(self, nonterminal_name):
        self.add_node(self.get_last_expansion, NonterminalTermNode, nonterminal_name)

    def add_constraints(self, constraints):
        self.add_node(self.get_constraint_parent, ConstraintNode, constraints)

    def add_weight(self, weight):
        self.add_node(self.get_last_expansion, WeightNode, weight)

    # After completing parsing

    def compute_depth(self):
        return self.root.compute_depth()

    def write_to_file(self):
        if type(self.root) == InitNode:
            self.compute_depth()
            fuzzing_code = self.root.get_code()
            with open(self.output_file, "w") as file:
                file.write(fuzzing_code)
        else:
            raise ValueError("Root node must be an InitNode")
