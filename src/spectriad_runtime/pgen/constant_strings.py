from rstr.xeger import Xeger
import typing
from re import Pattern
import sre_parse

DEBUG_OUTPUT = 0

RETRY_ATTEMPTS = 20
RETRY_ATTEMPTS_VARIABLE = "__retry_attempts"

EXPANSION_VARIABLE = "__expansion"
TERM_VARIABLE = "__term_"
COUNTER_VARIABLE = "__counter"

ALL_EXPANSIONS_VARIABLE = "__all_expansions"
ALL_EXPANSION_DEPTHS_VARIABLE = "__all_expansion_depths"
ALL_EXPANSION_CONSTRAINTS = "__all_expansion_constraints"
ALL_EXPANSION_WEIGHTS = "__all_expansion_weights"
ALL_EXPANSION_ENUM = "__all_expansion_enum"
CANDIDATE_EXPANSIONS = "__candidate_expansions"
CANDIDATE_WEIGHTS = "__candidate_weights"
CANDIDATE_INDEXES = "__candidate_indexes"

MAX_DEPTH_COEFFICIENT = 5
DEPTH_VARIABLE = "__depth"
MAX_DEPTH_VARIABLE = "__max_depth"
# GET_DEPTH = f"len(traceback.extract_stack())//2"

GS_DECLATE = "__global_state.declare_and_initialize"
GS_DELETE = "__global_state.delete"
GS_SAVE = "__global_state.save_state"
GS_SAVE_VARIABLE = "__saved_state"
GS_RESTORE = "__global_state.restore_state"
GS_DELETE_SAVED = "__global_state.delete_saved_state"
GS_CHECK_EMPTY = "__global_state.check_empty"
GS_RESET = "__global_state.reset"
GS_ALL_STATE_VARIABLES = "__all_state_variables"

REGEX_VARIABLE = "regex"


# On declare, push old (variable, value) onto stack, put new one in global
# On update, update use whichever variables are in global, no need to change stack
# On delete, delete the global variable, replace with poppd older one from stack if can
#
# DO NOT ALLOW USERS TO DECLARE "term_i" or "global_state", compiler check keyword?
class GlobalState:

    def __init__(self, all_state_vars) -> None:
        from collections import defaultdict

        # list of all self.variable_stacks, includes variables declared but not overwritten yet
        self.all_state_variables = all_state_vars
        self.declared_variables = set()

        self.variable_stacks = defaultdict(list)
        self.saved_states = []

    def _push(self, variable_name):
        value = globals()[variable_name]
        self.variable_stacks[variable_name].append(value)

    def _pop(self, variable_name):
        return self.variable_stacks[variable_name].pop()

    def save_state(self):
        current_state = {}
        for variable_name in self.declared_variables:
            value = globals()[variable_name]
            current_state[variable_name] = (
                value.copy() if isinstance(value, (dict, list, set)) else value
            )
        self.saved_states.append(current_state)

    def restore_state(self):
        if not self.saved_states:
            raise StateException("No saved state to restore.")
        for variable_name, value in self.saved_states[-1].items():
            globals()[variable_name] = value
        for variable_name in self.declared_variables - self.saved_states[-1].keys():
            if variable_name in globals():
                del globals()[variable_name]
        self.declared_variables = set(self.saved_states[-1].keys())

    def delete_saved_state(self):
        if not self.saved_states:
            raise StateException("No saved state to delete.")
        self.saved_states.pop()

    def declare_and_initialize(self, variable_name, value=None):
        if variable_name in globals():
            self._push(variable_name)
        self.declared_variables.add(variable_name)
        globals()[variable_name] = value

    def delete(self, variable_name):
        del globals()[variable_name]
        if self.variable_stacks[variable_name]:
            globals()[variable_name] = self._pop(variable_name)
        else:
            self.declared_variables.remove(variable_name)

    def check_empty(self):
        for var in self.variable_stacks:
            if self.variable_stacks[var]:
                print(self.variable_stacks)
                raise StateException(
                    f"Global state variable stack for {var} is not empty: {self.variable_stacks[var]}"
                )
        assert len(self.saved_states) == 0, "Saved states are not empty."
        assert len(self.declared_variables) == 0, "Variable stacks are not empty."

    def reset(self):
        self.declared_variables = set()
        self.variable_stacks.clear()
        self.saved_states.clear()
        for var in self.all_state_variables:
            if var in globals():
                del globals()[var]


class Regex(Xeger):
    parsed = {}

    # override the Xeger.xeger() method to cache patterns
    def xeger(self, string_or_regex: str) -> str:
        try:
            pattern = typing.cast(Pattern[str], string_or_regex).pattern
        except AttributeError:
            pattern = typing.cast(str, string_or_regex)

        if pattern not in self.parsed:
            self.parsed[pattern] = sre_parse.parse(pattern)

        parsed = self.parsed[pattern]
        result = self._build_string(parsed)
        self._cache.clear()
        return result

    def __call__(self, string_or_regex: str) -> str:
        return self.xeger(string_or_regex)


class IterationException(Exception):
    pass


class StateException(Exception):
    pass


class ConditionException(Exception):
    pass
