#!/usr/bin/env python
# -*- coding: utf-8 -*-
# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# PYTHON_ARGCOMPLETE_OK

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import errno
import os
import shutil
import sys
import traceback

from ansible import context
from ansible.errors import AnsibleError, AnsibleOptionsError, AnsibleParserError
from ansible.module_utils._text import to_text


# Used for determining if the system is running a new enough python version
# and should only restrict on our documented minimum versions
_PY38_MIN = sys.version_info[:2] >= (3, 8)
_PY3_MIN = sys.version_info[:2] >= (3, 5)
_PY2_MIN = (2, 6) <= sys.version_info[:2] < (3,)
_PY_MIN = _PY3_MIN or _PY2_MIN
if not _PY_MIN:
    raise SystemExit(
        f"ERROR: Ansible requires a minimum of Python2 version 2.6 or Python3 version 3.5. Current version: {''.join(sys.version.splitlines())}"
    )


class LastResort(object):
    # OUTPUT OF LAST RESORT
    def display(self, msg, log_only=None):
        print(msg, file=sys.stderr)

    def error(self, msg, wrap_text=None):
        print(msg, file=sys.stderr)


if __name__ == '__main__':

    display = LastResort()

    try:  # bad ANSIBLE_CONFIG or config options can force ugly stacktrace
        import ansible.constants as C
        from ansible.utils.display import Display, initialize_locale
    except AnsibleOptionsError as e:
        display.error(to_text(e), wrap_text=False)
        sys.exit(5)

    initialize_locale()

    me = os.path.basename(sys.argv[0])

    cli = None
    try:
        display = Display()
        if C.CONTROLLER_PYTHON_WARNING and not _PY38_MIN:
            display.deprecated(
                f"Ansible will require Python 3.8 or newer on the controller starting with Ansible 2.12. Current version: {''.join(sys.version.splitlines())}",
                version='2.12',
                collection_name='ansible.builtin',
            )
        display.debug("starting run")

        sub = None
        target = me.split('-')
        if target[-1][0].isdigit():
            # Remove any version or python version info as downstreams
            # sometimes add that
            target = target[:-1]

        if len(target) > 1:
            sub = target[1]
            myclass = f"{sub.capitalize()}CLI"
        elif target[0] == 'ansible':
            sub = 'adhoc'
            myclass = 'AdHocCLI'
        else:
            raise AnsibleError(f"Unknown Ansible alias: {me}")

        try:
            mycli = getattr(__import__(f"ansible.cli.{sub}", fromlist=[myclass]), myclass)
        except ImportError as e:
            # ImportError members have changed in py3
            msg = e.msg if 'msg' in dir(e) else e.message
            if msg.endswith(f' {sub}'):
                raise AnsibleError(f"Ansible sub-program not implemented: {me}")
            else:
                raise

        b_ansible_dir = os.path.expanduser(os.path.expandvars(b"~/.ansible"))
        try:
            os.mkdir(b_ansible_dir, 0o700)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                display.warning("Failed to create the directory '%s': %s"
                                % (to_text(b_ansible_dir, errors='surrogate_or_replace'),
                                   to_text(exc, errors='surrogate_or_replace')))
        else:
            display.debug("Created the '%s' directory" % to_text(b_ansible_dir, errors='surrogate_or_replace'))

        try:
            args = [to_text(a, errors='surrogate_or_strict') for a in sys.argv]
        except UnicodeError:
            display.error('Command line args are not in utf-8, unable to continue.  Ansible currently only understands utf-8')
            display.display(u"The full traceback was:\n\n%s" % to_text(traceback.format_exc()))
            exit_code = 6
        else:
            cli = mycli(args)
            exit_code = cli.run()

    except AnsibleOptionsError as e:
        cli.parser.print_help()
        display.error(to_text(e), wrap_text=False)
        exit_code = 5
    except AnsibleParserError as e:
        display.error(to_text(e), wrap_text=False)
        exit_code = 4
    except AnsibleError as e:
        display.error(to_text(e), wrap_text=False)
        exit_code = 1
    except KeyboardInterrupt:
        display.error("User interrupted execution")
        exit_code = 99
    except Exception as e:
        if C.DEFAULT_DEBUG:
            # Show raw stacktraces in debug mode, It also allow pdb to
            # enter post mortem mode.
            raise
        have_cli_options = bool(context.CLIARGS)
        display.error(
            f"Unexpected Exception, this is probably a bug: {to_text(e)}",
            wrap_text=False,
        )
        if not have_cli_options or context.CLIARGS['verbosity'] > 2:
            log_only = False
            if hasattr(e, 'orig_exc'):
                display.vvv('\nexception type: %s' % to_text(type(e.orig_exc)))
                why = to_text(e.orig_exc)
                if to_text(e) != why:
                    display.vvv('\noriginal msg: %s' % why)
        else:
            display.display("to see the full traceback, use -vvv")
            log_only = True
        display.display(u"the full traceback was:\n\n%s" % to_text(traceback.format_exc()), log_only=log_only)
        exit_code = 250

    sys.exit(exit_code)
