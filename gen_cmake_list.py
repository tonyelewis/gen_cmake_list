#!/usr/bin/env python3

'''Recursively scan the current directory for .cpp files and then
write them as a tree of CMake variables to `./auto_generated_file_list.cmake`'''

from collections import defaultdict
from functools   import cmp_to_key
from itertools   import chain, groupby
from os          import walk
from pathlib     import Path
from re          import search
from typing      import Callable, Dict, List, Tuple, Union


autogen_warning_str = "##### DON'T EDIT THIS FILE - IT'S AUTO-GENERATED #####"


def recurse_get_matching_files(prm_root_dir: Path, prm_filter: Callable[[Path], bool]) -> List[Path]:
	'''Recurse through the specified directory and return a sorted list of files matching the specified filter function
	
	The files will be returned as relative to prm_root_dir.'''
	def make_to_file(recurse_dir_and_file: Tuple[ Path, str ]) -> Path:
		( recurse_dir, file ) = recurse_dir_and_file
		return Path( recurse_dir ).relative_to( prm_root_dir ) / file

	return sorted(
		filter( prm_filter,
			map( make_to_file,
				( ( Path( recurse_dir ), file ) for recurse_dir, _, files in walk( prm_root_dir ) for file in files )
			)
		)
	)


class cmake_tree_nonleaf_node:
	'''Represent a non-leaf node (ie directory) in the tree of dirs/files to be written out to CMake variables'''

	def __init__(self, prm_path: Path) -> None:
		self.path = prm_path

	def __repr__(self) -> str:
		return 'cmake_tree_nonleaf_node(' + repr(self.path) + ')'

	def __hash__(self):
		'''Provide a hash function to allow these to be used as keys in a dict
		
		Make the result different from just hashing the pat'''
		return hash( ( 'ctnn', self.path ) )

	def __eq__(self, other) -> bool:
		return self.path == other.path

	def __ne__(self, other) -> bool:
		return not( self == other )

	def __lt__(self, other) -> bool:
		if type( other ) is cmake_tree_nonleaf_node:
			return self.path < other.path
		elif isinstance( other, Path):
			return self.path < other
		else:
			return NotImplemented

	def __gt__(self, other) -> bool:
		if type( other ) is cmake_tree_nonleaf_node:
			return self.path > other.path
		elif isinstance( other, Path):
			return self.path > other
		else:
			return NotImplemented

	def to_name(self, prm_keystem: str) -> str:
		if self.path.is_absolute():
			raise Exception( 'Should not request key of absolute directory' )

		if not self.path.parts:
			return prm_keystem
		else:
			return prm_keystem + '_' + str( self.path ).upper().replace( '/', '_' )



class cmake_tree_links:
	'''Represent a tree of dirs/files to be written out to CMake variables

	Every non-leaf node represents the parent directory of its children, eg:
	
	    cmake_tree_nonleaf_node( Path( 'uni/structure/view_cache/filter' ) ) : {
	    	Path( 'uni/structure/view_cache/filter/filter_vs_full_score.cpp'       ) : 1,
	    	Path( 'uni/structure/view_cache/filter/filter_vs_full_score_list.cpp ' ) : 1
	    }
	'''

	def __init__(self) -> None:
		# self.data is a defaultdict from cmake_tree_nonleaf_node to a dict of cmake_tree_nonleaf_node/Path
		#
		# The second level of dict is conceptually just a list but the dict is being used to provide convenient
		# sorting and uniqueing
		#
		# Every value that appears as a key should also appear as a child of a cmake_tree_nonleaf_node
		# for its parent directory. For example if there's a node with key
		#
		#     cmake_tree_nonleaf_node( Path( 'uni/structure/view_cache/filter/detail' ) )
		#
		# ...then there should also be an entry:
		#
		# 	cmake_tree_nonleaf_node( Path( 'uni/structure/view_cache/filter' ) ) : {
		# 		cmake_tree_nonleaf_node( Path( 'uni/structure/view_cache/filter/detail') ) : 1,
		# 		[...]
		# 	}
		#
		# ...etc...
		self.data = defaultdict(dict)

	def _insert_entry_of_nonleaf_node(self, prm_nonleaf_node: cmake_tree_nonleaf_node, prm_entry: Union[cmake_tree_nonleaf_node, Path]) -> None:
		'''Insert an entry in the data for the specified key/value pair
		
		By itself, this doesn't populate parents so users should call add_file() instead'''
		self.data[ prm_nonleaf_node ][ prm_entry ] = 1

	def add_file(self, prm_file: Path) -> None:
		'''Add a file to the tree
		
		This automatically adds parents to their parents (and so on)'''
		if not prm_file.parts or prm_file.is_absolute():
			raise Exception( 'Cannot add empty file or absolute file to cmake_tree_links')

		path_backstepper = prm_file
		while path_backstepper.parts:
			entry = path_backstepper if path_backstepper == prm_file else cmake_tree_nonleaf_node( path_backstepper )
			self._insert_entry_of_nonleaf_node( cmake_tree_nonleaf_node( path_backstepper.parent ), entry )
			path_backstepper = path_backstepper.parent

	def cmake_string_for_nonleaf_node(self, prm_keystem: str, prm_node: cmake_tree_nonleaf_node) -> str:
		'''Return a string containing CMake text to create a variable for the specified node under the
		specified prm_keystem (eg 'NORMSOURCES')
		
		If in doubt, call to_cmake_string() instead'''
		def cmake_str_of_leaf(prm_leaf: Union[ Path, cmake_tree_nonleaf_node ] ) -> str:
			if type( prm_leaf ) is cmake_tree_nonleaf_node:
				return '${' + prm_leaf.to_name( prm_keystem ) + '}'
			else:
				return str( prm_leaf )
		return (
			  "set(\n\t"
			+ prm_node.to_name( prm_keystem )
			+ "".join(
				  "\n\t\t"
				+ cmake_str_of_leaf( x ) for x in sorted( self.data[ prm_node ] )
			)
			+ "\n)"
		)

	def to_cmake_string(self, prm_keystem: str) -> str:
		'''Return a string containing CMake text to create a tree of variables for the files in this tree'''

		# Define a cmp-style function for sorting the nodes:
		#  * If one of the nodes has a path that's the start of the other's path, evaluate the longer one lower (ie first)
		#  * otherwise, just return normal cmp on the paths
		def my_key_cmp(lhs: cmake_tree_nonleaf_node, rhs: cmake_tree_nonleaf_node) -> int:
			min_num_parts = min( len( lhs.path.parts ), len( rhs.path.parts ) )
			if lhs.path.parts[ 0 : min_num_parts ] == rhs.path.parts[ 0 : min_num_parts ]:
				return ( len( lhs.path.parts ) < len( rhs.path.parts ) ) - ( len( lhs.path.parts ) > len( rhs.path.parts ) )
			else:
				return ( lhs.path > rhs.path ) - ( lhs.path < rhs.path )

		# Return the result of joining the CMake strings for each of the sorted keys
		sorted_keys = sorted( self.data, key=cmp_to_key( my_key_cmp ) )
		return "\n\n".join( self.cmake_string_for_nonleaf_node( prm_keystem, x ) for x in sorted_keys )

def cmake_set_string_of_keystem_and_files(prm_keystem: str, prm_files: List[Path]) -> str:
	'''Get the CMake test for a lists of files with a specified key stem (eg 'NORMSOURCES')'''
	the_tree = cmake_tree_links()
	for file in prm_files:
		if file.is_absolute():
			raise Exception( 'Files should all be relative by this point' )
		the_tree.add_file( file )
	return the_tree.to_cmake_string( prm_keystem )

def cmake_text_of_files_by_keystem(prm_files_by_keystem: Dict[ str, List[ Path ]]) -> str:
	'''Get the CMake test for lists of files, keyed in a dictionary under the keystem to use (eg 'NORMSOURCES')'''
	sorted_keys = sorted( prm_files_by_keystem.keys() )
	return (
			  autogen_warning_str
			+ "\n"
			+ "\n".join( map( lambda x: "\n" + cmake_set_string_of_keystem_and_files( x, prm_files_by_keystem[ x ] ), sorted_keys ) )
			+ "\n\n"
			+ autogen_warning_str
			+ "\n"
	)

# Get a sorted list of all (relative) files in the directory (or its children) with filenames ending with '.cpp'
all_source_files = recurse_get_matching_files( Path.cwd(), lambda x: str( x ).endswith( '.cpp' ) )

# Group the .cpp files into two lists:
# * TESTSOURCES for filenames that indicated they're test-related
# * NORMSOURCES for all others
source_files_by_keystem = {
	'NORMSOURCES' : [ x for x in all_source_files if not search( '(Test|_test|_fixture).cpp', str( x ) ) ],
	'TESTSOURCES' : [ x for x in all_source_files if     search( '(Test|_test|_fixture).cpp', str( x ) ) ],
}

# Write those two sets out to CMake text that will build them into a tree of CMake variables
with open( Path.cwd() / 'auto_generated_file_list.cmake', 'w' ) as output_cmake_file:
	output_cmake_file.write( cmake_text_of_files_by_keystem( source_files_by_keystem ) )
