"""
typedload
Module to load data into typed data structures
"""

# Copyright (C) 2018-2021 Salvo "LtWorf" Tomaselli
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


import datetime
import ipaddress
from pathlib import Path
from typing import *

from .exceptions import *
from .typechecks import *
from .helpers import tname


__all__ = [
    'Loader',
]


T = TypeVar('T')


class Loader:
    """
    A loader object that recursively loads data into
    the desired type.

    basictypes: a set of types that are considered as
        building blocks for everything else and do not
        need to be converted further.
        If you are not loading from json, you probably
        want to add bytes to the set.

    failonextra: Disabled by default.
        When enabled, the loader will raise exceptions if
        there are fields in the data that are not being used
        by the type.

    basiccast: Enabled by default.
        When disabled, instead of trying to perform casts,
        exceptions will be raised.
        Since many json seem to encode numbers as strings,
        to avoid extra complications this functionality is
        provided.
        If you know that your original data is encoded
        properly, it is better to disable this.

    dictequivalence: Enabled by default.
        Automatically convert dict-like classes to dictionary
        when loading. This enables them to be loaded into other
        classes.
        At the moment it supports:
            argparse.Namespace

    raiseconditionerrors: Enabled by default.
        Raises exceptions when evaluating a condition from an
        handler. When disabled, the exceptions are not raised
        and the condition is considered False.

    uniondebugconflict: Disabled by default
        When enabled, all the possible types for the unions
        are evaluated instead of stopping at the first that works.
        If more than one type in the union works, an error is raised
        because the types are conflicting and the union might return
        different types with the same input value.
        This option makes the loading slower and is only to be used when
        debugging issues.

    mangle_key: Defaults to 'name'
        Specifies which key is used into the metadata dictionaries
        to perform name-mangling.

    handlers: This is the list that the loader uses to
        perform its task.
        The type is:
        List[
            Tuple[
                Callable[[Type[T]], bool],
                Callable[['Loader', Any, Type[T]], T]
            ]
        ]

        The elements are: Tuple[Condition,Loader]
        Condition(type) -> Bool
        Loader(loader, value, type) -> type

        In most cases, it is sufficient to append new elements
        at the end, to handle more types.

        There is an internal cache to speed up lookup, so after the
        first call to load, this should no longer be modified.

    strconstructed: Set of types to construct from a string.

    frefs: Dictionary to resolve ForwardRef.
        Something like
        class Node(NamedTuple):
            next: Optional['Node']

        requires a ForwardRef (also in python3.7), which means that the type
        is stored as string and must be resolved at runtime.

        This dictionary contains the names of the types as keys, and the
        actual types as values.

        A loader object by default starts with an empty dictionary and
        fills it with the types it encounters, but it is possible to
        manually add more types to the dictionary.

        Setting this to None disables any support for ForwardRef.

        Reusing the same loader object on unrelated types might cause
        failures, if the types are different but use the same names.

    These parameters can be set as named arguments in the constructor
    or they can be set later on.

    The constructor will accept any named argument, but only the documented
    ones have any effect. This is to allow custom handlers to have their
    own parameters as well.

    Using unions is complicated. If the types in the union are too
    similar to each other, it is easy to obtain an unexpected type.
    """

    def __init__(self, **kwargs) -> None:
        # Types that do not need conversion
        self.basictypes = {int, bool, float, str, NONETYPE}

        # If true, it attempts to do casting of basic types
        # otherwise an exception is raised
        self.basiccast = True

        # Raise errors if the value has more data than the
        # type expects.
        # By default the extra data is ignored.
        self.failonextra = False

        # Raise errors if the condition fails
        self.raiseconditionerrors = True

        # Forward refs dictionary
        self.frefs = {}  # type: Optional[Dict[str, Type]]

        # Enable conversion of dict-like things to dicts, before loading
        self.dictequivalence = True

        # Which key is used in metadata to perform name mangling
        self.mangle_key = 'name'

        # Fail if multiple types work within the union
        self.uniondebugconflict = False

        # Objects loaded from a string
        self.strconstructed = {
            Path,
            ipaddress.IPv4Address,
            ipaddress.IPv6Address,
            ipaddress.IPv4Network,
            ipaddress.IPv6Network,
            ipaddress.IPv4Interface,
            ipaddress.IPv6Interface
        }

        # The list of handlers to use to load the data.
        # It gets iterated in order, and the first condition
        # that matches is used to load the value.
        self.handlers = [
            (is_nonetype, _noneload),
            (is_union, _unionload),
            (lambda type_: type_ in self.basictypes, _basicload),
            (is_enum, _enumload),
            (is_tuple, _tupleload),
            (is_list, _listload),
            (is_dict, _dictload),
            (is_set, _setload),
            (is_frozenset, _frozensetload),
            (is_namedtuple, _namedtupleload),
            (is_dataclass, _dataclassload),
            (is_forwardref, _forwardrefload),
            (is_literal, _literalload),
            (is_typeddict, _typeddictload),
            (lambda type_: type_ in {datetime.date, datetime.time, datetime.datetime}, _datetimeload),
            (lambda type_: type_ in self.strconstructed, _strconstructload),
            (is_attrs, _attrload),
            (is_any, _anyload),
            (is_newtype, _newtypeload),
        ]  # type: List[Tuple[Callable[[Any], bool], Callable[[Loader, Any, Type], Any]]]

        for k, v in kwargs.items():
            setattr(self, k, v)

        self._indexcache = {}  # type: Dict[Type, int]

    def index(self, type_: Type[T]) -> int:
        """
        Returns the index in the handlers list
        that matches the given type.

        If no condition matches, ValueError is raised.
        """
        for i, cond in ((q[0], q[1][0]) for q in enumerate(self.handlers)):
            try:
                match = cond(type_)
            except:
                if self.raiseconditionerrors:
                    raise
                match = False
            if match:
                return i
        raise ValueError('No matching condition found')

    def load(self, value: Any, type_: Type[T], *, annotation: Optional[Annotation] = None) -> T:
        """
        Loads value into the typed data structure.

        TypeError is raised if there is no known way to treat type_,
        otherwise all errors raise a ValueError.

        annotation is used by recursive calls to track which path was
        being executed in case of exceptions.

        It is only needed when calling load recursively from
        a custom handler.
        """
        p_index = self._indexcache.get(type_)

        if p_index is not None:
            index = p_index
        else:
            try:
                index = self.index(type_)
                self._indexcache[type_] = index
            except ValueError:
                raise TypedloadTypeError(
                    'Cannot deal with value of type %s' % tname(type_),
                    value=value,
                    type_=type_
                )

            # Add type to known types, to resolve ForwardRef later on
            if self.frefs is not None and hasattr(type_, '__name__'):
                typename = type_.__name__
                if typename not in self.frefs:
                    self.frefs[typename] = type_

        func = self.handlers[index][1]

        try:
            return func(self, value, type_)
        except Exception as e:
            assert isinstance(e, TypedloadException)
            e.trace.insert(0, TraceItem(value, type_, annotation))
            raise e


def _forwardrefload(l: Loader, value: Any, type_: type) -> Any:
    """
    This resolves a ForwardRef.

    It just looks up the type in the dictionary of known types
    and loads the value using that.
    """
    if l.frefs is None:
        raise TypedloadException('ForwardRef resolving is disabled for the loader', value=value, type_=type_)
    tname = type_.__forward_arg__  # type: ignore
    t = l.frefs.get(tname)
    if t is None:
        raise TypedloadValueError(
            "ForwardRef '%s' unknown" % tname,
            value=value,
            type_=type_
        )
    return l.load(value, t, annotation=Annotation(AnnotationType.FORWARDREF, tname))


def _anyload(l: Loader, value: Any, type_: type) -> Any:
    return value


def _literalload(l: Loader, value: Any, type_: type) -> Any:
    """
    Checks if the value is within the allowed literals and
    returns it.
    """
    if value in literalvalues(type_):
        return value
    raise TypedloadValueError('Not one of the allowed values in %s' % tname(type_), value=value, type_=type_)


def _basicload(l: Loader, value: Any, type_: type) -> Any:
    """
    This converts a value into a basic type.

    In theory it does nothing, but it performs type checking
    and raises if conditions fail.

    It also attempts casting, if enabled.
    """

    if type(value) != type_:
        if l.basiccast:
            try:
                return type_(value)
            except ValueError as e:
                raise TypedloadValueError(str(e), value=value, type_=type_)
            except TypeError as e:
                raise TypedloadTypeError(str(e), value=value, type_=type_)
            except Exception as e:
                raise TypedloadException(str(e), value=value, type_=type_)
        else:
            raise TypedloadValueError('Got %s of type %s, expected %s' % (repr(value), tname(type(value)), tname(type_)), value=value, type_=type_)
    return value


def _listload(l: Loader, value, type_) -> List:
    """
    This loads into something like List[int]
    """
    if isinstance(value, dict):
        raise TypedloadTypeError('Unable to load dictionary as a list', value=value, type_=type_)
    t = type_.__args__[0]
    try:
        return [l.load(v, t, annotation=Annotation(AnnotationType.INDEX, i)) for i, v in enumerate(value)]
    except TypeError as e:
        if isinstance(e, TypedloadException):
            raise
        raise TypedloadTypeError(str(e), value=value, type_=type_)


def _dictload(l: Loader, value, type_) -> Dict:
    """
    This loads into something like Dict[str,str]

    Recursively loads both keys and values.
    """
    key_type, value_type = type_.__args__

    value = _dictequivalence(l, value)

    try:
        return {
            l.load(k, key_type, annotation=Annotation(AnnotationType.KEY, k)): l.load(v, value_type, annotation=Annotation(AnnotationType.VALUE, v))
            for k, v in value.items()}
    except AttributeError as e:
        raise TypedloadAttributeError(str(e), type_=type_, value=value)


def _setload(l: Loader, value, type_) -> Set:
    """
    This loads into something like Set[int]
    """
    if isinstance(value, dict):
        raise TypedloadTypeError('Unable to load dictionary as a set', value=value, type_=type_)
    t = type_.__args__[0]
    return {l.load(v, t, annotation=Annotation(AnnotationType.INDEX, i)) for i, v in enumerate(value)}


def _frozensetload(l: Loader, value, type_) -> FrozenSet:
    """
    This loads into something like FrozenSet[int]
    """
    if isinstance(value, dict):
        raise TypedloadTypeError('Unable to load dictionary as a frozenset', value=value, type_=type_)
    t = type_.__args__[0]
    return frozenset(l.load(v, t, annotation=Annotation(AnnotationType.INDEX, i)) for i, v in enumerate(value))


def _tupleload(l: Loader, value, type_) -> Tuple:
    """
    This loads into something like Tuple[int,str]
    """
    if isinstance(value, dict):
        raise TypedloadTypeError('Unable to load dictionary as a tuple', value=value, type_=type_)
    if HAS_TUPLEARGS:
        args = type_.__args__
    else:
        args = type_.__tuple_params__

    if len(args) == 2 and args[1] == ...: # Tuple[something, ...]
        return tuple(l.load(v, args[0], annotation=Annotation(AnnotationType.INDEX, i)) for i, v in enumerate(value))
    else: # Tuple[something, something, somethingelse]
        if l.failonextra and len(value) > len(args):
            raise TypedloadValueError('Value is too long for type %s' % tname(type_), value=value, type_=type_)
        elif len(value) < len(args):
            raise TypedloadValueError('Value is too short for type %s' % tname(type_), value=value, type_=type_)
        return tuple(l.load(v, t, annotation=Annotation(AnnotationType.INDEX, i)) for i, (v, t) in enumerate(zip(value, args)))


def _mangle_names(namesmap: Dict[str, str], value: Dict[str, Any], failonextra: bool) -> Dict[str, Any]:
    """
    Mangling names of a dictionary.

    The dictionary is copied internally.

    Namesmap is the mapping to be applied, in the format [dataname] = pyname
    """
    if not namesmap:
        return value
    r = {}

    # Disallow the python names if they are in the map
    skip = set(namesmap.values())

    for k, v in value.items():
        if k in skip and k not in namesmap:
            if failonextra:
                raise ValueError('Extra field: %s' % k)
            else:
                continue
        if k in namesmap:
            k = namesmap[k]
        r[k] = v
    return r


def _dataclassload(l: Loader, value: Dict[str, Any], type_) -> Any:
    """
    This loads a Dict[str, Any] into a NamedTuple.
    """
    from dataclasses import _MISSING_TYPE as DT_MISSING_TYPE
    fields = set(type_.__dataclass_fields__.keys())
    necessary_fields = {k for k,v in type_.__dataclass_fields__.items() if
                        v.init == True and
                        isinstance(v.default, DT_MISSING_TYPE) and
                        isinstance(v.default_factory, DT_MISSING_TYPE)}
    type_hints = {k: v.type for k,v in type_.__dataclass_fields__.items()}

    #Name mangling

    # Prepare the list of the needed name changes
    transforms = {}  # type: Dict[str, str]
    for pyname in fields:
        if type_.__dataclass_fields__[pyname].metadata:
            name = type_.__dataclass_fields__[pyname].metadata.get(l.mangle_key)
            if name:
                transforms[name] = pyname

    try:
        value = _mangle_names(transforms, value, l.failonextra)
    except ValueError as e:
        raise TypedloadValueError(str(e), value=value, type_=type_)
    except AttributeError as e:
        raise TypedloadAttributeError(str(e), value=value, type_=type_)

    return _objloader(l, fields, necessary_fields, type_hints, value, type_)


def _dictequivalence(l: Loader, value: Any) -> Dict:
    '''
    Helper function to convert classes that are functionally
    the same as a dict into a dict.

    At the moment the only class that can be converted is
    argparse.Namespace.

    in all other cases this simply returns value.
    '''
    # Convert argparse.Namespace to dictionary
    if l.dictequivalence and hasattr(value, '_get_kwargs'):
        return {k: v for k,v in value._get_kwargs()}
    return value


def _objloader(l: Loader, fields: Set[str], necessary_fields: Set[str], type_hints, value: Dict[str, Any], type_) -> Any:
    '''
    Helper function to load dict-like data into an object.
    '''
    try:
        vfields = set(value.keys())
    except AttributeError as e:
        newvalue = _dictequivalence(l, value)

        if newvalue is value:
            raise TypedloadAttributeError(str(e), value=value, type_=type_)
        else:
            value = newvalue
            vfields = set(value.keys())

    if necessary_fields.intersection(vfields) != necessary_fields:
        raise TypedloadValueError(
            'Value does not contain fields: %s which are necessary for type %s' % (
                necessary_fields.difference(vfields),
                tname(type_)
            ),
            value=value,
            type_=type_,
        )

    params = {}
    for k, v in value.items():
        if k not in fields:
            # Field in value is not in the type
            if l.failonextra:
                extra = ', '.join(vfields.difference(fields))
                raise TypedloadValueError(
                    'Dictionary has unrecognized fields: %s and cannot be loaded into %s' % (extra, tname(type_)),
                    value=value,
                    type_=type_,
                )
            else:
                continue
        params[k] = l.load(
            v,
            type_hints[k],
            annotation=Annotation(AnnotationType.FIELD, k),
        )
    try:
        return type_(**params)
    except TypeError as e:
        raise TypedloadTypeError(e)
    except ValueError as e:
        raise TypedloadValueError(e)


def _namedtupleload(l: Loader, value: Dict[str, Any], type_) -> Any:
    """
    This loads a Dict[str, Any] into a NamedTuple.
    """
    fields = set(type_.__annotations__.keys())
    optional_fields = set(getattr(type_, '_field_defaults', {}).keys())
    type_hints = type_.__annotations__
    necessary_fields = fields.difference(optional_fields)

    return _objloader(l, fields, necessary_fields, type_hints, value, type_)


def _typeddictload(l: Loader, value: Dict[str, Any], type_) -> Any:
    """
    This loads a Dict[str, Any] into a NamedTuple.
    """
    fields = set(type_.__annotations__.keys())
    type_hints = type_.__annotations__

    if hasattr(type_, '__required_keys__') and hasattr(type_, '__optional_keys__'):
        # TypedDict, since 3.9
        necessary_fields = type_.__required_keys__
    elif getattr(type_, '__total__', True) == False:
        # TypedDict, only for 3.8
        necessary_fields = set()
    else:
        necessary_fields = fields

    return _objloader(l, fields, necessary_fields, type_hints, value, type_)


def _unionload(l: Loader, value, type_) -> Any:
    """
    Loads a value into a union.

    Basically this iterates all the types inside the
    union, until one that doesn't raise an exception
    is found.

    If no suitable type is found, an exception is raised.
    """
    args = uniontypes(type_)

    value_type = type(value)

    # Do not convert basic types, if possible
    if value_type in l.basictypes and value_type in args:
        return value

    exceptions = []

    # Give a score to the types
    sorted_args = list(args)  # type: List[Type]
    sorted_args.sort(key=lambda i: i in l.basictypes)

    # Try all types
    loaded_count = 0
    r = None
    for t in sorted_args:
        try:
            r = l.load(value, t, annotation=Annotation(AnnotationType.UNION, t))
            loaded_count += 1
            if not l.uniondebugconflict:
                # Do not try more if we are not debugging
                break
        except TypedloadException as e:
            exceptions.append(e)

    if loaded_count == 1:
        # Loaded only once, all good
        return r
    elif loaded_count == 0:
        # Could not be loaded
        raise TypedloadValueError(
            'Value of %s could not be loaded into %s' % (tname(value_type), tname(type_)),
                value=value,
                type_=type_,
                exceptions=exceptions
        )
    else:
        # Loaded more than once, conflict
        raise TypedloadTypeError(
            'Value of %s could be loaded into %s %d times' % (tname(value_type), tname(type_), loaded_count),
                value=value,
                type_=type_,
                exceptions=exceptions
        )


def _enumload(l: Loader, value, type_) -> Enum:
    """
    This loads something into an Enum.

    It tries with basic types first.

    If that fails, it tries to look for type annotations inside the
    Enum, and tries to use those to load the value into something
    that is compatible with the Enum.

    Of course if that fails too, a ValueError is raised.
    """
    try:
        # Try naïve conversion
        return type_(value)
    except:
        pass

    # Try with the typing hints
    exceptions = []
    for _, t in get_type_hints(type_).items():
        try:
            return type_(l.load(value, t, annotation=Annotation(AnnotationType.UNION, t)))
        except Exception as e:
            exceptions.append(e)
    if len(type_.__members__) <= 10 and all(type(i.value) in l.basictypes for i in type_.__members__.values()):
        lst = '\nValue %s not between: ' % repr(value) + \
        ', '.join(repr(i.value) for i in type_.__members__.values())
    else:
        lst = ''
    raise TypedloadValueError(
        'Value of %s could not be loaded into %s%s' % (tname(type(value)), tname(type_), lst),
        value=value,
        type_=type_,
        exceptions=exceptions
    )


def _noneload(l: Loader, value, type_) -> None:
    """
    Loads a value that can only be None,
    so it fails if it isn't
    """
    if value is None:
        return None
    raise TypedloadValueError('Not None', value=value, type_=type_)


def _datetimeload(l: Loader, value, type_) -> Union[datetime.date, datetime.time, datetime.datetime]:
    try:
        return type_(*value)
    except TypeError as e:
        raise TypedloadTypeError(str(e), type_=type_, value=value)


def _attrload(l, value, type_):
    from attr._make import _Nothing as NOTHING

    fields = {i.name for i in type_.__attrs_attrs__}
    necessary_fields = set()
    type_hints = {i.name: i.type for i in type_.__attrs_attrs__}
    namesmap = {}  # type: Dict[str, str]

    for attribute in type_.__attrs_attrs__:
        if attribute.default is NOTHING and attribute.init:
            necessary_fields.add(attribute.name)

        # Manage name mangling
        if l.mangle_key in attribute.metadata:
            namesmap[attribute.metadata[l.mangle_key]] = attribute.name

    try:
        value = _mangle_names(namesmap, value, l.failonextra)
    except ValueError as e:
        raise TypedloadValueError(str(e), value=value, type_=type_)
    except AttributeError as e:
        raise TypedloadAttributeError(str(e), value=value, type_=type_)

    return _objloader(l, fields, necessary_fields, type_hints, value, type_)


def _strconstructload(l: Loader, value, type_):
    """
    Loader for all the types taking a string as single constructor parameter
    """
    try:
        return type_(value)
    except ValueError as e:
        raise TypedloadValueError(str(e), type_=type_, value=value)
    except TypeError as e:
        raise TypedloadTypeError(str(e), type_=type_, value=value)
    except Exception as e:
        raise TypedloadException(str(e), type_=type, value=value)


def _newtypeload(l: Loader, value, type_):
    return l.load(value, type_.__supertype__)
