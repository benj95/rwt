from __future__ import print_function

import os
import sys
import contextlib
import subprocess
import tempfile
import shutil
import itertools
import functools

from pip._vendor import pkg_resources


filterfalse = getattr(itertools, 'filterfalse', None) or itertools.ifilterfalse


@contextlib.contextmanager
def _update_working_set():
	"""
	Update the master working_set to include these new packages.

	TODO: would be better to use an officially-supported API,
	but no suitable API is apparent.
	"""
	try:
		pkg_resources = sys.modules['pkg_resources']
		if not hasattr(pkg_resources, '_initialize_master_working_set'):
			exec(_init_ws_patch, vars(pkg_resources))
		pkg_resources._initialize_master_working_set()
	except KeyError:
		# it's unnecessary to re-initialize when it hasn't
		# yet been initialized.
		pass
	yield


@contextlib.contextmanager
def load(*args):
	target = tempfile.mkdtemp(prefix='rwt-')
	args = ('install', '-t', target) + args
	cmd = (
		sys.executable,
		'-m', 'pip',
	) + args
	with _patch_prefix():
		subprocess.check_call(cmd)
	try:
		yield target
	finally:
		shutil.rmtree(target)


@contextlib.contextmanager
def load_direct(*args):
	target = tempfile.mkdtemp(prefix='rwt-')
	args = ('install', '-t', target) + args
	with _patch_prefix():
		__import__('pip').main(list(args))
	try:
		yield target
	finally:
		shutil.rmtree(target)


@contextlib.contextmanager
def _patch_prefix():
	"""
	To workaround pypa/pip#4106, override the system prefix with
	a user prefix, restoring the original file after.
	"""
	cfg_fn = os.path.expanduser('~/.pydistutils.cfg')
	with _save_file(cfg_fn):
		with open(cfg_fn, 'w') as cfg:
			cfg.write('[install]\nprefix=\n')
		yield


@contextlib.contextmanager
def _save_file(filename):
	"""
	Capture the state of filename and restore it after the context
	exits.
	"""
	# For now, only supports a missing filename.
	if os.path.exists(filename):
		tmpl = "Unsupported with extant {filename}"
		raise NotImplementedError(tmpl.format(**locals()))
	try:
		yield
	finally:
		if os.path.exists(filename):
			os.remove(filename)


@contextlib.contextmanager
def on_sys_path(*args):
	"""
	Install dependencies via args to pip and ensure they have precedence
	on sys.path.
	"""
	with load(*args) as target:
		sys.path.insert(0, target)
		try:
			with _update_working_set():
				yield target
		finally:
			sys.path.remove(target)


def pkg_installed(spec):
	try:
		pkg_resources.require(spec)
	except Exception:
		return False
	return True


not_installed = functools.partial(filterfalse, pkg_installed)


# from setuptools 19.6.2
_init_ws_patch = '''
def _initialize_master_working_set():
	"""
	Prepare the master working set and make the ``require()``
	API available.

	This function has explicit effects on the global state
	of pkg_resources. It is intended to be invoked once at
	the initialization of this module.

	Invocation by other packages is unsupported and done
	at their own risk.
	"""
	working_set = WorkingSet._build_master()
	_declare_state('object', working_set=working_set)

	require = working_set.require
	iter_entry_points = working_set.iter_entry_points
	add_activation_listener = working_set.subscribe
	run_script = working_set.run_script
	# backward compatibility
	run_main = run_script
	# Activate all distributions already on sys.path, and ensure that
	# all distributions added to the working set in the future (e.g. by
	# calling ``require()``) will get activated as well.
	add_activation_listener(lambda dist: dist.activate())
	working_set.entries=[]
	# match order
	list(map(working_set.add_entry, sys.path))
	globals().update(locals())
'''
