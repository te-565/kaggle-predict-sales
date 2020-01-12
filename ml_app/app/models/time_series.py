import pandas as pd
import numpy as np
from dask import delayed, compute
from fbprophet import Prophet


def create_all_time_series(df, uid, time_index, target, ts_drop_cols):
    """
    Summary
    -------
    Groups a dataframe and generates a time series using Prophet for each uid
    via the create_single_time_series function which is executed via
    groupby / apply and processed in parallel via Dask delayed.

    Only records where the last 6 months sales are greater than 6 and the
    latest month is greater than 0 are processed.

    This outputs a list of dictionary records which is then convered to a
    pandas dataframe and returned.

    Parameters
    ----------
    df: pandas.DataFrame
        The dataframe containing the records to generate a time series for.

    uid: str
        The name of the column containing the unique id

    time_index: str
        The name of the column containing the time index

    target: str
        The name of the column containing the target variable to predict


    Returns
    -------
    df_ts_all: pandas.DataFrame
        A pandas dataframe containing time series data for the relevent records
        of the input dataframe

    Example
    --------
    df_ts_all = create_all_time_series(df, uid, time_index, target)

    """
    df_ts = (
        df[[uid, time_index, target]]
        .rename({
            time_index: 'ds',
            target: 'y'
        }, axis=1)
    )

    df_ts['y'] = df_ts['y'].fillna(0)

    # Group the dataframe by unique id
    df_ts_gp = df_ts.groupby(uid)

    # Create an output list to append results to
    ts_output = []

    # Generate a time series for each appropriate record
    for group in df_ts_gp.groups:
        df_ts = df_ts_gp.get_group(group)
        # if (df_ts['y'].tail(6).sum() > 6) & (df_ts['y'].tail(1).sum() > 1):
        ts_dict = create_single_time_series(df_ts, uid, ts_drop_cols)
        ts_output.append(ts_dict)

    # Compute the time series via dask
    ts_output = compute(ts_output)[0]

    # Create an empty list to iterate the results into
    records_list = []

    # Create a list of records for conversion to a dataframe
    for item in ts_output:
        for record in item:
            records_list.append(record)

    # Convert the output list of records to a dataframe
    df_ts_all = (
        pd.DataFrame(records_list)
        .rename({
            'ds': time_index,
            'y': target
        }, axis=1)
    )

    return df_ts_all


@delayed
def create_single_time_series(df_ts, uid, ts_drop_cols):
    """
    Summary
    -------
    Creates a single monthly time series using Prophet for the supplied
    dataframe and returns the prediction for the next month alongside the
    output from the Prophet predict method.

    Delayed via Dask.

    Parameters
    ----------
    df_ts: pandas.DataFrame
        A group within a dataframe to create a time series for.

    Returns
    -------
    ts_dict: dict
        A dictionary in records format containing the input data alongside the
        output generated by Prophhet.

    Example
    --------
    for group in df_ts_gp.groups:
        df_ts = df_ts_gp.get_group(group)
        if (df_ts['y'].tail(6).sum() > 6) & (df_ts['y'].tail(1).sum() > 1):
            ts_dict = create_single_time_series(df_ts)
            ts_output.append(ts_dict)
    """

    # Get the UID
    uid_value = df_ts[uid].unique().tolist()[0]

    # Create the model
    model = Prophet(
        seasonality_mode='multiplicative',
        weekly_seasonality=False,
        daily_seasonality=False,
        yearly_seasonality=True,
        growth='logistic',
        changepoint_prior_scale=0.5,
    )

    # Add monthly seasonality
    model.add_seasonality(
        name='monthly',
        period=30.5,
        fourier_order=5
    )

    # Add Russian Holidays
    model.add_country_holidays(country_name='Russia')

    # Set the cap and floor
    df_ts['cap'] = (df_ts['y'].max() * 2)
    df_ts['floor'] = 1

    try:
        # Fit the model & set to 2k max iterations
        model.fit(df_ts, iter=2000)

        # Create future dataframe to generate predictions for
        df_future = model.make_future_dataframe(periods=1)
        df_future['cap'] = (df_ts['y'].max() * 2)
        df_future['floor'] = 1

        # Generate predictions
        df_preds = model.predict(df_future)
        df_preds[uid] = uid_value

        df_preds = (
            df_preds.drop(ts_drop_cols, axis=1)
            .to_dict(orient='records')
        )

        return df_preds

    except:
        return []
