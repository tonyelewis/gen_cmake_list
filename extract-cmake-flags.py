#!/usr/bin/env python3

import itertools
import logging
import shlex
import subprocess
import tempfile

from pathlib import Path
from typing import Dict, List, Optional, Set

import argparse
import json
import sys

# Example commands:
#   extract-cmake-flags.py                            -- -DCMAKE_TOOLCHAIN_FILE=$(ls -1d ~/puppet/toolchain-files/clang_rwdi.cmake )
#   extract-cmake-flags.py --conan-profile clang_rwdi -- -DCMAKE_TOOLCHAIN_FILE=$(ls -1d ~/puppet/toolchain-files/clang_rwdi.cmake ) -DCMAKE_MODULE_PATH=#EXTRACT_BUILD_DIR#
#
# Note that any #EXTRACT_BUILD_DIR# in the cmake args gets replaced with the build dir being used

# A list of standard build directories, in which to search for include directories that are constructed as part of the build (eg git version headers)
CANDIDATE_REL_INC_BASES: List[Path] = [
	Path('ninja_clang_dbgchk'),
	Path('ninja_clang_debug'),
	Path('ninja_clang_memsan'),
	Path('ninja_clang_rwdi'),
	Path('ninja_clang_thrsan'),
	Path('ninja_clang_ubasan'),
	Path('ninja_gcc_dbgchk'),
	Path('ninja_gcc_debug'),
	Path('ninja_gcc_rwdi'),
	Path('ninja_gcc_ubasan'),
]

logging.basicConfig(
	format='%(asctime)s [ %(levelname)s ] %(message)s',
	level=logging.INFO,
	stream=sys.stderr,
)
logger = logging.getLogger( __name__ )

def resolve_include_dir(query_dir: Path,
                        *,
                        candidate_rel_inc_bases: List[Path]
                        ) -> Path:
	'''
	Find the an existing directory that matches the specified include directory, relative to one of the base directories
	(which are typically build directories) or just return the original if none can be found

	This is used to handle finding an include directory that's constructed as part of the build (eg git version headers)

	:param query_dir               : The relative dir to search for (eg Path('source/external_info))
	:param candidate_rel_inc_bases : A list of build directories in which special, build-constructed include directories might be found (eg [ Path('ninja_clang_dbgchk'), ...])
	'''
	if not query_dir.is_absolute():
		for candidate_rel_inc_base in candidate_rel_inc_bases:
			if (candidate_rel_inc_base / str(query_dir)).is_dir():
				return (candidate_rel_inc_base / str(query_dir)).resolve()
	return query_dir


def extract_flags_from_cmake_db(*,
                                cmake_commands_db: List[dict],
                                candidate_rel_inc_bases: List[Path]
                                ) -> List[str]:
	'''
	Extract the union of all the flags of interest in all the commands

	:param cmake_commands_db       : The commands
	:param candidate_rel_inc_bases : A list of build directories in which special, build-constructed include directories might be found
	'''
	definition_of_macro_name: Dict[str,str] = {}
	system_includes: Set[Path] = set()
	local_includes: Set[Path] = set()
	cpp_standard: Optional[str] = None

	# Grab all the flags of interest from all the commands
	for compile_command in cmake_commands_db:
		command_parts = compile_command['command'].split()
		for [cmd_idx, cmd_part] in enumerate(command_parts):
			if cmd_part == '-isystem':
				system_includes.add(Path(command_parts[cmd_idx + 1]))
			if cmd_part.startswith('-I'):
				if cmd_part == '-I':
					local_includes.add(Path(command_parts[cmd_idx + 1]))
				else:
					local_includes.add(Path(cmd_part[2:]))
			elif cmd_part.startswith('-D'):
				definition_key = cmd_part[2:].split('=')[0]
				definition_of_macro_name[definition_key] = cmd_part
			elif cmd_part.startswith('-std='):
				cpp_standard = cmd_part[5:]

	# Return all the parts
	return [
		*sorted(definition_of_macro_name.values()),
		*[
			'-I' + str(resolve_include_dir(x, candidate_rel_inc_bases=candidate_rel_inc_bases))
			for x in sorted(local_includes)
		],
		*itertools.chain.from_iterable(
			('-isystem', str(resolve_include_dir(x, candidate_rel_inc_bases=candidate_rel_inc_bases)))
			for x in sorted(system_includes)
		),
		*([] if cpp_standard is None else [f'-std={cpp_standard}'])
	]


def main():
	'''
	The main function, to prevent global variables
	'''

	# Prepare an ArgumentParser
	arg_parser = argparse.ArgumentParser(
		description="Extract the -std=..., -D... and -isystem flags from the compile commands CMake generates.",
		epilog="Append arguments to pass-through to CMake after a dummy '--' argument",
	)
	arg_parser.add_argument('--conan-profile', type=str,
                         help='Run Conan before CMake using the specified profile')

	# In a temporary directory...
	with tempfile.TemporaryDirectory() as temp_dir_handle:
		temp_dir = Path(temp_dir_handle)

		# Process the command-line arguments
		all_args = sys.argv[1:]
		num_arg_breakers = all_args.count('--')
		if num_arg_breakers > 1:
			arg_parser.error("The command line arguments breaker '--' should only be used at most once")
		arg_breaker_index = all_args.index('--') if (num_arg_breakers == 1) else len(all_args)
		local_args = all_args[0: arg_breaker_index]
		cmake_args = [x.replace('#EXTRACT_BUILD_DIR#', str(temp_dir)) for x in all_args[arg_breaker_index + 1: len(all_args)]]
		args = arg_parser.parse_args(local_args)

		# Log the args
		logger.info(f'Conan profile                      : { str(args.conan_profile) }')
		logger.info(f'Arguments to pass through to CMake : { " ".join( cmake_args ) }')

		# If there's a Conan profile command, run Conan
		if args.conan_profile is not None:
			conan_command: List[str] = [
				'conan',
				'install',
				'--build', 'missing',
				'--install-folder', str(temp_dir),
				'.',
				'--profile', str(args.conan_profile),
			]
			logger.info(f'About to run Conan command: { shlex.join(conan_command) }')
			conan_result = subprocess.run(conan_command, check=False, capture_output=True, text=True)
			print(f"\nConan stdout:\n{ conan_result.stdout }\nConan stderr:\n{ conan_result.stderr }", file=sys.stderr)
			conan_result.check_returncode()

		# Run CMake
		cmake_command: List[str] = [
			'cmake',
			('-B' + str(temp_dir)),
			'-H.',
			'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
			*cmake_args
		]
		logger.info(f'About to run CMake command: { shlex.join(cmake_command) }')
		cmake_result = subprocess.run(cmake_command, check=False, capture_output=True, text=True)
		print(f"\nCMake stdout:\n{ cmake_result.stdout }\nCMake stderr:\n{ cmake_result.stderr }", file=sys.stderr)
		cmake_result.check_returncode()

		# Read the compile commands data
		with open(temp_dir / 'compile_commands.json', 'r') as compile_commands_fh:
			flags = extract_flags_from_cmake_db(
				cmake_commands_db=json.loads(compile_commands_fh.read()),
				candidate_rel_inc_bases=CANDIDATE_REL_INC_BASES,
			)

	# Print the extracted flags
	print(shlex.join(flags))


if __name__ == "__main__":
	main()
