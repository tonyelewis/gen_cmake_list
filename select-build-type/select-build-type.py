#!/usr/bin/env python3

import random
import sys
import os

from asciimatics.event  import KeyboardEvent
from asciimatics.screen import Screen

options = [
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

def choose_build_type_with_screen(screen):
	# Seem to need to do this to prevent the first printed line always using white foreground color
	screen.print_at( '.', 0, 0, )
	screen.refresh()
	screen.print_at( ' ', 0, 0, )

	active_index = 0
	if 'BUILDTYPE' in os.environ and os.environ[ 'BUILDTYPE' ] in options:
		active_index = options.index( os.environ[ 'BUILDTYPE' ] )

	# Run the event loop
	while True:

		# Print the options
		for option_idx, option in enumerate( options ):
			is_active = option_idx == active_index
			screen.print_at(
				option,
				x      = 0,
				y      = option_idx,
				bg     = Screen.COLOUR_WHITE if is_active else Screen.COLOUR_BLACK,
				colour = Screen.COLOUR_BLACK if is_active else Screen.COLOUR_WHITE,
			)

		# Get any event and respond to relevant keys
		event = screen.get_event()
		if isinstance( event, KeyboardEvent ):
			if event.key_code in ( ord( "\n" ), ord('Q'), ord('q') ):
				return options[ active_index ]
			if event.key_code == Screen.KEY_DOWN:
				# active_index = min( len( options ) - 1, active_index + 1 )
				active_index = active_index + 1 if active_index + 1 < len( options ) else 0
			elif event.key_code == Screen.KEY_UP:
				active_index = active_index - 1 if active_index     > 0              else len( options ) - 1

		# Refresh screen
		screen.refresh()

if len( sys.argv ) != 2:
	print( '''Usage: select-build-type.py script-file
	
Prompt the user to choose a BUILDTYPE and then print a zsh/bash shell script that
sets the BUILDTYPE environment variable accordingly.''' )

chosen_build_type = Screen.wrapper( choose_build_type_with_screen )

with open( sys.argv[ 1 ], 'w' ) as script_fh:
	script_fh.write( f'export BUILDTYPE={ chosen_build_type }' )
