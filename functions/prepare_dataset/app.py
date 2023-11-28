from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit
import io
import logging
import pandas as pd

logger = logging.getLogger()
logger.setLevel(logging.INFO)

metrics = Metrics()

def convert_fahrenheit_to_celsius(temp):
    return (temp - 32) / 1.8

def extract_day_of_week(date):
    return pd.Timestamp(date).dayofweek

@metrics.log_metrics  # ensures metrics are flushed upon request completion/failure
def lambda_handler(event, context):
    logger.info(event)

    key = event['Key']

    # create a Panda data frame based on the csv data
    df = pd.read_csv(io.StringIO(event['File']['Body']))

    # record the initial row and column count
    shape = df.shape
    initial_row_count = shape[0]
    initial_column_count = shape[1]

    # drop all columns we don't need
    df.drop(['TEMP_ATTRIBUTES','DEWP','DEWP_ATTRIBUTES','SLP','SLP_ATTRIBUTES','STP','STP_ATTRIBUTES','VISIB','VISIB_ATTRIBUTES','WDSP','WDSP_ATTRIBUTES','MXSPD','GUST','MAX_ATTRIBUTES','MIN_ATTRIBUTES','PRCP','PRCP_ATTRIBUTES','SNDP','FRSHTT'], axis=1, inplace=True)

    # drop all rows with 'NAN' and '-INF' values
    df = df.dropna()

    # prepare data: convert temperature value from fahrenheit to celsius
    df[['TEMP', 'MAX', 'MIN']] = df[['TEMP', 'MAX', 'MIN']].apply(convert_fahrenheit_to_celsius)
    df.rename(columns={'TEMP' : 'TEMP_CELSIUS', 'MAX' : 'MAX_CELSIUS', 'MIN' : 'MIN_CELSIUS'}, inplace=True)

    # validate data: drop rows where the temperature is out of range and it's most likely a measurement error
    df.drop(df[(df.TEMP_CELSIUS < -90) | (df.TEMP_CELSIUS > 60)].index, inplace=True)
    df.drop(df[(df.MIN_CELSIUS < -90) | (df.MIN_CELSIUS > 60)].index, inplace=True)
    df.drop(df[(df.MAX_CELSIUS < -90) | (df.MAX_CELSIUS > 60)].index, inplace=True)

    # extract feature: store the day of week as separate column
    df['DAY_OF_WEEK'] = df['DATE'].apply(extract_day_of_week)

    # record the current row and column count
    shape = df.shape
    row_count = shape[0]
    column_count = shape[1]

    # don't write the row index
    file_content = df.to_csv(index=False)

    # add a custom AWS CloudWatch metric to track number of successful dataset preparation executions
    metrics.add_metric(name="SuccessfulDatasetPreparation", unit=MetricUnit.Count, value=1)

    event['File']['Body'] = file_content
    event['InitialColumnCount'] = initial_column_count
    event['ColumnCount'] = column_count
    event['InitialRowCount'] = initial_row_count
    event['RowCount'] = row_count

    return event
