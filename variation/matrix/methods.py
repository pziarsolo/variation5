from itertools import chain
import sys
import math

import h5py
import numpy

from variation.iterutils import group_items, first
from variation import SNPS_PER_CHUNK

# Missing docstring
# pylint: disable=C0111

AVAILABLE_MEM = 0.5 * 1024 * 1024


def resize_matrix(matrix, new_size):
    if is_array(matrix):
        matrix.resize(new_size, refcheck=False)

    elif is_dataset(matrix):
        matrix.resize(new_size)


def _extend_dset(dset, arrays):
    for array in arrays:
        append_matrix(dset, array)


def is_array(array):
    if isinstance(array, numpy.ndarray):
        return True
    else:
        return False


def is_dataset(array):
    if isinstance(array, h5py.Dataset):
        return True
    else:
        return False


def append_matrix(matrix, matrix_to_append):
    start = matrix.shape[0]
    stop = start + matrix_to_append.shape[0]
    size = matrix.shape
    new_size = list(size)
    new_size[0] = stop

    if is_dataset(matrix_to_append):
        array = matrix_to_append[:]
    else:
        array = matrix_to_append
    resize_matrix(matrix, new_size)

    matrix[start:stop] = array


def fill_array(array, size, dim=0):
    num_fill = size - array.shape[dim]
    fill_format = [[0, 0]] * dim + [[0, num_fill]] + [[0, 0]] * (array.ndim - dim - 1)
    return numpy.pad(array, fill_format, mode='constant', constant_values=0)


def extend_matrix(matrix, arrays):
    arrays = iter(arrays)
    if is_dataset(matrix):
        _extend_dset(matrix, arrays)
    else:
        _extend_array_with_iter(matrix, arrays)


def _extend_array(array, arrays):
    arrays = list(filter(lambda x: x is not None, arrays))
    if not arrays:
        return
    n_snps = sum([array_.shape[0] for array_ in arrays])
    n_snps += array.shape[0]

    for array_ in arrays:
        if array.shape[1:] != array_.shape[1:]:
            msg = 'The arrays to extend do not match the shape'
            raise ValueError(msg)

    i0 = array.shape[0]
    shape = list(arrays[0].shape)
    shape[0] = n_snps
    array.resize(shape, refcheck = False)

    for array_to_append in arrays:
        if array_to_append is array:
            msg = 'You cannot append an array onto itself'
            raise ValueError(msg)
        i1 = i0 + array_to_append.shape[0]
        array[i0:i1] = array_to_append
        i0 = i1


def _extend_array_with_iter(array, matrices):
    try:
        matrix = first(matrices)
    except ValueError:
        return

    matrices = chain([matrix], matrices)

    matrix_size = sys.getsizeof(matrix)
    mats_in_group = math.floor(AVAILABLE_MEM / matrix_size)
    if not mats_in_group:
        mats_in_group = 1
    for mats_in_mem in group_items(matrices, mats_in_group):
        _extend_array(array, mats_in_mem)


def num_variations(matrix):
    return matrix.shape[0]


def iterate_matrix_chunks(matrix):
    nsnps = num_variations(matrix)
    chunk_size = SNPS_PER_CHUNK
    for start in range(0, nsnps, chunk_size):
        stop = start + chunk_size
        if stop > nsnps:
            stop = nsnps
        yield matrix[start:stop]


def calc_min_max(matrix):
    if is_dataset(matrix):
        max_ = None
        min_ = None
        for chunk in iterate_matrix_chunks(matrix):
            chunk_max = numpy.max(chunk)
            chunk_min = numpy.min(chunk)
            if max_ is None or max_ < chunk_max:
                max_ = chunk_max
            if min_ is None or min_ > chunk_min:
                min_ = chunk_min
    else:
        max_ = numpy.max(matrix)
        min_ = numpy.min(matrix)
    return min_, max_