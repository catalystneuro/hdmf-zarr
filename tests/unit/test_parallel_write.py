"""Module for testing the parallel write feature for the ZarrIO."""
import unittest
from pathlib import Path
from typing import Tuple, Dict
from io import StringIO
from unittest.mock import patch

import numpy as np
from numpy.testing import assert_array_equal
from hdmf_zarr import ZarrIO
from hdmf.common import DynamicTable, VectorData, get_manager
from hdmf.data_utils import GenericDataChunkIterator, DataChunkIterator

try:
    import tqdm  # noqa: F401
    TQDM_INSTALLED = True
except ImportError:
    TQDM_INSTALLED = False

class PickleableDataChunkIterator(GenericDataChunkIterator):
    """Generic data chunk iterator used for specific testing purposes."""

    def __init__(self, data, **base_kwargs):
        self.data = data

        self._base_kwargs = base_kwargs
        super().__init__(**base_kwargs)

    def _get_dtype(self) -> np.dtype:
        return self.data.dtype

    def _get_maxshape(self) -> tuple:
        return self.data.shape

    def _get_data(self, selection: Tuple[slice]) -> np.ndarray:
        return self.data[selection]

    def __reduce__(self):
        instance_constructor = self._from_dict
        initialization_args = (self._to_dict(),)
        return (instance_constructor, initialization_args)

    def _to_dict(self) -> Dict:
        dictionary = dict()
        # Note this is not a recommended way to pickle contents
        # ~~ Used for testing purposes only ~~
        dictionary["data"] = self.data
        dictionary["base_kwargs"] = self._base_kwargs

        return dictionary

    @staticmethod
    def _from_dict(dictionary: dict) -> GenericDataChunkIterator:  # TODO: need to investigate the need of base path
        data = dictionary["data"]

        iterator = PickleableDataChunkIterator(data=data, **dictionary["base_kwargs"])
        return iterator

class NotPickleableDataChunkIterator(GenericDataChunkIterator):
    """Generic data chunk iterator used for specific testing purposes."""

    def __init__(self, data, **base_kwargs):
        self.data = data

        self._base_kwargs = base_kwargs
        super().__init__(**base_kwargs)

    def _get_dtype(self) -> np.dtype:
        return self.data.dtype

    def _get_maxshape(self) -> tuple:
        return self.data.shape

    def _get_data(self, selection: Tuple[slice]) -> np.ndarray:
        return self.data[selection]
    
def test_parallel_write(tmpdir):
    number_of_jobs = 2
    data = np.array([1., 2., 3.])
    column = VectorData(name="TestColumn", description="", data=PickleableDataChunkIterator(data=data))
    dynamic_table = DynamicTable(name="TestTable", description="", columns=[column])

    zarr_top_level_path = str(tmpdir / "test_parallel_write.zarr")
    with ZarrIO(path=zarr_top_level_path,  manager=get_manager(), mode="w") as io:
        io.write(dynamic_table, number_of_jobs=number_of_jobs)

    # TODO: roundtrip currently fails due to read error
    #with ZarrIO(path=zarr_top_level_path, mode="r") as io:
    #    dynamic_table_roundtrip = io.read()
    #    data_roundtrip = dynamic_table_roundtrip["TestColumn"].data
    #    assert_array_equal(data_roundtrip, data)
        
        
def test_mixed_iterator_types(tmpdir):
    number_of_jobs = 2
    generic_column = VectorData(name="TestGenericColumn", description="", data=PickleableDataChunkIterator(data=np.array([1., 2., 3.])))
    classic_column = VectorData(name="TestClassicColumn", description="", data=DataChunkIterator(data=np.array([4., 5., 6.])))
    unwrapped_column = VectorData(name="TestUnwrappedColumn", description="", data=np.array([7., 8., 9.]))
    dynamic_table = DynamicTable(name="TestTable", description="", columns=[generic_column, classic_column, unwrapped_column])

    zarr_top_level_path = str(tmpdir / "test_mixed_iterator_types.zarr")
    with ZarrIO(path=zarr_top_level_path,  manager=get_manager(), mode="w") as io:
        io.write(dynamic_table, number_of_jobs=number_of_jobs)
        
    # TODO: roundtrip currently fails 
    #with ZarrIO(path=zarr_top_level_path, mode="r") as io:
    #    dynamic_table_roundtrip = io.read()
    #    data_roundtrip = dynamic_table_roundtrip["TestColumn"].data
    #    assert_array_equal(data_roundtrip, data)

def test_mixed_iterator_pickleability(tmpdir):
    number_of_jobs = 2
    pickleable_column = VectorData(name="TestGenericColumn", description="", data=PickleableDataChunkIterator(data=np.array([1., 2., 3.])))
    not_pickleable_column = VectorData(name="TestClassicColumn", description="", data=NotPickleableDataChunkIterator(data=np.array([4., 5., 6.])))
    dynamic_table = DynamicTable(name="TestTable", description="", columns=[pickleable_column, not_pickleable_column])

    zarr_top_level_path = str(tmpdir / "test_mixed_iterator_pickleability.zarr")
    with ZarrIO(path=zarr_top_level_path,  manager=get_manager(), mode="w") as io:
        io.write(dynamic_table, number_of_jobs=number_of_jobs)

    # TODO: roundtrip currently fails due to read error
    #with ZarrIO(path=zarr_top_level_path, mode="r") as io:
    #    dynamic_table_roundtrip = io.read()
    #    data_roundtrip = dynamic_table_roundtrip["TestColumn"].data
    #    assert_array_equal(data_roundtrip, data)


@unittest.skipIf(not TQDM_INSTALLED, "optional tqdm module is not installed")
def test_simple_tqdm(tmpdir):
    number_of_jobs = 2
    expected_desc = f"Writing Zarr datasets with {number_of_jobs} jobs"

    zarr_top_level_path = str(tmpdir / "test_simple_tqdm.zarr")
    with patch("sys.stderr", new=StringIO()) as tqdm_out, ZarrIO(path=zarr_top_level_path,  manager=get_manager(), mode="w") as io:
        column = VectorData(
            name="TestColumn",
            description="",
            data=PickleableDataChunkIterator(
                data=np.array([1., 2., 3.]),
                display_progress=True,
                #progress_bar_options=dict(file=tqdm_out),
            )
        )
        dynamic_table = DynamicTable(name="TestTable", description="", columns=[column])
        io.write(dynamic_table, number_of_jobs=number_of_jobs)

    assert expected_desc in tqdm_out.getvalue()


@unittest.skipIf(not TQDM_INSTALLED, "optional tqdm module is not installed")
def test_compound_tqdm(tmpdir):
    number_of_jobs = 2
    expected_desc_pickleable = f"Writing Zarr datasets with {number_of_jobs} jobs"
    expected_desc_not_pickleable = "Writing non-parallel dataset..."

    zarr_top_level_path = str(tmpdir / "test_compound_tqdm.zarr")
    with patch("sys.stderr", new=StringIO()) as tqdm_out, ZarrIO(path=zarr_top_level_path,  manager=get_manager(), mode="w") as io:
        pickleable_column = VectorData(
            name="TestGenericColumn",
            description="",
            data=PickleableDataChunkIterator(
                data=np.array([1., 2., 3.]),
                display_progress=True,
            )
        )
        not_pickleable_column = VectorData(
            name="TestClassicColumn",
            description="",
            data=NotPickleableDataChunkIterator(
                data=np.array([4., 5., 6.]),
                display_progress=True,
                progress_bar_options=dict(desc=expected_desc_not_pickleable, position=1)
            )
        )
        dynamic_table = DynamicTable(name="TestTable", description="", columns=[pickleable_column, not_pickleable_column])
        io.write(dynamic_table, number_of_jobs=number_of_jobs)

    tqdm_out_value = tqdm_out.getvalue()
    assert expected_desc_pickleable in tqdm_out_value
    assert expected_desc_not_pickleable in tqdm_out_value


def test_extra_args(tmpdir):
    pass # TODO? Should we test if the other arguments like thread count can be passed?
    # I mean, anything _can_ be passed due to dynamic **kwargs, but how to test if it was actually used? Seems difficult...
