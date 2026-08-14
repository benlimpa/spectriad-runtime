from .constant_strings import *
from .code_blocks import *

DEBUG = False
debug_print = print if DEBUG else lambda *args, **kwargs: None


state_variables = []
nonterminals = {}  # map nonterminal name to NonterminalNode

# TODO: add another layer after nodes to gather information in case switch languages
# - put all the information from the tree into a single data structure
# - use a language-specific information extractor for each part of the code
# - pass that new data structure to the code generator functions


class ListenerNode:
    def __init__(self, value=None, parent=None):
        self.parent = parent
        self.children = []
        self.value = self.sanitize_value(value)
        self.original_value = value

    def set_parent(self, parent):
        self.parent = parent

    def add_child(self, child: "ListenerNode"):
        self.children.append(child)

    def get_last_child(self):
        return self.children[-1]

    def sanitize_value(self, value):
        return value

    def get_code(self):
        raise NotImplementedError


class InitNode(ListenerNode):
    def add_state_variable(self, state_variable):
        state_variables.append(state_variable)

    def add_child(self, child: "NonterminalNode"):
        super().add_child(child)
        nonterminals[child.original_value] = child

    def compute_depth(self):
        for _ in range(len(self.children) + 1):
            for child in self.children:
                child.update_depth()
        if DEBUG:
            for child in self.children:
                debug_print(child.original_value, child.min_depth)
        self.min_max_depth = max([child.min_depth for child in self.children])

    def get_code(self):
        default_max_depth = MAX_DEPTH_COEFFICIENT * self.min_max_depth
        rest_of_code = "\n".join([child.get_code() for child in self.children])
        main_function = main_function_string(self.children[0].value)
        return getInitCodeBlock(
            default_max_depth, rest_of_code, main_function, state_variables
        )


class NonterminalNode(ListenerNode):
    def __init__(self, value=None, parent=None):
        super().__init__(value, parent)
        self.min_depth = float("inf")

    def update_depth(self):
        self.min_depth = (
            min([expansion.compute_depth() for expansion in self.children]) + 1
        )

    def get_code(self):
        expansions_code_blocks = "".join(
            [child.get_code(i) for i, child in enumerate(self.children)]
        )
        expansion_calls = [
            f"{EXPANSION_VARIABLE}_{i}" for i in range(len(self.children))
        ]
        expansion_depths = [str(expansion.depth) for expansion in self.children]
        expansion_constraints = [
            expansion.children[0].get_code() for expansion in self.children
        ]
        expansion_weights = [expansion.weight for expansion in self.children]
        return getNonterminalCodeBlock(
            self.value,
            expansions_code_blocks,
            expansion_calls,
            expansion_depths,
            expansion_constraints,
            expansion_weights,
        )


class ExpansionNode(ListenerNode):
    def __init__(self, value=None, parent=None):
        super().__init__(value, parent)
        self.depth = float("inf")
        self.weight = "1"
        self.children = [ConstraintNode("(True)", self)]

    def add_child(self, child):
        if type(child) == ConstraintNode:
            self.children[0] = child
        elif type(child) == WeightNode:
            self.weight = child.value
        else:
            self.children.append(child)  # type: ignore

    def is_empty_expansion(self):
        return len(self.children) == 1 and type(self.children[0]) == ConstraintNode

    def get_expansion_terms(self):
        return self.children[1:]

    def compute_depth(self):
        nonterminal_depths = [
            child.get_nonterminal_node().min_depth
            for child in self.children
            if type(child) == NonterminalTermNode
        ]
        self.depth = max(nonterminal_depths + [0])
        return self.depth

    def get_code(self, expansion_num):
        variables_list = set()
        term_variables = []
        term_code_lines_list = []
        del_state_vars = []

        for i, child in enumerate(self.get_expansion_terms()):
            if type(child) == NonterminalTermNode:
                child.set_backtrack_deletions(del_state_vars[::-1])

            term_code_lines_list.append(child.get_code(i))

            # Collect nonterminals' and expansions' vars for a list
            if type(child) == NonterminalTermNode or type(child) == ExpressionNode:
                if child.variable:
                    variables_list.add(child.variable)

            # Collect terms to concat
            if type(child) in {
                TerminalNode,
                NonterminalTermNode,
                ExpressionNode,
            }:
                term_variables.append(TERM_VARIABLE + str(i))

            # Collect state variables to delete
            if type(child) == InitializeStateNode:
                del_state_vars.append(child.get_delete_code())

        isStateVars = state_variables != []
        state_var_joined = ", ".join(state_variables)
        variables_lists_string = "\n".join([f"\t\t{nt}=[]" for nt in variables_list])
        term_code_blocks = "\n".join(term_code_lines_list)  # code for terms
        delete_vars_code = "\n".join(del_state_vars[::-1])
        return getExpansionCodeBlock(
            expansion_num,
            isStateVars,
            state_var_joined,
            variables_lists_string,
            term_code_blocks,
            delete_vars_code,
            term_variables,
        )


class TerminalNode(ListenerNode):
    def get_code(self, expansion_num):
        return getTerminalCodeBlock(
            expansion_num,
            self.value,
        )


class StateNode(ListenerNode):
    def sanitize_value(self, value):
        # Assumes there is a nonterminal before "this" in any expansion
        referenced = None
        for child in reversed(self.parent.children):  # type: ignore
            if isinstance(child, NonterminalTermNode):
                return replace_this_keyword(value, child.original_value)
            if isinstance(child, ExpressionNode) and child.variable:
                return replace_this_keyword(value, child.variable)
        return value


class InitializeStateNode(StateNode):
    def __init__(self, var_value_tuple: tuple[str, str], parent=None):
        variable, initialized_value = var_value_tuple
        super().__init__(variable, parent)
        self.variable = variable
        self.initialized_value = (
            self.sanitize_value(initialized_value) if initialized_value else None
        )

    def get_code(self, _):
        return getInitializeStateCodeBlock(self.variable, self.initialized_value)

    def get_delete_code(self):
        return getInitializeStateDeleteCodeBlock(self.variable)


class UpdateStateNode(StateNode):
    def get_code(self, _):
        return getUpdateStateCodeBlock(self.value)


class ExpressionNode(ListenerNode):
    def __init__(self, var_value_tuple: tuple[str, str], parent=None):
        variable, expression = var_value_tuple
        super().__init__(expression, parent)
        self.variable = variable
        self.expression = expression

    def get_code(self, expansion_num):
        return getExpressionCodeBlock(expansion_num, self.variable, self.expression)


class NonterminalTermNode(ListenerNode):
    def __init__(self, value=None, parent=None):
        super().__init__(value, parent)
        self.variable = value
        self.backtrack_deletions = []

    def get_nonterminal_node(self):
        return nonterminals[self.original_value]

    def set_backtrack_deletions(self, deletions: list[str]):
        self.backtrack_deletions = deletions

    def get_code(self, expansion_num):
        constraint_code = self.children[0].get_code() if self.children else None
        # Have to add an extra tab of indentation. Sorry for the mess
        deletion_code = "\n".join(
            [line.replace("\n\t", "\n\t\t") for line in self.backtrack_deletions]
        )
        return getNonterminalTermCodeBlock(
            expansion_num,
            self.value,
            self.original_value,
            constraint_code,
            deletion_code,
        )


class ConstraintNode(ListenerNode):
    def sanitize_value(self, value):
        if type(self.parent) != NonterminalTermNode:
            return value

        # If nonterminal, allow "this" keyword
        return replace_this_keyword(
            value,
            self.parent.original_value,
        )

    def get_code(self, *_):
        assert type(self.parent) in {
            NonterminalTermNode,  # used as loop condition
            ExpansionNode,  # used in expansion condition check
        }, "Parent of constraint node must be a NonterminalTermNode or ExpansionNode"
        return f"{self.value}"


class WeightNode(ListenerNode):
    pass


# Just manually replace "this" when its not part of a bigger word
def replace_this_keyword(constraint_str, last_nonterminal):
    invalidating_chars = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    replacement = f"{last_nonterminal}[-1]"

    start_index = 0

    while "this" in constraint_str[start_index:]:
        this_index = constraint_str.index("this", start_index)

        previous_index = this_index - 1
        next_index = this_index + 4

        previous_valid = (
            previous_index < 0
            or constraint_str[previous_index] not in invalidating_chars
        )
        next_valid = (
            next_index >= len(constraint_str)
            or constraint_str[next_index] not in invalidating_chars
        )

        if previous_valid and next_valid:
            constraint_str = (
                constraint_str[:this_index]
                + replacement
                + constraint_str[this_index + 4 :]
            )

        start_index = this_index + 1

    return constraint_str


sanitizations = {
    NonterminalNode: lambda _, x: f"_{x}",
    NonterminalTermNode: lambda _, x: f"_{x}",
}

for node_type, sanitize in sanitizations.items():
    node_type.sanitize_value = sanitize
