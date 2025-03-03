import numpy as np
from numpy import save
import pandas as pd

# Drop the land nodes (the rows in the node feature matrix with NAs).
def drop_rows_w_nas(arr, *args, **kwarg):
    assert isinstance(arr, np.ndarray)
    dropped=pd.DataFrame(arr).dropna(*args, **kwarg).values
    if arr.ndim==1:
        dropped=dropped.flatten()
    return dropped

# Get SSTAs from an SST vector.
def get_ssta(time_series, train_num_year):
    monthly_avg = []
    for month in range(12):
      monthly_sst = time_series[month:train_num_year*12:12]
      monthly_avg.append(avg(monthly_sst))
      time_series[month::12] -= monthly_avg[month]
    return time_series

# Extract output vectors for more places.
def extract_y(lat, lon, filename, data_path, soda, train_num_year):
    soda_temp = soda.loc[dict(LAT=str(lat), LONN359_360=str(lon))]
    soda_temp_sst = np.zeros((len(soda.TIME), 1))
    soda_temp_sst[:,:] = soda_temp.variables['TEMP'][:,:]
    soda_temp_ssta = get_ssta(soda_temp_sst, train_num_year)
    save(data_path + 'y_' + filename + '.npy', soda_temp_ssta)

def avg(list):
    return sum(list) / len(list)