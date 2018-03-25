# typedload
#
# This library loads Python data structures into
# more strict data structures.
#
# The main purpose is to load things that come from
# json, bson or similar into NamedTuple.
#
# For example this Json:
#    {
#        'users': [
#            {
#                'username': 'salvo',
#                'shell': 'bash',
#                'sessions': ['pts/4', 'tty7', 'pts/6']
#            },
#            {
#                'username': 'lop'
#            }
#        ],
#    }
#
# Can be treated more easily if loaded into this:
#
#class User(NamedTuple):
#    username: str
#    shell: str = 'bash'
#    sessions: List[str] = []
#
#class Logins(NamedTuple):
#    users: List[User]
#
# And can then be loaded with
#
# typedload.load(data, Logins)

# Copyright (C) 2018 Salvo "LtWorf" Tomaselli
#
# typedload is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# author Salvo "LtWorf" Tomaselli <tiposchi@tiscali.it>


from typing import Any


__all__ = [
    'dataloader',
    'load',
]


def load(value: Any, type_: type) -> Any:
    """
    Quick function call to load data into a type.

    It is useful to avoid creating the Loader object,
    in case only the default parameters are used.
    """
    from . import dataloader
    loader = dataloader.Loader()
    return loader.load(value, type_)
