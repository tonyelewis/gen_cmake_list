#!/usr/bin/env python3

from subprocess import PIPE, run
from tempfile   import TemporaryDirectory
from pathlib    import Path
from typing     import List

import argparse
import json
import sys

all_args = sys.argv[ 1: ]
num_arg_breakers = all_args.count( '--' )
if num_arg_breakers > 1:
	raise Exception( "The command line arguments breaker '--' should only be used at most once" )

arg_breaker_index = all_args.index( '--' ) if ( num_arg_breakers == 1 ) else len( all_args )
local_args        = all_args[ 0                     : arg_breaker_index ]
cmake_args        = all_args[ arg_breaker_index + 1 : len( all_args )   ]

arg_parser = argparse.ArgumentParser(
	description="Extract the -D... and -isystem flags from the compile commands CMake generates.",
	epilog="Append arguments to pass-through to CMake after a dummy '--' argument",
)
arg_parser.add_argument('--conan-profile-file', type=Path,
                   help='Run Conan before CMake using the specified file')

args = arg_parser.parse_args( local_args )

print( f'Conan profile file                 : ' + str( args.conan_profile_file ), file=sys.stderr )
print( f'Arguments to pass through to CMake : { " ".join( cmake_args ) }', file=sys.stderr )

temp_dir_handle    = TemporaryDirectory()
temp_dir           = Path( temp_dir_handle.name )

if args.conan_profile_file is not None:
	# Run conan
	conan_command: List[str] = [
		'conan',
		'install',
		'--build', 'missing',
		'--install-folder', str( temp_dir ),
		'.',
		'--profile', str( args.conan_profile_file ),
	]
	print( "About to run Conan command:\n\t" + ( ' ' . join( conan_command ) ), file=sys.stderr )
	conan_result = run( conan_command, stdout=PIPE, stderr=PIPE )
	print( "\nConan stdout:\n" + conan_result.stdout.decode() + "\nConan stderr:\n" + conan_result.stderr.decode(), file=sys.stderr )
	conan_result.check_returncode()

cmake_command: List[str] = [
	'cmake',
	( '-B' + str( temp_dir ) ),
	'-H.',
	'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
	*cmake_args
]
print( "About to run CMake command:\n\t" + ( ' ' . join( cmake_command ) ), file=sys.stderr )
cmake_result = run( cmake_command, stdout=PIPE, stderr=PIPE  )
print( "\nCMake stdout:\n" + cmake_result.stdout.decode() + "\nCMake stderr:\n" + cmake_result.stderr.decode(), file=sys.stderr )
cmake_result.check_returncode()

# Read the compile commands data
compile_commands_file: Path = temp_dir / 'compile_commands.json'
with open( compile_commands_file, 'r') as compile_commands_fh:
	compile_commands = json.loads( compile_commands_fh.read() )

def extract_flags_from_cmake_db(compile_commands):
	definitions     = set()
	system_includes = set()
	for compile_command in compile_commands:
		command_parts = compile_command[ 'command' ].split()
		for [ cmd_idx, cmd_part ] in enumerate( command_parts ):
			if cmd_part == '-isystem':
				system_includes.add( command_parts[ cmd_idx + 1 ] )
			elif cmd_part.startswith( '-D' ):
				definitions.add( cmd_part )
	return [
		*sorted( definitions ),
		*list( map(
			lambda x: '-isystem ' + x,
			sorted( system_includes )
		) )
	]

flags = extract_flags_from_cmake_db(compile_commands)

# print(
# 	"export CMAKE_EXTRACTED_COMPILE_FLAGS=' "
# 		+ ' '.join( sorted( flags ) )
# 		+ " '"
# )
print( ' '.join( sorted( flags ) ) )
