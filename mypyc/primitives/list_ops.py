"""List primitive ops."""

from typing import List

from mypyc.ir.ops import ERR_MAGIC, ERR_NEVER, ERR_FALSE, EmitterInterface
from mypyc.ir.rtypes import (
    int_rprimitive, short_int_rprimitive, list_rprimitive, object_rprimitive, bool_rprimitive
)
from mypyc.primitives.registry import (
    name_ref_op, binary_op, func_op, method_op, custom_op, simple_emit,
    call_emit, call_negative_bool_emit,
)


# Get the 'builtins.list' type object.
name_ref_op('builtins.list',
            result_type=object_rprimitive,
            error_kind=ERR_NEVER,
            emit=simple_emit('{dest} = (PyObject *)&PyList_Type;'),
            is_borrowed=True)

# list(obj)
to_list = func_op(
    name='builtins.list',
    arg_types=[object_rprimitive],
    result_type=list_rprimitive,
    error_kind=ERR_MAGIC,
    emit=call_emit('PySequence_List'))


def emit_new(emitter: EmitterInterface, args: List[str], dest: str) -> None:
    # TODO: This would be better split into multiple smaller ops.
    emitter.emit_line('%s = PyList_New(%d); ' % (dest, len(args)))
    emitter.emit_line('if (likely(%s != NULL)) {' % dest)
    for i, arg in enumerate(args):
        emitter.emit_line('PyList_SET_ITEM(%s, %s, %s);' % (dest, i, arg))
    emitter.emit_line('}')


# Construct a list from values: [item1, item2, ....]
new_list_op = custom_op(arg_types=[object_rprimitive],
                        result_type=list_rprimitive,
                        is_var_arg=True,
                        error_kind=ERR_MAGIC,
                        steals=True,
                        format_str='{dest} = [{comma_args}]',
                        emit=emit_new)


# list[index] (for an integer index)
list_get_item_op = method_op(
    name='__getitem__',
    arg_types=[list_rprimitive, int_rprimitive],
    result_type=object_rprimitive,
    error_kind=ERR_MAGIC,
    emit=call_emit('CPyList_GetItem'))

# Version with no int bounds check for when it is known to be short
method_op(
    name='__getitem__',
    arg_types=[list_rprimitive, short_int_rprimitive],
    result_type=object_rprimitive,
    error_kind=ERR_MAGIC,
    emit=call_emit('CPyList_GetItemShort'),
    priority=2)

# This is unsafe because it assumes that the index is a non-negative short integer
# that is in-bounds for the list.
list_get_item_unsafe_op = custom_op(
    name='__getitem__',
    arg_types=[list_rprimitive, short_int_rprimitive],
    result_type=object_rprimitive,
    error_kind=ERR_NEVER,
    format_str='{dest} = {args[0]}[{args[1]}] :: unsafe list',
    emit=simple_emit('{dest} = CPyList_GetItemUnsafe({args[0]}, {args[1]});'))

# list[index] = obj
list_set_item_op = method_op(
    name='__setitem__',
    arg_types=[list_rprimitive, int_rprimitive, object_rprimitive],
    steals=[False, False, True],
    result_type=bool_rprimitive,
    error_kind=ERR_FALSE,
    emit=call_emit('CPyList_SetItem'))


# list.append(obj)
list_append_op = method_op(
    name='append',
    arg_types=[list_rprimitive, object_rprimitive],
    result_type=bool_rprimitive,
    error_kind=ERR_FALSE,
    emit=call_negative_bool_emit('PyList_Append'))

# list.extend(obj)
list_extend_op = method_op(
    name='extend',
    arg_types=[list_rprimitive, object_rprimitive],
    result_type=object_rprimitive,
    error_kind=ERR_MAGIC,
    emit=simple_emit('{dest} = _PyList_Extend((PyListObject *) {args[0]}, {args[1]});'))

# list.pop()
list_pop_last = method_op(
    name='pop',
    arg_types=[list_rprimitive],
    result_type=object_rprimitive,
    error_kind=ERR_MAGIC,
    emit=call_emit('CPyList_PopLast'))

# list.pop(index)
list_pop = method_op(
    name='pop',
    arg_types=[list_rprimitive, int_rprimitive],
    result_type=object_rprimitive,
    error_kind=ERR_MAGIC,
    emit=call_emit('CPyList_Pop'))

# list.count(obj)
method_op(
    name='count',
    arg_types=[list_rprimitive, object_rprimitive],
    result_type=short_int_rprimitive,
    error_kind=ERR_MAGIC,
    emit=call_emit('CPyList_Count'))


def emit_multiply_helper(emitter: EmitterInterface, dest: str, lst: str, num: str) -> None:
    temp = emitter.temp_name()
    emitter.emit_declaration('Py_ssize_t %s;' % temp)
    emitter.emit_lines(
        "%s = CPyTagged_AsSsize_t(%s);" % (temp, num),
        "if (%s == -1 && PyErr_Occurred())" % temp,
        "    CPyError_OutOfMemory();",
        "%s = PySequence_Repeat(%s, %s);" % (dest, lst, temp))


def emit_multiply(emitter: EmitterInterface, args: List[str], dest: str) -> None:
    emit_multiply_helper(emitter, dest, args[0], args[1])


def emit_multiply_reversed(emitter: EmitterInterface, args: List[str], dest: str) -> None:
    emit_multiply_helper(emitter, dest, args[1], args[0])


# list * int
binary_op(op='*',
          arg_types=[list_rprimitive, int_rprimitive],
          result_type=list_rprimitive,
          error_kind=ERR_MAGIC,
          format_str='{dest} = {args[0]} * {args[1]} :: list',
          emit=emit_multiply)

# int * list
binary_op(op='*',
          arg_types=[int_rprimitive, list_rprimitive],
          result_type=list_rprimitive,
          error_kind=ERR_MAGIC,
          format_str='{dest} = {args[0]} * {args[1]} :: list',
          emit=emit_multiply_reversed)


def emit_len(emitter: EmitterInterface, args: List[str], dest: str) -> None:
    temp = emitter.temp_name()
    emitter.emit_declaration('Py_ssize_t %s;' % temp)
    emitter.emit_line('%s = PyList_GET_SIZE(%s);' % (temp, args[0]))
    emitter.emit_line('%s = CPyTagged_ShortFromSsize_t(%s);' % (dest, temp))


# len(list)
list_len_op = func_op(name='builtins.len',
                      arg_types=[list_rprimitive],
                      result_type=short_int_rprimitive,
                      error_kind=ERR_NEVER,
                      emit=emit_len)
