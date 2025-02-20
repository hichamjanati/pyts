"""Code for Dynamic Time Warping and its variants."""

import numpy as np
from math import ceil, log2, sqrt
from numba import njit, prange
from sklearn.utils import check_array


@njit()
def _square(x, y):
    return (x - y) ** 2


@njit()
def _absolute(x, y):
    return abs(x - y)


@njit()
def _cost_matrix_region(x, y, dist, region):
    n_timestamps = x.size
    cost_mat = np.full((n_timestamps, n_timestamps), np.inf)
    for j in prange(n_timestamps):
        for i in prange(region[0, j], region[1, j]):
            cost_mat[i, j] = dist(x[i], y[j])
    return cost_mat


@njit()
def _cost_matrix_no_region(x, y, dist):
    n_timestamps = x.size
    cost_mat = np.empty((n_timestamps, n_timestamps))
    for j in prange(n_timestamps):
        for i in prange(n_timestamps):
            cost_mat[i, j] = dist(x[i], y[j])
    return cost_mat


def _check_input_dtw(x, y):
    x = check_array(x, ensure_2d=False, dtype='float64')
    y = check_array(y, ensure_2d=False, dtype='float64')
    if x.ndim != 1:
        raise ValueError("'x' must be a one-dimensional array.")
    if y.ndim != 1:
        raise ValueError("'y' must be a one-dimensional array.")
    if x.shape != y.shape:
        raise ValueError("'x' and 'y' must have the same shape.")
    return x, y, x.size


def cost_matrix(x, y, dist='square', region=None):
    """Compute the cost matrix between two samples.

    Parameters
    ----------
    x : array-like, shape = (n_timestamps,)
        First sample.

    y : array-like, shape = (n_timestamps,)
        Second sample.

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

    region : None or array-like, shape = (2, n_timestamps) (default = None)
        Constraint region. If None, there is no contraint region.
        If array-like, the first row indicates the starting indices (included)
        and the second row the ending indices (excluded) of the valid rows
        for each column.

    Returns
    -------
    cost_matrix : array, shape = (n_timestamps, n_timestamps)
        Cost matrix.

    """
    x, y, _ = _check_input_dtw(x, y)
    if dist == 'square':
        dist_ = _square
    elif dist == 'absolute':
        dist_ = _absolute
    elif isinstance(dist, str):
        raise ValueError("'dist' must be either 'square', 'absolute' or "
                         "callable (got {0}).".format(dist))
    else:
        try:
            temp = dist(1, 1)
        except:
            raise ValueError("Calling dist(1, 1) did not work.")
        else:
            if not isinstance(temp, (int, float)):
                raise ValueError("Calling dist(1, 1) did not return a float "
                                 "or an integer.")
        dist_ = dist
    if region is not None:
        region = check_array(region)
        region_shape = region.shape
        if region_shape != (2, x.size):
            raise ValueError(
                "The shape of 'region' must be equal to (2, n_timestamps) "
                "(got {0}).".format(region_shape)
            )
    if region is None:
        cost_mat = _cost_matrix_no_region(x, y, dist_)
    else:
        cost_mat = _cost_matrix_region(x, y, dist_, region)
    return cost_mat


@njit()
def _accumulated_cost_matrix_region(cost_matrix, region):
    n_timestamps = cost_matrix.shape[0]
    acc_cost_mat = np.ones((n_timestamps, n_timestamps)) * np.inf
    acc_cost_mat[0, 0: region[1, 0]] = np.cumsum(
        cost_matrix[0, 0: region[1, 0]]
    )
    acc_cost_mat[0: region[1, 0], 0] = np.cumsum(
        cost_matrix[0: region[1, 0], 0]
    )
    for j in range(1, n_timestamps):
        for i in range(region[0, j], region[1, j]):
            acc_cost_mat[i, j] = cost_matrix[i, j] + min(
                acc_cost_mat[i - 1][j - 1],
                acc_cost_mat[i - 1][j],
                acc_cost_mat[i][j - 1]
            )
    return acc_cost_mat


@njit()
def _accumulated_cost_matrix_no_region(cost_matrix):
    n_timestamps = cost_matrix.shape[0]
    acc_cost_mat = np.empty((n_timestamps, n_timestamps))
    acc_cost_mat[0] = np.cumsum(cost_matrix[0])
    acc_cost_mat[:, 0] = np.cumsum(cost_matrix[:, 0])
    for j in range(1, n_timestamps):
        for i in range(1, n_timestamps):
            acc_cost_mat[i, j] = cost_matrix[i, j] + min(
                acc_cost_mat[i - 1][j - 1],
                acc_cost_mat[i - 1][j],
                acc_cost_mat[i][j - 1]
            )
    return acc_cost_mat


def accumulated_cost_matrix(cost_mat, region=None):
    """Compute the accumulated cost matrix.

    Parameters
    ----------
    cost_mat : array-like, shape = (n_timestamps, n_timestamps)
        Cost matrix.

    region : None or array-like, shape = (2, n_timestamps) (default = None)
        Constraint region. If None, there is no contraint region.
        If array-like, the first row indicates the starting indices (included)
        and the second row the ending indices (excluded) of the valid rows
        for each column.

    Returns
    -------
    acc_cost_mat : array, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix.

    """
    cost_mat = check_array(
        cost_mat, ensure_min_samples=2, ensure_min_features=2,
        force_all_finite=False, dtype='float64'
    )
    cost_mat_shape = cost_mat.shape
    if cost_mat_shape[0] != cost_mat_shape[1]:
        raise ValueError("'cost_mat' must be a square matrix.")
    if region is None:
        acc_cost_mat = _accumulated_cost_matrix_no_region(cost_mat)
    else:
        region = check_array(region, dtype='int64')
        region_shape = region.shape
        if region_shape != (2, cost_mat_shape[0]):
            raise ValueError("The shape of 'region' must be equal to "
                             "(2, n_timestamps) (got {0})".format(region_shape)
                             )
        acc_cost_mat = _accumulated_cost_matrix_region(cost_mat, region)
    return acc_cost_mat


@njit()
def _return_path(acc_cost_mat):
    n_timestamps = acc_cost_mat.shape[0]
    path = [(n_timestamps - 1, n_timestamps - 1)]
    while path[-1] != (0, 0):
        i, j = path[-1]
        if i == 0:
            path.append((0, j - 1))
        elif j == 0:
            path.append((i - 1, 0))
        else:
            arr = np.array([acc_cost_mat[i - 1][j - 1],
                            acc_cost_mat[i - 1][j],
                            acc_cost_mat[i][j - 1]])
            argmin = np.argmin(arr)
            if argmin == 0:
                path.append((i - 1, j - 1))
            elif argmin == 1:
                path.append((i - 1, j))
            else:
                path.append((i, j - 1))
    return np.transpose(np.array(path)[::-1])


def _return_results(dtw_dist, cost_mat, acc_cost_mat,
                    return_cost=False, return_accumulated=False,
                    return_path=False):
    """Return the results according to the parameters."""
    res = (dtw_dist, )
    if return_cost:
        res += (cost_mat, )
    if return_accumulated:
        res += (acc_cost_mat, )
    if return_path:
        path = _return_path(acc_cost_mat)
        res += (path, )
    if len(res) == 1:
        return res[0]
    else:
        return res


def dtw_classic(x, y, dist='square', return_cost=False,
                return_accumulated=False, return_path=False):
    """Classic Dynamic Time Warping (DTW) distance between two samples.

    Parameters
    ----------
    x : array-like, shape = (n_timestamps,)
        First array.

    y : array-like, shape = (n_timestamps,)
        Second array

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

    return_cost : bool (default = False)
        If True, the cost matrix is returned.

    return_accumulated : bool (default = False)
        If True, the accumulated cost matrix is returned.

    return_path : bool (default = False)
        If True, the optimal path is returned.

    Returns
    -------
    dtw_dist : float
        The DTW distance between the two arrays.

    cost_mat : array, shape = (n_timestamps, n_timestamps)
        Cost matrix. Only returned if ``return_cost=True``.

    acc_cost_mat : array, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix. Only returned if ``return_accumulated=True``.

    path : array, shape = (2, path_length)
        The optimal path along the cost matrix. The first row consists
        of the indices of the optimal path for x while the second row
        consists of the indices of the optimal path for y. Only returned
        if ``return_path=True``.

    Examples
    --------
    >>> from pyts.metrics import dtw_classic
    >>> x = [0, 1, 1]
    >>> y = [2, 0, 1]
    >>> dtw_classic(x, y)
    2.0

    """
    x, y, n_timestamps = _check_input_dtw(x, y)

    cost_mat = cost_matrix(x, y, dist=dist, region=None)
    acc_cost_mat = accumulated_cost_matrix(cost_mat)
    dtw_dist = acc_cost_mat[-1, -1]
    if dist == 'square':
        dtw_dist = sqrt(dtw_dist)

    res = _return_results(dtw_dist, cost_mat, acc_cost_mat,
                          return_cost, return_accumulated, return_path)
    return res


def dtw_region(x, y, dist='square', region=None, return_cost=False,
               return_accumulated=False, return_path=False):
    """Dynamic Time Warping (DTW) distance with a constraint region.

    Parameters
    ----------
    x : array-like, shape = (n_timestamps,)
        First array.

    y : array-like, shape = (n_timestamps,)
        Second array

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

     region : None or array-like, shape = (2, n_timestamps)
         Constraint region. If None, no constraint region is used. Otherwise,
         the first row consists of the starting indices (included) and the
         second row consists of the ending indices (excluded) of the valid rows
         for each column.

    return_cost : bool (default = False)
        If True, the cost matrix is returned.

    return_accumulated : bool (default = False)
        If True, the accumulated cost matrix is returned.

    return_path : bool (default = False)
        If True, the optimal path is returned.

    Returns
    -------
    dtw_dist : float
        The DTW distance between the two arrays.

    cost_mat : array, shape = (n_timestamps, n_timestamps)
        Cost matrix. Only returned if ``return_cost=True``.

    acc_cost_mat : array, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix. Only returned if ``return_accumulated=True``.

    path : array, shape = (2, path_length)
        The optimal path along the cost matrix. The first row consists
        of the indices of the optimal path for x while the second row
        consists of the indices of the optimal path for y. Only returned
        if ``return_path=True``.

    Examples
    --------
    >>> from pyts.metrics import dtw_region
    >>> x = [0, 1, 1]
    >>> y = [2, 0, 1]
    >>> region = [[0, 1, 1], [2, 2, 3]]
    >>> dtw_region(x, y, region=region)
    2.23...

    """
    x, y, n_timestamps = _check_input_dtw(x, y)

    if region is not None:
        region = check_array(region, dtype='int64')
        if region.shape != (2, n_timestamps):
            raise ValueError("If 'region' is not None, it must be array-like "
                             "with shape (2, n_timestamps).")

    cost_mat = cost_matrix(x, y, dist=dist, region=region)
    acc_cost_mat = accumulated_cost_matrix(cost_mat)
    dtw_dist = acc_cost_mat[-1, -1]
    if dist == 'square':
        dtw_dist = sqrt(dtw_dist)

    res = _return_results(dtw_dist, cost_mat, acc_cost_mat,
                          return_cost, return_accumulated, return_path)
    return res


def sakoe_chiba_band(n_timestamps, window_size=0.1):
    """Compute the Sakoe-Chiba band.

    Parameters
    ----------
    n_timestamps : int
        The size of both time series.

    window_size : int or float (default = 0.1)
        The window above and below the diagonale. If float, it must be between
        0 and 1, and the actual window size will be computed as
        ``ceil(window_size * (n_timestamps - 1))``. Each cell whose distance
        with the diagonale is lower than or equal to 'window_size' becomes a
        valid cell for the path.

    Returns
    -------
    region : array, shape = (2, n_timestamps)
        Constraint region. The first row consists of the starting indices
        (included) and the second row consists of the ending indices (excluded)
        of the valid rows for each column.

    Examples
    --------
    >>> from pyts.metrics import sakoe_chiba_band
    >>> print(sakoe_chiba_band(5, window_size=2))
    [[0 0 0 1 2]
     [3 4 5 5 5]]

    """
    if not isinstance(n_timestamps, (int, np.integer)):
        raise TypeError("'n_timestamps' must be an intger.")
    else:
        if not n_timestamps >= 2:
            raise ValueError("'n_timestamps' must be an integer greater than "
                             "or equal to 2.")
    if not isinstance(window_size, (int, np.integer, float, np.floating)):
        raise TypeError("'window_size' must be an integer or a float.")
    if isinstance(window_size, (int, np.integer)):
        if not 0 <= window_size <= (n_timestamps - 1):
            raise ValueError(
                "If 'window_size' is an integer, it must be greater "
                "than or equal to 0 and lower than 'n_timestamps'."
            )
        window_size_ = window_size
    elif isinstance(window_size, (float, np.floating)):
        if not 0. <= window_size <= 1.:
            raise ValueError("If 'window_size' is a float, it must be between "
                             "0 and 1.")
        window_size_ = ceil(window_size * (n_timestamps - 1))

    region = np.array([np.arange(n_timestamps) for _ in range(2)])
    region += np.array([- window_size_, window_size_ + 1]).reshape(2, 1)
    region = np.clip(region, 0, n_timestamps)
    return region


def dtw_sakoechiba(x, y, dist='square', window_size=0.1, return_cost=False,
                   return_accumulated=False, return_path=False):
    """Dynamic Time Warping (DTW) distance with Sakoe-Chiba band constraint.

    Parameters
    ----------
    x : array-like, shape = (n_timestamps,)
        First array.

    y : array-like, shape = (n_timestamps,)
        Second array

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

    window_size : int or float (default = 0.1)
        The window above and below the diagonale. If float, it must be between
        0 and 1, and the actual window size will be computed as
        ``int(window_size * (n_timestamps - 1))``. Each cell whose distance
        with the diagonale is lower than or equal to 'window_size' becomes a
        valid cell for the path.

    return_cost : bool (default = False)
        If True, the cost matrix is returned.

    return_accumulated : bool (default = False)
        If True, the accumulated cost matrix is returned.

    return_path : bool (default = False)
        If True, the optimal path is returned.

    Returns
    -------
    dtw_dist : float
        The DTW distance between the two arrays.

    cost_mat : array, shape = (n_timestamps, n_timestamps)
        Cost matrix. Only returned if ``return_cost=True``.

    acc_cost_mat : array, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix. Only returned if ``return_accumulated=True``.

    path : array, shape = (2, path_length)
        The optimal path along the cost matrix. The first row consists
        of the indices of the optimal path for x while the second row
        consists of the indices of the optimal path for y. Only returned
        if ``return_path=True``.

    Examples
    --------
    >>> from pyts.metrics import dtw_sakoechiba
    >>> x = [0, 1, 1]
    >>> y = [2, 0, 1]
    >>> dtw_sakoechiba(x, y, window_size=1)
    2.0

    """
    x, y, n_timestamps = _check_input_dtw(x, y)

    region = sakoe_chiba_band(n_timestamps, window_size)
    cost_mat = cost_matrix(x, y, dist=dist, region=region)
    acc_cost_mat = accumulated_cost_matrix(cost_mat)
    dtw_dist = acc_cost_mat[-1, -1]
    if dist == 'square':
        dtw_dist = sqrt(dtw_dist)

    res = _return_results(dtw_dist, cost_mat, acc_cost_mat,
                          return_cost, return_accumulated, return_path)
    return res


def itakura_parallelogram(n_timestamps, max_slope=2.):
    """Compute the Itakura parallelogram.

    Parameters
    ----------
    n_timestamps : int
        The size of both time series.

    max_slope : float (default = 2.)
        Maximum slope for the parallelogram.

    Returns
    -------
    region : array, shape = (2, n_timestamps)
        Constraint region. The first row consists of the starting indices
        (included) and the second row consists of the ending indices (excluded)
        of the valid rows for each column.

    Examples
    --------
    >>> from pyts.metrics import itakura_parallelogram
    >>> print(itakura_parallelogram(5))
    [[0 1 1 2 4]
     [1 3 4 4 5]]

    """
    if not isinstance(n_timestamps, (int, np.integer)):
        raise TypeError("'n_timestamps' must be an intger.")
    else:
        if not n_timestamps >= 2:
            raise ValueError("'n_timestamps' must be an integer greater than "
                             "or equal to 2.")
    if not isinstance(max_slope, (int, np.integer, float, np.floating)):
        raise TypeError("'max_slope' must be an integer or a float.")
    else:
        if not max_slope >= 1:
            raise ValueError("'max_slope' must be a number greater "
                             "than or equal to 1.")

    min_slope = 1 / max_slope

    lower_bound = np.empty((2, n_timestamps))
    lower_bound[0] = min_slope * np.arange(n_timestamps)
    lower_bound[1] = ((1 - max_slope) * (n_timestamps - 1)
                      + max_slope * np.arange(n_timestamps))
    lower_bound = np.round(lower_bound, 2)
    lower_bound = np.ceil(np.max(lower_bound, axis=0))

    upper_bound = np.empty((2, n_timestamps))
    upper_bound[0] = max_slope * np.arange(n_timestamps)
    upper_bound[1] = ((1 - min_slope) * (n_timestamps - 1)
                      + min_slope * np.arange(n_timestamps))
    upper_bound = np.round(upper_bound, 2)
    upper_bound = np.floor(np.min(upper_bound, axis=0) + 1)

    region = np.asarray([lower_bound, upper_bound]).astype('int64')
    return region


def dtw_itakura(x, y, dist='square', max_slope=2., return_cost=False,
                return_accumulated=False, return_path=False):
    """Dynamic Time Warping distance with Itakura parallelogram constraint.

    Parameters
    ----------
    x : array-like, shape (n_timestamps,)
        First array.

    y : array-like, shape (n_timestamps,)
        Second array

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

    max_slope : float (default = 2.)
        Maximum slope for the parallelogram.

    return_cost : bool (default = False)
        If True, the cost matrix is returned.

    return_accumulated : bool (default = False)
        If True, the accumulated cost matrix is returned.

    return_path : bool (default = False)
        If True, the optimal path is returned.

    Returns
    -------
    dtw_dist : float
        The DTW distance between the two arrays.

    cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Cost matrix. Only returned if ``return_cost=True``.

    acc_cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix. Only returned if ``return_accumulated=True``.

    path : array, shape = (2, path_length)
        The optimal path along the cost matrix. The first row consists
        of the indices of the optimal path for x while the second row
        consists of the indices of the optimal path for y. Only returned
        if ``return_path=True``.

    Examples
    --------
    >>> from pyts.metrics import dtw_itakura
    >>> x = [0, 1, 1]
    >>> y = [2, 0, 1]
    >>> dtw_itakura(x, y, max_slope=1.5)
    2.23...

    """
    x, y, n_timestamps = _check_input_dtw(x, y)

    region = itakura_parallelogram(n_timestamps, max_slope)
    cost_mat = cost_matrix(x, y, dist=dist, region=region)
    acc_cost_mat = accumulated_cost_matrix(cost_mat)
    dtw_dist = acc_cost_mat[-1, -1]
    if dist == 'square':
        dtw_dist = sqrt(dtw_dist)

    res = _return_results(dtw_dist, cost_mat, acc_cost_mat,
                          return_cost, return_accumulated, return_path)
    return res


def _multiscale_region(n_timestamps, resolution_level, n_timestamps_reduced,
                       path, radius):
    path_length = path.shape[1]
    path_up = np.repeat(path, radius, axis=1)
    path_down = path_up.copy()
    path_left = path_up.copy()
    path_right = path_up.copy()

    for i in range(1, radius + 1):
        start = path_length * (i - 1)
        end = path_length * i
        path_up[0, start: end] += i
        path_down[0, start: end] -= i
        path_left[1, start: end] -= i
        path_right[1, start: end] += i

    path_radius = np.clip(
        np.c_[path, path_up, path_down, path_left, path_right],
        0, n_timestamps_reduced - 1
    )

    region_reduced = np.empty((2, n_timestamps_reduced))
    for i in range(n_timestamps_reduced):
        arr = path_radius[1, path_radius[0] == i]
        min_, max_ = np.min(arr), np.max(arr)
        region_reduced[0, i] = min_ * resolution_level
        region_reduced[1, i] = (max_ + 1) * resolution_level

    region = np.repeat(region_reduced, resolution_level, axis=1)
    region = np.clip(region[:, :n_timestamps], 0, n_timestamps)

    return region.astype('int64')


def dtw_multiscale(x, y, dist='square', resolution=2, radius=0,
                   return_cost=False, return_accumulated=False,
                   return_path=False):
    """Multiscale Dynamic Time Warping distance.

    Parameters
    ----------
    x : array-like, shape = (n_timestamps,)
        First array.

    y : array-like, shape = (n_timestamps,)
        Second array

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

    resolution : int (default = 2)
        The resolution level.

    radius : int (default = 0)
        The radius used to expand the constraint region. The optimal path
        computed at the resolution level is expanded with `radius` cells to the
        top, bottom, left and right of every cell belonging to the optimal
        path. It is computed at the resolution level.

    return_cost : bool (default = False)
        If True, the cost matrix is returned.

    return_accumulated : bool (default = False)
        If True, the accumulated cost matrix is returned.

    return_path : bool (default = False)
        If True, the optimal path is returned.

    Returns
    -------
    dtw_dist : float
        The DTW distance between the two arrays.

    cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Cost matrix. Only returned if ``return_cost=True``.

    acc_cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix. Only returned if ``return_accumulated=True``.

    path : array, shape = (2, path_length)
        The optimal path along the cost matrix. The first row consists
        of the indices of the optimal path for x while the second row
        consists of the indices of the optimal path for y. Only returned
        if ``return_path=True``.

    Examples
    --------
    >>> from pyts.metrics import dtw_multiscale
    >>> x = [0, 1, 1]
    >>> y = [2, 0, 1]
    >>> dtw_multiscale(x, y, resolution=2)
    2.23...

    """
    x, y, n_timestamps = _check_input_dtw(x, y)
    if not isinstance(resolution, (int, np.integer)):
        raise TypeError("'resolution' must be an integer.")
    if resolution < 1:
        raise ValueError("'resolution' must be a positive integer.")
    if not isinstance(radius, (int, np.integer)):
        raise TypeError("'radius' must be an integer.")
    if radius < 0:
        raise ValueError("'radius' must be a non-negative integer.")

    if resolution == 1:
        region = None
    else:
        remainder = n_timestamps % resolution
        if remainder != 0:
            x_padded = np.append(x, np.repeat(x[-1], resolution - remainder))
            y_padded = np.append(y, np.repeat(y[-1], resolution - remainder))
            x_padded = x_padded.reshape(-1, resolution).mean(axis=1)
            y_padded = y_padded.reshape(-1, resolution).mean(axis=1)
        else:
            x_padded = x.reshape(-1, resolution).mean(axis=1)
            y_padded = y.reshape(-1, resolution).mean(axis=1)

        cost_mat_res = cost_matrix(x_padded, y_padded, dist=dist, region=None)
        acc_cost_mat_res = accumulated_cost_matrix(cost_mat_res)
        path_res = _return_path(acc_cost_mat_res)
        region = _multiscale_region(n_timestamps, resolution,
                                    x_padded.size, path_res, radius)

    cost_mat = cost_matrix(x, y, dist=dist, region=region)
    acc_cost_mat = accumulated_cost_matrix(cost_mat)
    dtw_dist = acc_cost_mat[-1, -1]
    if dist == 'square':
        dtw_dist = sqrt(dtw_dist)

    res = _return_results(dtw_dist, cost_mat, acc_cost_mat,
                          return_cost, return_accumulated, return_path)
    return res


def dtw_fast(x, y, dist='square', radius=0, return_cost=False,
             return_accumulated=False, return_path=False):
    """Fast Dynamic Time Warping distance.

    Parameters
    ----------
    x : array-like, shape = (n_timestamps,)
        First array.

    y : array-like, shape = (n_timestamps,)
        Second array

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

    radius : int (default = 0)
        The radius used to expand the constraint region. The optimal path
        computed at the resolution level is expanded with `radius` cells to the
        top, bottom, left and right of every cell belonging to the optimal
        path. It is computed at the resolution level.

    return_cost : bool (default = False)
        If True, the cost matrix is returned.

    return_accumulated : bool (default = False)
        If True, the accumulated cost matrix is returned.

    return_path : bool (default = False)
        If True, the optimal path is returned.

    Returns
    -------
    dtw_dist : float
        The DTW distance between the two arrays.

    cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Cost matrix. Only returned if ``return_cost=True``.

    acc_cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix. Only returned if ``return_accumulated=True``.

    path : ndarray, shape = (2, path_length)
        The optimal path along the cost matrix. The first row consists
        of the indices of the optimal path for x while the second row
        consists of the indices of the optimal path for y. Only returned
        if ``return_path=True``.

    Examples
    --------
    >>> from pyts.metrics import dtw_fast
    >>> x = [0, 1, 1]
    >>> y = [2, 0, 1]
    >>> dtw_multiscale(x, y, resolution=2, radius=1)
    2.0

    """
    x, y, n_timestamps = _check_input_dtw(x, y)
    if not isinstance(radius, (int, np.integer)):
        raise TypeError("'radius' must be an integer.")
    if radius < 0:
        raise ValueError("'radius' must be a non-negative integer.")

    min_size = radius + 2
    region = None
    if n_timestamps > min_size:
        n_recursions = ceil(log2(n_timestamps / min_size))
        for i in range(n_recursions):
            resolution = 2 ** (n_recursions - i)
            remainder = n_timestamps % resolution
            if remainder != 0:
                x_padded = np.append(
                    x, np.repeat(x[-1], resolution - remainder)
                )
                y_padded = np.append(
                    y, np.repeat(y[-1], resolution - remainder)
                )
                x_padded = x_padded.reshape(-1, resolution).mean(axis=1)
                y_padded = y_padded.reshape(-1, resolution).mean(axis=1)
            else:
                x_padded = x.reshape(-1, resolution).mean(axis=1)
                y_padded = y.reshape(-1, resolution).mean(axis=1)

            cost_mat_res = cost_matrix(x_padded, y_padded,
                                       dist=dist, region=region)
            acc_cost_mat_res = accumulated_cost_matrix(cost_mat_res)
            path_res = _return_path(acc_cost_mat_res)
            n_timestamps_next = ceil((2 * n_timestamps) / resolution)
            region = _multiscale_region(n_timestamps_next, 2, x_padded.size,
                                        path_res, radius)

    cost_mat = cost_matrix(x, y, dist=dist, region=region)
    acc_cost_mat = accumulated_cost_matrix(cost_mat)
    dtw_dist = acc_cost_mat[-1, -1]
    if dist == 'square':
        dtw_dist = sqrt(dtw_dist)

    res = _return_results(dtw_dist, cost_mat, acc_cost_mat,
                          return_cost, return_accumulated, return_path)
    return res


def dtw(x, y, dist='square', method='classic', options=None, return_cost=False,
        return_accumulated=False, return_path=False):
    """Dynamic Time Warping (DTW) distance between two samples.

    Parameters
    ----------
    x : array-like, shape = (n_timestamps,)
        First array.

    y : array-like, shape = (n_timestamps,)
        Second array

    dist : 'square', 'absolute' or callable (default = 'square')
        Distance used. If 'square', the squared difference is used.
        If 'absolute', the absolute difference is used. If callable,
        it must be a function with a numba.njit() decorator that takes
        as input two numbers (two arguments) and returns a number.

    method : str (default = 'classic')
        Method used.  Should be one of

            - 'classic': Classic DTW
            - 'sakoechiba': DTW with Sakoe-Chiba band constraint
            - 'itakura': DTW with Itakura parallelogram constraint
            - 'multiscale': MultiscaleDTW
            - 'fast': FastDTW

    options : None or dict (default = None)
        Dictionary of method options

            - 'classic': None
            - 'sakoechiba': window_size (int or float)
            - 'itakura': max_slope (float)
            - 'multiscale': resolution (int) and radius (int)
            - 'fast': radius (int)

    return_cost : bool (default = False)
        If True, the cost matrix is returned.

    return_accumulated : bool (default = False)
        If True, the accumulated cost matrix is returned.

    return_path : bool (default = False)
        If True, the optimal path is returned.

    Returns
    -------
    dist : float
        The DTW distance between the two arrays.

    cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Cost matrix. Only returned if ``return_cost=True``.

    acc_cost_mat : ndarray, shape = (n_timestamps, n_timestamps)
        Accumulated cost matrix. Only returned if ``return_accumulated=True``.

    path : ndarray, shape = (2, path_length)
        The optimal path along the cost matrix. The first row consists
        of the indices of the optimal path for x while the second row
        consists of the indices of the optimal path for y. Only returned
        if ``return_path=True``.

    Examples
    --------
    >>> from pyts.metrics import dtw
    >>> x = [0, 1, 1]
    >>> y = [2, 0, 1]
    >>> dtw(x, y, method='sakoechiba', options={'window_size': 2})
    2.0

    """
    if options is None:
        options = dict()

    if method == 'classic':
        return dtw_classic(x, y, dist=dist, return_cost=return_cost,
                           return_accumulated=return_accumulated,
                           return_path=return_path)
    elif method == 'sakoechiba':
        return dtw_sakoechiba(x, y, dist=dist, return_cost=return_cost,
                              return_accumulated=return_accumulated,
                              return_path=return_path, **options)
    elif method == 'itakura':
        return dtw_itakura(x, y, dist=dist, return_cost=return_cost,
                           return_accumulated=return_accumulated,
                           return_path=return_path, **options)
    elif method == 'multiscale':
        return dtw_multiscale(x, y, dist=dist, return_cost=return_cost,
                              return_accumulated=return_accumulated,
                              return_path=return_path, **options)
    elif method == 'fast':
        return dtw_fast(x, y, dist=dist, return_cost=return_cost,
                        return_accumulated=return_accumulated,
                        return_path=return_path, **options)
    else:
        raise ValueError("'method' must be either 'classic', 'sakoechiba', "
                         "'itakura', 'multiscale' or 'fast'.")


def show_options(method=None, disp=True):
    """Show documentation for additional options of DTW methods.

    These are method-specific options that can be supplied through the
    ``options`` dict.

    Parameters
    ----------
    method : None or str (default = None)
        If None, shows all methods of the specified solver. Otherwise,
        show only the options for the specified method. If str, it must be
        either 'classic', 'sakoechiba', 'itakura', 'multiscale' or 'fast'.

    disp : bool (default = True)
        Whether to print the result rather than returning it.

    Returns
    -------
    text
        Either None (for disp=True) or the text string (disp=False).

    """
    import textwrap

    text = """\n\n"""
    if method is None:
        text += "classic\n=======\n\n" + dtw_classic.__doc__ + "\n"
        text += "sakoechiba\n==========\n\n" + dtw_sakoechiba.__doc__ + "\n"
        text += "itakura\n=======\n\n" + dtw_itakura.__doc__ + "\n"
        text += "multiscale\n==========\n\n" + dtw_multiscale.__doc__ + "\n"
        text += "fast\n====\n\n" + dtw_fast.__doc__ + "\n"
    elif method == 'classic':
        doc = textwrap.dedent(dtw_classic.__doc__).strip()
        text += doc
    elif method == 'sakoechiba':
        doc = textwrap.dedent(dtw_sakoechiba.__doc__).strip()
        text += doc
    elif method == 'itakura':
        doc = textwrap.dedent(dtw_itakura.__doc__).strip()
        text += doc
    elif method == 'multiscale':
        doc = textwrap.dedent(dtw_multiscale.__doc__).strip()
        text += doc
    elif method == 'fast':
        doc = textwrap.dedent(dtw_fast.__doc__).strip()
        text += doc
    else:
        raise ValueError("'method' must be either None, 'classic', "
                         "'sakoechiba', 'itakura', 'multiscale' or 'fast'.")
    if disp:
        print(text)
        return
    else:
        return text
