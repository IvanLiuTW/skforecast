################################################################################
#                    ForecasterLastEquivalentDate                              #
#                                                                              #
# This work by skforecast team is licensed under the BSD 3-Clause License.     #
################################################################################
# coding=utf-8

from typing import Union, Tuple, Optional, Callable
import warnings
import logging
import sys
import numpy as np
import pandas as pd
from sklearn.base import clone
from copy import copy

import skforecast
from ..utils import check_predict_input
from ..utils import preprocess_y
from ..utils import preprocess_last_window
from ..utils import expand_index

logging.basicConfig(
    format = '%(name)-10s %(levelname)-5s %(message)s', 
    level  = logging.INFO,
)


class ForecasterLastEquivalentDate():
    """
    This forecaster predicts future values based on the most recent observed data
    similar to the target period. This approach is useful as a baseline. However,
    it is a simplistic method and may not capture complex underlying patterns.
    
    Parameters
    ----------
    offset : int, pandas.tseries.offsets.DateOffset
        Number of steps to go back in time to find the most recent data similar
        to the target period.
        If `offset` is an integer, it represents the number of steps to go back
        in time. For example, if the frequency of the time series is 1 day, the
        most recent data similar to the target period is the value observed 7
        days ago (offset = 7).
        Pandas DateOffsets can also be used to define the offset to move dates
        forward a given number of valid dates. For example, Bday(2) can be added
        subtracted to a date to move it two business days backward. If the date
        does not start on a valid date, first it is moved to a valid date. For
        example, if the date is a Saturday, it is moved to the previous Friday.
        Then, the offset is applied. If the result is a non valid date, it is
        moved to the next valid date. For example, if the date is a Sunday, it
        is moved to the next Monday. Find more information about offsets in
        https://pandas.pydata.org/docs/reference/offset_frequency.html.
    forecaster_id : str, int, default `None`
        Name used as an identifier of the forecaster.
    
    Attributes
    ----------
    offset : int, pandas.tseries.offsets.DateOffset
        Number of steps to go back in time to find the most recent data similar
        to the target period.
        If `offset` is an integer, it represents the number of steps to go back
        in time. For example, if the frequency of the time series is 1 day, the
        most recent data similar to the target period is the value observed 7
        days ago (offset = 7).
        Pandas DateOffsets can also be used to define the offset to move dates
        forward a given number of valid dates. For example, Bday(2) can be added
        subtracted to a date to move it two business days backward. If the date
        does not start on a valid date, first it is moved to a valid date. For
        example, if the date is a Saturday, it is moved to the previous Friday.
        Then, the offset is applied. If the result is a non valid date, it is
        moved to the next valid date. For example, if the date is a Sunday, it
        is moved to the next Monday. Find more information about offsets in
        https://pandas.pydata.org/docs/reference/offset_frequency.html.
    n_equivalent_dates : int
        Number of equivalent dates (multiple of offset) used in the prediction.
        For example, if the frequency of the time series is dayly, offset = 7 and
        n_equivalent_dates = 2, the most recent equivalent data used to predict the
        value of the next day is the value observed 7 days ago and 14 days ago.
    agg_func : callable, default `np.mean`
        Function used to aggregate the values of the equivalent dates when the
        number of equivalent dates is greater than 1.
    window_size : int
        Size of the window of past values needed to include last equivalent date
        according to the offset.
    last_window : pandas Series
        This window represents the most recent data observed by the predictor
        during its training phase. It contains the past values needed to include
        the last equivalent date according to the offset.
    index_type : type
        Type of index of the input used in training.
    index_freq : str
        Frequency of Index of the input used in training.
    training_range : pandas Index
        First and last values of index of the data used during training.
    fitted : bool
        Tag to identify if the regressor has been fitted (trained).
    transformer_y : Ignored
            Not used, present here for API consistency by convention.
    transformer_exog : Ignored
            Not used, present here for API consistency by convention.
    weight_func : Ignored
            Not used, present here for API consistency by convention.
    differentiation : Ignored
            Not used, present here for API consistency by convention.
    fit_kwargs : Ignored
            Not used, present here for API consistency by convention.
    creation_date : str
        Date of creation.
    fit_date : str
        Date of last fit.
    skforcast_version : str
        Version of skforecast library used to create the forecaster.
    python_version : str
        Version of python used to create the forecaster.
    forecaster_id : str, int
        Name used as an identifier of the forecaster.
    
    """
    
    def __init__(
        self,
        offset: Union[int, pd.tseries.offsets.DateOffset],
        n_equivalent_dates: int=1,
        agg_func: Callable=np.mean,
        forecaster_id: Optional[Union[str, int]]=None
    ) -> None:
        
        self.offset                  = offset
        self.n_equivalent_dates      = n_equivalent_dates
        self.agg_func                = agg_func
        self.regressor               = None
        self.transformer_y           = None
        self.transformer_exog        = None
        self.weight_func             = None
        self.differentiation         = None
        self.differentiator          = None
        self.source_code_weight_func = None
        self.last_window             = None
        self.index_type              = None
        self.index_freq              = None
        self.training_range          = None
        self.included_exog           = False
        self.exog_type               = None
        self.exog_dtypes             = None
        self.exog_col_names          = None
        self.X_train_col_names       = None
        self.in_sample_residuals     = None
        self.out_sample_residuals    = None
        self.fitted                  = False
        self.creation_date           = pd.Timestamp.today().strftime('%Y-%m-%d %H:%M:%S')
        self.fit_date                = None
        self.skforcast_version       = skforecast.__version__
        self.python_version          = sys.version.split(" ")[0]
        self.forecaster_id           = forecaster_id
       
        if not isinstance(self.offset, (int, pd.tseries.offsets.DateOffset)):
            raise Exception(
                "`offset` must be an integer or a pandas.tseries.offsets. "
                "Find more information about offsets in "
                "https://pandas.pydata.org/docs/reference/offset_frequency.html"
            )
        self.window_size = self.offset * self.n_equivalent_dates
        

    def __repr__(
        self
    ) -> str:
        """
        Information displayed when a Forecaster object is printed.
        """

        info = (
            f"{'=' * len(type(self).__name__)} \n"
            f"{type(self).__name__} \n"
            f"{'=' * len(type(self).__name__)} \n"
            f"Offset: {self.offset} \n"
            f"Number of equivalent dates: {self.n_equivalent_dates} \n"
            f"Aggregation function: {self.agg_func.__name__} \n"
            f"Window size: {self.window_size} \n"
            f"Training range: {self.training_range.to_list() if self.fitted else None} \n"
            f"Training index type: {str(self.index_type).split('.')[-1][:-2] if self.fitted else None} \n"
            f"Training index frequency: {self.index_freq if self.fitted else None} \n"
            f"Creation date: {self.creation_date} \n"
            f"Last fit date: {self.fit_date} \n"
            f"Skforecast version: {self.skforcast_version} \n"
            f"Python version: {self.python_version} \n"
            f"Forecaster id: {self.forecaster_id} \n"
        )

        return info

        
    def fit(
        self,
        y: pd.Series,
        exog=None,
        store_in_sample_residuals=None
    ) -> None:
        """
        Training Forecaster.
        
        Parameters
        ----------
        y : pandas Series
            Training time series.
        exog : Ignored
            Not used, present here for API consistency by convention.
        store_in_sample_residuals : Ignored
            Not used, present here for API consistency by convention.
        Returns
        -------
        None
        
        """

        if isinstance(self.offset, pd.tseries.offsets.DateOffset) and not isinstance(
            y.index, pd.DatetimeIndex
        ):
            raise Exception(
                "If `offset` is a pandas DateOffset, the index of `y` must be a "
                "pandas DatetimeIndex with a frequency."
            )
        
        # Reset values in case the forecaster has already been fitted.
        self.index_type     = None
        self.index_freq     = None
        self.last_window    = None
        self.fitted         = False
        self.training_range = None


        self.fitted = True
        self.fit_date = pd.Timestamp.today().strftime('%Y-%m-%d %H:%M:%S')
        _, y_index = preprocess_y(y=y, return_values=True)
        self.training_range = y_index[[0, -1]]
        self.index_type = type(y_index)
        if isinstance(y_index, pd.DatetimeIndex):
            self.index_freq = y_index.freqstr
        else: 
            self.index_freq = y_index.step

        if isinstance(self.offset, pd.tseries.offsets.DateOffset):
            first_date_window = y_index[-1] - (self.offset * self.n_equivalent_dates)
            self.window_size = len(y.loc[first_date_window:])
        
        # The last time window of training data is stored so that lags needed as
        # predictors in the first iteration of `predict()` can be calculated.
        self.last_window = y.iloc[-self.window_size:].copy()

            
    def predict(
        self,
        steps: int,
        last_window: Optional[pd.Series]=None,
        exog=None
    ) -> pd.Series:
        """
        Predict n steps ahead.
        
        Parameters
        ----------
        steps : int
            Number of future steps predicted.
        last_window : pandas Series, default `None`
            Series values used to create the predictors (lags) needed in the 
            first iteration of the prediction (t + 1).
            If `last_window = None`, the values stored in `self.last_window` are
            used to calculate the initial predictors, and the predictions start
            right after training data.
        exog : Ignored
            Not used, present here for API consistency by convention.

        Returns
        -------
        predictions : pandas Series
            Predicted values.
        
        """

        if last_window is None:
            last_window = copy(self.last_window)

        check_predict_input(
            forecaster_name  = None,
            steps            = steps,
            fitted           = self.fitted,
            included_exog    = None,
            index_type       = self.index_type,
            index_freq       = self.index_freq,
            window_size      = self.window_size,
            last_window      = last_window,
            last_window_exog = None,
            exog             = None,
            exog_type        = None,
            exog_col_names   = None,
            interval         = None,
            alpha            = None,
            max_steps        = None,
            levels           = None,
            series_col_names = None
        )

        last_window_values, last_window_index = preprocess_last_window(
                                                    last_window = last_window
                                                )
        
        if isinstance(self.offset, int):
            equivalent_indexes = np.tile(
                                    np.arange(-self.offset, 0),
                                    int(np.ceil(steps/self.offset))
                                )
            equivalent_indexes = equivalent_indexes[:steps]
            equivalent_indexes = [
                equivalent_indexes - n * self.offset 
                for n
                in np.arange(self.n_equivalent_dates)
            ]
            equivalent_indexes = np.vstack(equivalent_indexes)
            equivalent_values = last_window_values[equivalent_indexes]

            if self.n_equivalent_dates == 1:
                predictions = equivalent_values.ravel()
            else:
                predictions = np.apply_along_axis(
                                self.agg_func,
                                axis=0,
                                arr=equivalent_values
                            )
            predictions_index = expand_index(index=last_window_index,steps=steps)

        if isinstance(self.offset, pd.tseries.offsets.DateOffset):
            predictions_index = expand_index(index=last_window_index,steps=steps)
            print(predictions_index[0])
            print(self.offset)
            print(self.index_freq)
            equivalent_dates = [
                            predictions_index[0] - self.offset + n * last_window_index.freq
                            for n
                            in np.arange(steps)[:len(last_window)]
                        ]
            equivalent_dates = np.tile(
                                    equivalent_dates,
                                    int(np.ceil(steps/len(equivalent_dates)))
                                )
            equivalent_dates = equivalent_dates[:steps]
            equivalent_dates = [
                [
                    date - self.offset * n
                    for n
                    in np.arange(self.n_equivalent_dates)
                ]
                for date
                in equivalent_dates
            ]
            equivalent_values = [
                last_window.loc[dates].to_numpy()
                for dates in equivalent_dates
            ]
            predictions = np.apply_along_axis(
                            func1d=np.mean,
                            axis=1,
                            arr=equivalent_values
                          )

        predictions = pd.Series(
                          data  = predictions,
                          index = predictions_index,
                          name = 'pred'
                      )
        
        return predictions