# typedload
# Copyright (C) 2021 Salvo "LtWorf" Tomaselli
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

from typing import List, NamedTuple, Union
import sys

from typedload import load
import apischema
import pydantic

from common import timeit


class DataPy(pydantic.BaseModel):
    data: List[Union[int, float]]


class Data(NamedTuple):
    data: List[Union[int, float]]


data = {'data': [i if i % 2 else float(i) for i in range(3000000)]}


if sys.argv[1] == '--typedload':
    print(timeit(lambda: load(data, Data)))
elif sys.argv[1] == '--pydantic':
    print(timeit(lambda: DataPy(**data)))
elif sys.argv[1] == '--apischema':
    print(timeit(lambda: apischema.deserialize(Data, data)))
