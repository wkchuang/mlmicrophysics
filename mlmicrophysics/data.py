import numpy as np
import pandas as pd
import xarray as xr
from glob import glob
from os.path import join, exists


def load_cam_output(path, file_start="TAU_run1.cam.h1", file_end="nc"):
    """
    Load set of model output from CAM/CESM into xarray Dataset object.

    Args:
        path: Path to directory containing model output
        file_start: Shared beginning of model files
        file_end: Filetype shared by all files.

    Returns:
        xarray Dataset object containing the model output
    """
    if not exists(path):
        raise FileNotFoundError("Specified path " + path + " does not exist")
    data_files = sorted(glob(join(path, file_start + "*" + file_end)))
    if len(data_files) > 0:
        cam_dataset = xr.open_mfdataset(data_files, decode_times=False)
    else:
        raise FileNotFoundError("No matching CAM output files found in " + path)
    return cam_dataset


def unstagger_vertical(dataset, variable, vertical_dim="lev"):
    """
    Interpolate a 4D variable on a staggered vertical grid to an unstaggered vertical grid. Will not execute
    until compute() is called on the result of the function.

    Args:
        dataset: xarray Dataset object containing the variable to be interpolated
        variable: Name of the variable being interpolated
        vertical_dim: Name of the vertical coordinate dimension.

    Returns:
        xarray DataArray containing the vertically interpolated data
    """
    var_data = dataset[variable]
    unstaggered_var_data = xr.DataArray(0.5 * (var_data[:, :-1].values + var_data[:, 1:].values),
                                        coords=[var_data.time, dataset[vertical_dim], var_data.lat, var_data.lon],
                                        dims=("time", vertical_dim, "lat", "lon"))
    return unstaggered_var_data


def convert_to_dataframe(dataset, variables, times, time_var="time", subset_variable="QC_TAU_in", subset_threshold=0):
    """
    Convert 4D Dataset to flat dataframe for machine learning.

    Args:
        dataset: xarray Dataset containing all relevant variables and times.
        variables: List of variables in dataset to be included in DataFrame. All variables should have the same
            dimensions and coordinates.
        times: Iterable of times to select from dataset.
        time_var: Variable used as the time coordinate.
        subset_variable: Variable used to select a subset of grid points from file
        subset_threshold: Threshold that must be exceeded for examples to be kept.
    Returns:

    """
    data_frames = []
    for t, time in enumerate(times):
        print(t, time)
        time_df = dataset[variables].sel(**{time_var: time}).to_dataframe()
        data_frames.append(time_df.loc[time_df[subset_variable] > subset_threshold].reset_index())
        print(data_frames[-1])
        del time_df
    return pd.concat(data_frames)


def load_csv_data(csv_path, index_col="Index"):
    """
    Read pre-processed csv files into memory.

    Args:
        csv_path: Path to csv files
        index_col: Column label used as the index

    Returns:
        `pandas.DataFrame` containing data from all csv files in the csv_path directory.
    """
    csv_files = sorted(glob(join(csv_path, "*.csv")))
    all_data = []
    for csv_file in csv_files:
        all_data.append(pd.read_csv(csv_file, index_col=index_col))
    return pd.concat(all_data, axis=0)


def subset_data_by_date(data, train_date_start=0, train_date_end=1, test_date_start=2, test_date_end=3,
                        validation_frequency=3, subset_col="time"):
    """
    Subset temporal data into training, validation, and test sets by the date column.

    Args:
        data: pandas DataFrame containing all data for training, validation, and testing.
        train_date_start: First date included in training period
        train_date_end: Last date included in training period
        test_date_start: First date included in testing period
        test_date_end: Last date included in testing period.
        validation_frequency: How often days are separated from training dataset for validation.
            Should be an integer > 1. 2 is every other day, 3 is every third day, etc.
        subset_col: Name of column being used for date evaluation.

    Returns:
        training_set, validation_set, test_set
    """
    if train_date_start > train_date_end:
        raise ValueError("train_date_start should not be greater than train_date_end")
    if test_date_start > test_date_end:
        raise ValueError("test_date_start should not be greater than test_date_end")
    if train_date_end > test_date_start:
        raise ValueError("train and test date periods overlap.")
    train_indices = (data[subset_col] >= train_date_start) & (data[subset_col] <= train_date_end)
    test_indices = (data[subset_col] >= test_date_start) & (data[subset_col] <= test_date_end)
    train_and_validation_data = data.loc[train_indices]
    test_data = data.loc[test_indices]
    train_and_validation_dates = np.unique(train_and_validation_data[subset_col].values)
    validation_dates = train_and_validation_dates[validation_frequency::validation_frequency]
    train_dates = train_and_validation_dates[np.isin(train_and_validation_dates,
                                                     validation_dates,
                                                     assume_unique=True,
                                                     invert=True)]
    train_data = data.loc[np.isin(data[subset_col].values, train_dates)]
    validation_data = data.loc[np.isin(data[subset_col].values, validation_dates)]
    return train_data, validation_data, test_data