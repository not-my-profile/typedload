# typedload
# Copyright (C) 2018-2019 Salvo "LtWorf" Tomaselli
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

from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Set, Tuple, Union
import unittest

import attr

from typedload import load, dump, exceptions, typechecks
from typedload import datadumper


class Hair(Enum):
    BROWN = 'brown'
    BLACK = 'black'
    BLONDE = 'blonde'
    WHITE = 'white'


@attr.s
class Person:
    name = attr.ib(default='Turiddu', type=str)
    address = attr.ib(type=Optional[str], default=None)


@attr.s
class DetailedPerson(Person):
    hair = attr.ib(type=Hair, default=Hair.BLACK)


@attr.s
class Students:
    course = attr.ib(type=str)
    students = attr.ib(type=List[Person])

@attr.s
class Mangle:
    value = attr.ib(type=int, metadata={'name': 'va.lue'})

class TestAttrDump(unittest.TestCase):

    def test_basicdump(self):
        assert dump(Person()) == {}
        assert dump(Person('Alfio')) == {'name': 'Alfio'}
        assert dump(Person('Alfio', '33')) == {'name': 'Alfio', 'address': '33'}

    def test_norepr(self):
        @attr.s
        class A:
            i = attr.ib(type=int)
            j = attr.ib(type=int, repr=False)
        assert dump(A(1,1)) == {'i': 1}

    def test_dumpdefault(self):
        dumper = datadumper.Dumper()
        dumper.hidedefault = False
        assert dumper.dump(Person()) == {'name': 'Turiddu', 'address': None}

    def test_factory_dump(self):
        @attr.s
        class A:
            a: List[int] = attr.ib(factory=list, metadata={'ciao': 'ciao'})

        assert dump(A()) == {}
        assert dump(A(), hidedefault=False) == {'a': []}

    def test_nesteddump(self):
        assert dump(
            Students('advanced coursing', [
            Person('Alfio'),
            Person('Carmelo', 'via mulino'),
        ])) == {
            'course': 'advanced coursing',
            'students': [
                {'name': 'Alfio'},
                {'name': 'Carmelo', 'address': 'via mulino'},
            ]
        }


class TestAttrload(unittest.TestCase):

    def test_condition(self):
        assert typechecks.is_attrs(Person)
        assert typechecks.is_attrs(Students)
        assert typechecks.is_attrs(Mangle)
        assert typechecks.is_attrs(DetailedPerson)
        assert not typechecks.is_attrs(int)
        assert not typechecks.is_attrs(List[int])
        assert not typechecks.is_attrs(Union[str, int])
        assert not typechecks.is_attrs(Tuple[str, int])

    def test_basicload(self):
        assert load({'name': 'gino'}, Person) == Person('gino')
        assert load({}, Person) == Person('Turiddu')

    def test_nestenum(self):
        assert load({'hair': 'white'}, DetailedPerson) == DetailedPerson(hair=Hair.WHITE)

    def test_nested(self):
        assert load(
            {
                'course': 'advanced coursing',
                'students': [
                    {'name': 'Alfio'},
                    {'name': 'Carmelo', 'address': 'via mulino'},
                ]
            },
            Students,
        ) == Students('advanced coursing', [
            Person('Alfio'),
            Person('Carmelo', 'via mulino'),
        ])

    def test_uuid(self):
        import uuid

        @attr.s
        class A:
            a = attr.ib(type=int)
            uuid_value = attr.ib(type=str, init=False)

            def __attrs_post_init__(self):
                self.uuid_value = str(uuid.uuid4())

        assert type(load({'a': 1}, A).uuid_value) == str
        assert load({'a': 1}, A) != load({'a': 1}, A)


class TestMangling(unittest.TestCase):

    def test_load_metanames(self):
        a = {'va.lue': 12}
        b = a.copy()
        assert load(a, Mangle) == Mangle(12)
        assert a == b

    def test_dump_metanames(self):
        assert dump(Mangle(12)) == {'va.lue': 12}


class TestAttrExceptions(unittest.TestCase):

    def test_wrongtype(self):
        try:
            load(3, Person)
        except exceptions.TypedloadTypeError:
            pass

        data = {
            'course': 'how to be a corsair',
            'students': [
                {'name': 'Alfio'},
                3
            ]
        }
        try:
            load(data, Students)
        except exceptions.TypedloadTypeError as e:
            assert e.trace[-1].annotation[1] == 1

    def test_index(self):
        try:
            load(
                {
                    'course': 'advanced coursing',
                    'students': [
                        {'name': 'Alfio'},
                        {'name': 'Carmelo', 'address': 'via mulino'},
                        [],
                    ]
                },
                Students,
            )
        except Exception as e:
            assert e.trace[-2].annotation[1] == 'students'
            assert e.trace[-1].annotation[1] == 2
