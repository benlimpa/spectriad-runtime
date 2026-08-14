from .constant_strings import *
from inspect import getsource


def HEADER_STRING(all_state_vars_list):
    return f"""
import random
import sys
import argparse
import warnings
import time
import typing
import string
import sre_parse
from re import Pattern
from rstr.xeger import Xeger
from rstr import rstr # Can do Regex() trick again to cache for performance

DEBUG = {DEBUG_OUTPUT}
# debug_print = print if DEBUG else lambda *args, **kwargs: None

{getsource(GlobalState)}

{getsource(Regex)}

{getsource(IterationException)}

{getsource(StateException)}

{getsource(ConditionException)}

{REGEX_VARIABLE} = Regex()

__global_state = GlobalState({all_state_vars_list})

{DEPTH_VARIABLE} = 0

"""


def main_function_string(starting_nonterminal):
    min_depth_var_in_brackets = "{" + MAX_DEPTH_VARIABLE + "}"
    return f"""
def generate_root():
	# {GS_CHECK_EMPTY}() # For development only to verify correctness.
	# {GS_RESET}() # Shouldn't need it, state should undo itself when exiting it's scope
	while True:
		try:
			result = {starting_nonterminal}()
			return result
		except IterationException as e:
			pass
	
if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Process some parameters.")
	parser.add_argument("--debug", type=int, default=0, help="Enable debug output (0 or 1)")
	parser.add_argument("--retry_attempts", type=int, default={RETRY_ATTEMPTS_VARIABLE}, help="Number of retry attempts")
	parser.add_argument("--max_depth", type=int, default={MAX_DEPTH_VARIABLE}, help="Maximum depth for recursion")
	parser.add_argument("-n", "--num_iters", type=int, default=1, help="Number of iterations to run (0 for infinite)")
	parser.add_argument("-t", "--timeout", type=float, default=0, help="Timeout in seconds for each iteration (0 for no timeout)")
	parser.add_argument("-d", "--output_dir", type=str, default=None, help="Directory to save output files")
	
	args = parser.parse_args()

	if args.retry_attempts < 1:
		print("Retry attempts must be at least 1")
		sys.exit(1)

	if args.max_depth < {MAX_DEPTH_VARIABLE}:
		warnings.warn(f"Warning: Max depth must be at least {min_depth_var_in_brackets} for this grammar", RuntimeWarning)
		args.max_depth = {MAX_DEPTH_VARIABLE}

	if args.num_iters < 0:
		warnings.warn("Warning: Number of iterations must be at least 0", RuntimeWarning)
		args.num_iters = 1
	elif args.num_iters == 0:
		args.num_iters = sys.maxsize

	if args.timeout < 0:
		warnings.warn("Warning: Timeout must be at least 0", RuntimeWarning)
		args.timeout = 0
		
	if args.output_dir is None:
		warnings.warn("Warning: Output directory not specified, printing to stdout", RuntimeWarning)

	DEBUG = args.debug
	output_dir = args.output_dir

	{RETRY_ATTEMPTS_VARIABLE} = args.retry_attempts
	{MAX_DEPTH_VARIABLE} = args.max_depth

	generated_strings = set()
	end_time = time.time() + args.timeout
	for _ in range(args.num_iters):
		generated_strings.add(generate_root())
		if args.timeout > 0 and time.time() > end_time:
			break
	
	if output_dir:
		for i, string in enumerate(generated_strings):
			output_file = output_dir + "/" + str(i) + ".txt"
			with open(output_file, "w") as f:
				f.write(string)
	else:
		for string in generated_strings:
			print(string)
"""


def getInitCodeBlock(depth, rest_of_code, main_function, all_state_vars_list):
    return f"""
{HEADER_STRING(all_state_vars_list)}
{MAX_DEPTH_VARIABLE} = {depth}
{RETRY_ATTEMPTS_VARIABLE} = {RETRY_ATTEMPTS}

{rest_of_code}
{main_function}
"""


def getNonterminalCodeBlock(
    nonterminal_name,
    expansions_code_blocks,
    expansion_calls,
    expansion_depths,
    expansion_constraints,
    expansion_weights,
):
    get_expansion_result = "{__temp}"
    return f"""
def {nonterminal_name}():
	global {DEPTH_VARIABLE}
	{expansions_code_blocks}
	# debug_print({nonterminal_name}.__name__, {DEPTH_VARIABLE})
	{ALL_EXPANSIONS_VARIABLE} = [{", ".join(expansion_calls)}]
	{ALL_EXPANSION_DEPTHS_VARIABLE} = [{", ".join(expansion_depths)}]
	{ALL_EXPANSION_CONSTRAINTS} = [{", ".join(expansion_constraints)}]
	{ALL_EXPANSION_WEIGHTS} = [{", ".join(expansion_weights)}]
	{CANDIDATE_EXPANSIONS} = []
	{CANDIDATE_WEIGHTS} = []
	{CANDIDATE_INDEXES} = []
	candidates = 0
	for i, expansion in enumerate({ALL_EXPANSIONS_VARIABLE}):
		if {ALL_EXPANSION_DEPTHS_VARIABLE}[i]+{DEPTH_VARIABLE} <= {MAX_DEPTH_VARIABLE} and {ALL_EXPANSION_CONSTRAINTS}[i]:
			{CANDIDATE_EXPANSIONS}.append(expansion)
			{CANDIDATE_WEIGHTS}.append({ALL_EXPANSION_WEIGHTS}[i])
			{CANDIDATE_INDEXES}.append(candidates)
			candidates += 1
	{GS_SAVE}()
	while {CANDIDATE_INDEXES}:
		[__index] = random.choices({CANDIDATE_INDEXES}, weights={CANDIDATE_WEIGHTS})
		try:
			{DEPTH_VARIABLE} += 1
			__temp = {CANDIDATE_EXPANSIONS}[__index]()
			# debug_print(f"Expansion succeeded for {nonterminal_name}: {get_expansion_result}")
			{GS_DELETE_SAVED}()
			{DEPTH_VARIABLE} -= 1
			return __temp
		except IterationException as e:
			__index_index = {CANDIDATE_INDEXES}.index(__index)
			{CANDIDATE_INDEXES}.pop(__index_index)
			{CANDIDATE_WEIGHTS}.pop(__index_index)
			{DEPTH_VARIABLE} -= 1
			{GS_RESTORE}()
	{GS_DELETE_SAVED}()
	raise IterationException('All expansions failed for:', {nonterminal_name}.__name__, {CANDIDATE_EXPANSIONS})
"""


def getExpansionCodeBlock(
    expansion_num,
    isStateVars,
    state_variables,
    nonterminal_lists,
    term_code_blocks,
    delete_vars_code,
    term_variables,
):
    useGlobal = "global" if isStateVars else ""
    # need \n to start them on a new line with no tabs
    # Should refactor so the params are just data, and we compute the strings here
    # Maybe use a method to add indentations to it or something to avoid using \n
    return f"""
	def {EXPANSION_VARIABLE}_{expansion_num}():
		{useGlobal} {state_variables}
		\n{nonterminal_lists}
		\n{term_code_blocks}
		\n{delete_vars_code}
		return {'+'.join(term_variables)}
"""


def getTerminalCodeBlock(expansion_num, terminal_string):
    return f"""
		{TERM_VARIABLE}{expansion_num} = {terminal_string}
"""


def getInitializeStateCodeBlock(variable, initialized_value):
    # return f"\t\t{GS_DECLATE}('{self.value}')\n\t\tglobal {self.value}"
    return f"""
		{GS_DECLATE}('{variable}', {initialized_value})
		{variable} = {variable if initialized_value else None} # for IDE variable binding
"""


def getInitializeStateDeleteCodeBlock(variable):
    return f"""
		{GS_DELETE}('{variable}')
"""


def getUpdateStateCodeBlock(update_code):
    return f"""
		{update_code}
"""


def getExpressionCodeBlock(expansion_num, variable, expression):
    return f"""
		{TERM_VARIABLE}{expansion_num} = str({expression})
		{f"{variable}.append({TERM_VARIABLE}{expansion_num})" if variable else ""}
"""


def getNonterminalTermCodeBlock(
    expansion_num,
    nonterminal_call,
    nonterminal_name,
    constraint,
    previously_declared_vars,
):
    term_var = f"{TERM_VARIABLE}{expansion_num}"
    generate_nt = f"{term_var} = {nonterminal_call}()"

    if not constraint:
        loop_constraint = "True"  # invalidate the loop condition
    else:
        loop_constraint = constraint

    return f"""
		{f"{GS_SAVE}()" if constraint else ""}
		try:
			{generate_nt}
			{nonterminal_name}.append({term_var})
			{COUNTER_VARIABLE} = 0
			while not ({loop_constraint}):
				{GS_RESTORE}()
				if {COUNTER_VARIABLE} >= {RETRY_ATTEMPTS_VARIABLE}:
					raise IterationException('Too many attempts')
				{generate_nt}
				{nonterminal_name}[-1] = {term_var}
				{COUNTER_VARIABLE} += 1
			{f"{GS_DELETE_SAVED}()" if constraint else ""}
		except IterationException as e:
			{previously_declared_vars}
			{f"{GS_DELETE_SAVED}()" if constraint else ""}
			raise IterationException('Failed to get expansion for ', {nonterminal_name})
"""
