#!/usr/bin/env python3

import dataclasses
import functools
import os
import sys

from enum import Enum
from pathlib import Path
from typing import List, Optional

from asciimatics.event import KeyboardEvent  # type: ignore[import]
from asciimatics.screen import Screen  # type: ignore[import]

COLOUR_BRIGHT_RED = 196

STD_BUILD_TYPES = [
	'ninja_clang_dbgchk',
	'ninja_clang_debug',
	'ninja_clang_memsan',
	'ninja_clang_rwdi',
	'ninja_clang_thrsan',
	'ninja_clang_ubasan',
	'ninja_gcc_dbgchk',
	'ninja_gcc_debug',
	'ninja_gcc_rwdi',
	'ninja_gcc_ubasan',
]


def remove_prefix(the_str: str, prefix: str):
	'''
	Return a copy of the_str with any prefix removed from the start

	TODO: Come Python 3.9, remove this and use the removeprefix() method of string instead

	:param the_str      : The string
	:param prefix : The prefix
	'''
	return the_str[len(prefix):] if the_str.startswith(prefix) else the_str


class BuildPresence(Enum):
	'''
	How much a build_type is present in the local directory
	'''

	# There is no directory for the build_type
	ABSENT = 1

	# The build_type has a directory but it doesn't contain a build.ninja file
	HAS_DIR = 2

	# The build_type has a directory and it contains a build.ninja file
	HAS_DIR_AND_NINJA_FILE = 3


@dataclasses.dataclass
class BuildTypeOption:
	'''
	A possible build_type and its associated properties
	'''

	# The name of the build_type (eg ninja_clang_rwdi)
	build_type: str

	# How much the build_type is present in the local directory
	presence: BuildPresence = BuildPresence.ABSENT

	# Whether this is one of the standard build_types
	is_standard: bool = False


def make_build_type_option(build_type: str,
                           is_standard: bool
                           ) -> BuildTypeOption:
	'''
	Make a BuildTypeOption by checking the local directories to populate the appropriate fields

	:param build_type  : The name of the build_type (eg 'ninja_clang_rwdi')
	:param is_standard : Whether this is one of the standard build_types
	'''
	build_type_path = Path(build_type)
	no_dir_present = len(build_type_path.parts) != 1 or not build_type_path.is_dir()
	no_ninja_file = not (build_type_path / 'build.ninja').is_file()
	return BuildTypeOption(
		build_type=build_type,
		presence=(
			# autopep8: off
			BuildPresence.ABSENT                 if no_dir_present else
			BuildPresence.HAS_DIR                if no_ninja_file  else
			BuildPresence.HAS_DIR_AND_NINJA_FILE
			# autopep8: on
		),
		is_standard=is_standard,
	)


@dataclasses.dataclass
class BuildTypeDecision:
	'''
	The user's decision
	'''

	# The name of the selected build_type
	build_type: str

	# Whether to (re)run conan/cmake on the chosen build_type
	cmake_it: bool = False


def choose_build_type_with_screen(screen: Screen,
                                  build_type_options: List[BuildTypeOption]
                                  ) -> Optional[BuildTypeDecision]:
	'''
	TODOCUMENT

	:param screen             : TODOCUMENT
	:param build_type_options : TODOCUMENT
	'''
	# Seem to need to do this to prevent the first printed line always using white foreground color
	screen.print_at('.', 0, 0, )
	screen.refresh()
	screen.print_at(' ', 0, 0, )

	build_types = [x.build_type for x in build_type_options]

	active_index = 0
	cmake_it = False
	if 'BUILDTYPE' in os.environ and os.environ['BUILDTYPE'] in build_types:
		active_index = build_types.index(os.environ['BUILDTYPE'])

	# Run the event loop
	while True:

		# Print the build_type_options
		for option_idx, build_type_option in enumerate(build_type_options):
			max_build_type_len = max(len(x) for x in build_types)
			is_active = option_idx == active_index
			screen.print_at(
				(
					f' { build_type_option.build_type:{max_build_type_len}}      '
					+ (
						' ' if build_type_option.presence == BuildPresence.ABSENT  else
						'?' if build_type_option.presence == BuildPresence.HAS_DIR else
						u'\u2713'
					)
					+ ( ' ' if build_type_option.is_standard else '   [not-in-standard-list] ' )
				),
				x      = 4,
				y      = option_idx,
				bg     = ( COLOUR_BRIGHT_RED if cmake_it else Screen.COLOUR_WHITE ) if is_active else Screen.COLOUR_BLACK,
				colour = Screen.COLOUR_BLACK if is_active else Screen.COLOUR_WHITE,
			)

		for y_val, text in enumerate( ( '',
		                                '[up/down]  : change selection',
		                                '[enter]    : select',
		                                '[spacebar] : toggle whether to also (re)run conan/cmake (indicated by red)',
		                                '[q]        : quit with no change',
		                                '',
		                                u'\u2713' + ' : ninja file exists in directory',
		                                '? : directory exists' ), len( build_type_options ) ):
			screen.print_at( text, x=0, y=y_val, )

		# Get any event and respond to relevant keys
		event = screen.get_event()
		if isinstance(event, KeyboardEvent):
			if event.key_code == ord("\n"):
				return BuildTypeDecision(build_type=build_type_options[active_index].build_type, cmake_it=cmake_it)
			if event.key_code in (Screen.KEY_ESCAPE, ord('Q'), ord('q')):
				return None
			if event.key_code == Screen.KEY_DOWN:
				active_index = active_index + 1 if active_index + 1 < len(build_type_options) else 0
			elif event.key_code == Screen.KEY_UP:
				active_index = active_index - 1 if active_index > 0 else len(build_type_options) - 1
			elif event.key_code == ord(' '):
				cmake_it = not cmake_it

		# Refresh screen
		screen.refresh()


def main():
	'''
	TODOCUMENT
	'''
	if len(sys.argv) != 2:
		print('''Usage: select-build-type.py script-file

Prompt the user to choose a BUILDTYPE and then print a zsh/bash shell script that
sets the BUILDTYPE environment variable accordingly.''')

	# Get the list of build_types
	local_build_types = sorted(list(
		x.name for x in Path('.').iterdir() if (
			x.is_dir() and (x.name.startswith('ninja_') or (x / 'build.ninja').is_file())
		)
	))
	all_build_types = sorted(list(set([*STD_BUILD_TYPES, *local_build_types])))
	std_build_type_options = [make_build_type_option(x, x in STD_BUILD_TYPES) for x in all_build_types]

	# Run the choose_build_type_with_screen in a screen
	decision = Screen.wrapper(functools.partial(
		choose_build_type_with_screen,
		build_type_options=std_build_type_options
	))

	# Open the script file that will enact the decision
	with open(sys.argv[1], 'w') as script_fh:

		# If something should be done...
		if decision is not None:

			# Write a command to set the build_type
			script_fh.write(f'export BUILDTYPE={ decision.build_type }\n')

			# If appropriate, write a command to run conan/cmake
			if decision.cmake_it:
				stripped_build_type = remove_prefix(decision.build_type, 'ninja_')
				script_fh.write(f'cmake-all-of { stripped_build_type }\n')


if __name__ == "__main__":
	main()
