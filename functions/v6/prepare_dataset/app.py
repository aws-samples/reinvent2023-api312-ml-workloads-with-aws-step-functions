from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit
import boto3
import logging
import os
import pandas as pd
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

metrics = Metrics()

s3_source_bucket = os.environ.get('S3_SOURCE_BUCKET')
s3_target_bucket = os.environ.get('S3_TARGET_BUCKET')

s3_client = boto3.client('s3')

def convert_fahrenheit_to_celsius(temp):
    return (temp - 32) / 1.8

def extract_day_of_week(date):
    return pd.Timestamp(date).dayofweek

@metrics.log_metrics  # ensures metrics are flushed upon request completion/failure
def lambda_handler(event, context):
    logger.info(event)

    items = event.get('Items', [event])
    file_content = ''
    initial_row_count = 0
    initial_column_count = 0
    row_count = 0
    column_count = 0

    for item in items:
        key = item['Key']
        logger.info(f"preparing file: {key}")

        get_object_response = s3_client.get_object(
            Bucket=s3_source_bucket,
            Key=key
        )

        # create a Panda data frame based on the csv data
        df = pd.read_csv(get_object_response['Body'])

        # record the initial row and column count
        shape = df.shape
        initial_row_count = initial_row_count + shape[0]
        initial_column_count = shape[1]

        # drop all columns we don't need
        df.drop(['TEMP_ATTRIBUTES','DEWP','DEWP_ATTRIBUTES','SLP','SLP_ATTRIBUTES','STP','STP_ATTRIBUTES','VISIB','VISIB_ATTRIBUTES','WDSP','WDSP_ATTRIBUTES','MXSPD','GUST','MAX_ATTRIBUTES','MIN_ATTRIBUTES','PRCP','PRCP_ATTRIBUTES','SNDP','FRSHTT'], axis=1, inplace=True)

        # drop all rows with 'NAN' and '-INF' values
        df = df.dropna()

        # prepare data: convert temperature value from fahrenheit to celsius
        df[['TEMP', 'MAX', 'MIN']] = df[['TEMP', 'MAX', 'MIN']].apply(convert_fahrenheit_to_celsius)
        df.rename(columns={'TEMP' : 'TEMP_CELSIUS', 'MAX' : 'MAX_CELSIUS', 'MIN' : 'MIN_CELSIUS'}, inplace=True)

        # validate data: drop rows where the temperature is out of range, and it's most likely a measurement error
        df.drop(df[(df.TEMP_CELSIUS < -90) | (df.TEMP_CELSIUS > 60)].index, inplace=True)
        df.drop(df[(df.MIN_CELSIUS < -90) | (df.MIN_CELSIUS > 60)].index, inplace=True)
        df.drop(df[(df.MAX_CELSIUS < -90) | (df.MAX_CELSIUS > 60)].index, inplace=True)

        # extract feature: store the day of week as separate column
        df['DAY_OF_WEEK'] = df['DATE'].apply(extract_day_of_week)

        # record the current row and column count
        shape = df.shape
        row_count = row_count + shape[0]
        column_count = shape[1]

        # don't write the row index
        file_content = file_content + df.to_csv(index=False, header=(not file_content))

        # add a custom AWS CloudWatch metric to track number of successful dataset preparation executions
        metrics.add_metric(name="SuccessfulDatasetPreparation", unit=MetricUnit.Count, value=1)

    key = f"prepared-dataset/{str(uuid.uuid4())}.csv"
    s3_client.put_object(
        Bucket=s3_target_bucket,
        Key=key,
        Body=file_content
    )

    result = {
        'Key': key,
        'InitialColumnCount': initial_column_count,
        'ColumnCount': column_count,
        'InitialRowCount': initial_row_count,
        'RowCount': row_count
    }

    return result
