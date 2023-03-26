#!/usr/bin/env python3

import subprocess
import sys

from pathlib import Path
from typing import List


def main(argv: List[str]):
	'''
	The main function (to prevent global variables)
	'''
	if not (len(argv) in [2, 3]):
		print(f'Usage: { Path( argv[ 0 ] ).stem } branch_name (branch_destination)')
		sys.exit()

	(_, branch_name, *_) = argv

	# Run `git branch -vv` to check if the git branch is checked out anywhere
	git_branch_list_command = [
		'git',
		'branch',
		'-vv',
	]
	git_branch_list_result = subprocess.run(
		git_branch_list_command,
		capture_output=True,
		check=True,
		text=True,
	)
	checked_out_branch_lines: List[str] = [x for x in git_branch_list_result.stdout.splitlines() if x.startswith('+ ')]
	for checked_out_branch_line in checked_out_branch_lines:
		if checked_out_branch_line.startswith(f'+ { branch_name }'):
			print(f'Branch { branch_name } is already checked out:\n\n{ checked_out_branch_line }')
			sys.exit()

	# Run the `git branch --force` command and print the result
	git_branch_force_result = subprocess.run(
		['git', 'branch', '--force', *argv[1:]],
		capture_output=True,
		check=False,
		text=True,
	)
	print(git_branch_force_result.stdout, sep='', end='',)
	print(git_branch_force_result.stderr, sep='', end='', file=sys.stderr)
	sys.exit( git_branch_force_result.returncode )


if __name__ == '__main__':
	main(sys.argv)
