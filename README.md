# AWS re:invent 2023 CodeTalk API312 - Prepare terabytes of data for ML workloads with AWS Step Functions

This repository contains the sample code for the AWS re:invent 2023 CodeTalk session API312. Please clone this repository and follow the steps outlined below, to get hands-on experience with AWS Step Functions distributes map feature.
You can find the session slides and additional resources [here](https://serverlessland.com/explore/reinvent2023-api312).

## Prerequisites

To follow along, please make sure the following pre-requisites are in place:
- [ ] create an [AWS account](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/prerequisites.html#prerequisites-sign-up)
- [ ] create an [IAM user](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/prerequisites.html#prerequisites-create-user)
- [ ] install the [AWS CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/prerequisites.html#prerequisites-install-cli)
- [ ] configure the [AWS CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/prerequisites.html#prerequisites-configure-credentials)
- [ ] install [AWS SAM](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- [ ] install [jp](https://jqlang.github.io/jq/download/)


## Getting started

Clone this repository by running:
```bash
git clone https://github.com/aws-samples/reinvent2023-api312-ml-workloads-with-aws-step-functions.git
```

Change to the root directory of this sample:
```bash
cd reinvent2023-api312-ml-workloads-with-aws-step-functions
```

Next, provision the AWS services using the [AWS Serverless Application Model](https://aws.amazon.com/serverless/sam/) (AWS SAM). Because you will use a public dataset which is located in 'us-east-1' (N. Virginia), the recommendation is to use the same region for your deployment: 

```bash
sam build \
  && sam deploy \
    --region us-east-1 \
    --stack-name reinvent2023-api312 \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset
```

This SAM template provisions the following resources:  
  - an Amazon S3 bucket where you will store the public dataset
  - another Amazon S3 bucket where you will store the prepared datasets and a summary of the statemachine execution
  - an Amazon SNS topic, we use to notify interested services about a successful state machine execution
  - an AWS Lambda function which does the dataset preparation
  - an AWS Lambda function which mimics some pre-processing logic
  - an AWS CloudWatch dashboard, which visualizes some key metrics we want to optimize
  - the initial version of the AWS Step Functions (see below), which is using the inline Map state for parallel execution

![stepfunctions_graph_v1.png](images%2Fstepfunctions_graph_v1.png)

Now, you copy the [NOAA Global Surface Summary of Day](https://aws.amazon.com/marketplace/pp/prodview-yyq26ae3m6csk#resources) dataset to the previously created Amazon S3 bucket. This dataset includes global climate data obtained from the USAF Climatology Center, containing more than 570,000 CSV files.  
Let's first query for the S3 bucket name and store it in an local variable:
```bash
export SOURCE_S3_BUCKET_NAME=$(aws cloudformation describe-stacks \
--stack-name reinvent2023-api312 \
--query 'Stacks[].Outputs[?OutputKey==`MarketDataSourceS3BucketName`].OutputValue' \
--output text)
```

Copy the complete dataset into the S3 bucket by running the command below (this will take a few hours):  
```bash
aws s3 sync --no-progress s3://noaa-gsod-pds/ s3://$SOURCE_S3_BUCKET_NAME/
```

---
> **NOTE**: You can also copy a small subset by running for example `aws s3 cp --no-progress --recursive s3://noaa-gsod-pds/1929 s3://$SOURCE_S3_BUCKET_NAME/1929/` instead! To get a list about all available prefixes, run `aws s3 ls s3://noaa-gsod-pds/`.
---


## Run the initial version (v1)

First, store the AWS Step Functions ARN (Amazon Resource Name) in a local variable for easy reuse:  
```bash
export STEP_FUNCTIONS_ARN=$(aws cloudformation describe-stacks \
--stack-name reinvent2023-api312 \
--query 'Stacks[].Outputs[?OutputKey==`MarketDataMLPipelineStateMachine`].OutputValue' \
--output text)
```

Execute the Step Functions state machine and process the dataset from 1929 (21 files):  
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"1929/\"}" \
  | jq -r ".executionArn")
```

---
> **HINT**: You can also follow along by using the [AWS Step Functions Console](https://console.aws.amazon.com/states/home?#/statemachines) instead of the AWS CLI, if you wish so.
---

Now take a look at the execution status of this Step Functions execution:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

---
> **NOTE**: Make sure the execution finished already successfully. This will be the case, when the `status` is `SUCCEEDED`. Otherwise, rerun the previous command until the status changed to `SUCCEEDED`.
---

For such a small dataset, the execution work like expected and only takes around 5 seconds (the difference between `startDate` and `stopDate`).  

Using the [Amazon S3 Console](https://s3.console.aws.amazon.com/s3/buckets), take a look into the bucket starting with `reinvent2023-api312-marketdatatargets3bucket`. Navigate to the prefix `prepared-dataset/1929/` to look up the prepared files from our dataset.

Rerun the Step Functions statemachine with a larger dataset to face the first challenge (the dataset from 1941 contains 402 files):
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"1941/\"}" \
  | jq -r ".executionArn")
```

Take again a look at the execution status of this Step Functions execution:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

---
> **NOTE**: Rerun this command until the `status` changed from `RUNNING` to `SUCCEEDED`.
---

You will experience, this State Machine execution takes much longer to execute (more than 2 minutes). This will become a problem, taking the size of the dataset into account, you have to process by the end of this session (more than 570,000 files).  

---
> **Question 1**: Do you know why you see this large increase in the execution time, instead of AWS Step Functions scaling out the parallel executions more? Where you aware of it?
---

The AWS Lambda function `prepare_dataset` emits a custom Amazon CloudWatch metric `SuccessfulDatasetPreparation` in the namespace `API312`, which allows us to track how many files we processed per minute at peak. This is important, as this is the ultimate metric we want to optimize against.  
As part of the set-up, you also provisioned a CloudWatch dashboard which visualizes this and a few other important metrics. Let's take a look by navigating to the [Amazon CloudWatch dashboard](https://console.aws.amazon.com/cloudwatch/home?#dashboards/) and select the dashboard which starts with `MarketDataMLPipelineDashboard`. You will see that your peak throughput is about 200 files per minute:  

![throughput_v1.png](images%2Fthroughput_v1.png)

Before you tackle this challenge, rerun this Step Functions statemachine once more with an even larger dataset (the dataset from 1945 contains 1021 files):
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"1945/\"}" \
  | jq -r ".executionArn")
```

Take again a look at the execution status of this Step Functions execution:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

You will experience, this State Machine execution takes again much longer to execute (more than 5 minutes), before it fails. This is now stopping you to process even larger datasets. Let's tackle this problem now.  

---
> **Question 2**: Do you know why this Step Functions execution failed? Where you aware of it?
---

## Move from inline Map to distributes Map state (v2)

---
> **HINT**: We have prepared this version for you in the `[functions/v2](functions%2Fv2)` and `[statemachine/v2](statemachine%2Fv2)`, in case you want to straight execute the updated version.
---

First, update our solution so that it will reflect the following changes:
  - Step Functions statemachine definition: remove the `Source Data` state, as the `distributed Map` task will handle it
  - Step Functions statemachine definition: change the `Prepare Sourced Data` state to use the `DISTRIBUTED` mode

<details>
<summary>Expand to see the detailed changes</summary>

Run the below diff command to get the detailed list of changes you have to do:
```bash
sdiff -l statemachine/v1/sfn-template.asl.json statemachine/v2/sfn-template.asl.json | cat -n | grep -v -e '($'
```

You should see the following output:
```txt
     2    "Comment": "AWS re:invent 2023 API312 - v1",                |   "Comment": "AWS re:invent 2023 API312 - v2",
     3    "StartAt": "Source Data",                                   |   "StartAt": "Prepare Sourced Data",
     5      "Source Data": {                                          <
     6        "Type": "Task",                                         <
     7        "Resource": "arn:aws:states:::aws-sdk:s3:listObjectsV2" <
     8        "Parameters": {                                         <
     9          "Bucket": "${S3SourceBucket}",                        <
    10          "Prefix.$": "$.Prefix"                                <
    11        },                                                      <
    12        "Next": "Prepare Sourced Data"                          <
    13      },                                                        <
    16        "ItemsPath": "$.Contents",                              |       "MaxConcurrency": 500,
    17        "ResultPath": null,                                     |       "ItemReader": {
    18                                                                >         "Resource": "arn:aws:states:::s3:listObjectsV2",
    19                                                                >         "Parameters": {
    20                                                                >           "Bucket": "${S3SourceBucket}",
    21                                                                >           "Prefix.$": "$.Prefix"
    22                                                                >         }
    23                                                                >       },
    24                                                                >       "ResultWriter": {
    25                                                                >         "Resource": "arn:aws:states:::s3:putObject",
    26                                                                >         "Parameters": {
    27                                                                >           "Bucket": "${S3TargetBucket}",
    28                                                                >           "Prefix.$": "States.Format('execution-summary/{}', 
    29                                                                >         }
    30                                                                >       },
    33            "Mode": "INLINE"                                    |           "Mode": "DISTRIBUTED",
    34                                                                >           "ExecutionType": "EXPRESS"
```
</details>

Deploy your changes by running:
```bash
sam build \
&& sam deploy \
    --region us-east-1 \
    --stack-name reinvent2023-api312 \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset
```

Finally, your updated Step Functions statemachine should look like this one:

![stepfunctions_graph_v2.png](images%2Fstepfunctions_graph_v2.png)

Now it's time to rerun the dataset from 1945 to verify, that we could 
  - a) speed up the execution of datasets with hundreds of files
  - b) fixed the error with datasets with thousands of files

Start a new Step Functions execution by executing:
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"1945/\"}" \
  | jq -r ".executionArn")
```

Take again a look at the execution status of this Step Functions execution and rerun this command until the `status` shows `SUCCEEDED`:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

---
> **NOTE**: If the `status` changes to `FAILED`, please go back and make sure you update the Step Functions statemachine as described above.
---

You will see, this time we were successful in processing this dataset which failed before. It takes around 90 seconds to execute the statemachine. Not exactly where you would like to be at the end, but you made a good step towards the goal. 

Using the [Amazon S3 Console](https://s3.console.aws.amazon.com/s3/buckets), take a look into the bucket starting with `reinvent2023-api312-marketdatatargets3bucket`. Navigate to the prefix `prepared-dataset/execution-summary/1945/<UUID>/` to look up the `manifest.json` file, Step Functions distributed map generates for each run. Depending on the status of each run, you will also find the files `SUCCEEDED_0.json`, `PENDING_0.json` and `FAILED_0.json`. Take a minute to explore these files.

Rerun the Step Function statemachine again with an even larger dataset from 2001 (containing 9,008 files):
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"2001/\"}" \
  | jq -r ".executionArn")
```

Take again a look at the execution status of this Step Functions execution and rerun this command until the `status` shows `SUCCEEDED`:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

It will take less than 5 minutes to run it. But before you move on to the next challenge and optimize the throughput for even larger datasets, that a look at the CloudWatch dashboard again to verify how much we improved so far:  

![throughput_v2.png](images%2Fthroughput_v2.png)

You are now able to process around 4,000 files per minute, about 20 times more then before, without significant changes!

## ItemBatcher for improved throughput (v3)

---
> **HINT**: We have prepared this version for you in the `[functions/v3](functions%2Fv3)` and `[statemachine/v3](statemachine%2Fv3)`, in case you want to straight execute the updated version.
---

To optimize the throughput, we have to:  
  - a) improve the performance of our `prepare dataset` function
  - b) increase the number of parallel executions in Step Functions
  - c) process the individual files more efficiently

Let's assume the `prepare dataset` function cannot be optimized further. While we can increase the number of parallel executions in Step Functions, let's put that aside for a moment (we will come back to it later - promised!). Let's see how we can process the individual files more efficiently.  
When you look at the `Lambda Duration` metric in your CloudWatch dashboard, you will see that at `P90`, it takes less than 40ms to process one file:  

![lambda_execution_duration.png](images%2Flambda_execution_duration.png)

A more efficient way to process these files would be, to batch them. This would allow one Lambda function to process multiple files in one execution, reducing the back and forth between Step Functions and Lambda for every file. Let's do that.  

To do so, you have to make the following changes:
  - Step Functions statemachine definition: add the `ItemBatcher` configuration to our map state
  - Step Functions statemachine definition: remove the `Read File` state
  - Step Functions statemachine definition: remove the `Stage Dataset` state

<details>
<summary>Expand to see the detailed changes</summary>

Run the below diff command to get the detailed list of changes you have to do in the Step Functions statemachine definition:
```bash
sdiff -l statemachine/v2/sfn-template.asl.json statemachine/v3/sfn-template.asl.json | cat -n | grep -v -e '($'
```

You should see the following output:
```txt
     2    "Comment": "AWS re:invent 2023 API312 - v2",                |   "Comment": "AWS re:invent 2023 API312 - v3",
     8                                                                >       "ItemBatcher": {
     9                                                                >         "MaxItemsPerBatch": 20
    10                                                                >       },
    30          "StartAt": "Read File",                               |         "StartAt": "Pre Process",
    32            "Read File": {                                      <
    33              "Type": "Task",                                   <
    34              "Resource": "arn:aws:states:::aws-sdk:s3:getObjec <
    35              "Parameters": {                                   <
    36                "Bucket": "${S3SourceBucket}",                  <
    37                "Key.$": "$.Key"                                <
    38              },                                                <
    39              "ResultSelector": {                               <
    40                "Body.$": "$.Body"                              <
    41              },                                                <
    42              "ResultPath": "$.File",                           <
    43              "Next": "Pre Process"                             <
    44            },                                                  <
    63              "Next": "Stage Dataset"                           <
    64            },                                                  <
    65            "Stage Dataset": {                                  <
    66              "Type": "Task",                                   <
    67              "Resource": "arn:aws:states:::aws-sdk:s3:putObjec <
    68              "Parameters": {                                   <
    69                "Bucket": "${S3TargetBucket}",                  <
    70                "Key.$": "States.Format('prepared-dataset/{}',  <
    71                "Body.$": "$.File.Body"                         <
    72              },                                                <
    73              "ResultPath": null,                               <
```

Run the below diff command to get the detailed list of changes you have to do in the `prepare_dataset` Lambda function:
```bash
sdiff -l functions/v2/prepare_dataset/app.py functions/v3/prepare_dataset/app.py | cat -n | grep -v -e '($'
```

You should see the following output:  
```txt
     3  import io                                                     | import boto3
     4                                                                > import os
     6                                                                > import uuid
    10                                                                > s3_source_bucket = os.environ.get('S3_SOURCE_BUCKET')
    11                                                                > s3_target_bucket = os.environ.get('S3_TARGET_BUCKET')
    12                                                                > 
    13                                                                > s3_client = boto3.client('s3')
    14                                                                > 
    23      key = event['Key']                                        |     items = event.get('Items', [event])
    24                                                                >     file_content = ''
    25                                                                >     initial_row_count = 0
    26                                                                >     initial_column_count = 0
    27                                                                >     row_count = 0
    28                                                                >     column_count = 0
    30      # create a Panda data frame based on the csv data         |     for item in items:
    31      df = pd.read_csv(io.StringIO(event['File']['Body']))      |         key = item['Key']
    34      shape = df.shape                                          |             Bucket=s3_source_bucket,
    35      initial_row_count = shape[0]                              |             Key=key
    36      initial_column_count = shape[1]                           |         )
    38      # drop all columns we don't need                          |         # create a Panda data frame based on the csv data
    39      df.drop(['TEMP_ATTRIBUTES','DEWP','DEWP_ATTRIBUTES','SLP' |         df = pd.read_csv(get_object_response['Body'])
    41      # drop all rows with 'NAN' and '-INF' values              |         # record the initial row and column count
    42      df = df.dropna()                                          |         shape = df.shape
    43                                                                >         initial_row_count = initial_row_count + shape[0]
    44                                                                >         initial_column_count = shape[1]
    46      # prepare data: convert temperature value from fahrenheit |         # drop all columns we don't need
    47      df[['TEMP', 'MAX', 'MIN']] = df[['TEMP', 'MAX', 'MIN']].a |         df.drop(['TEMP_ATTRIBUTES','DEWP','DEWP_ATTRIBUTES','
    48      df.rename(columns={'TEMP' : 'TEMP_CELSIUS', 'MAX' : 'MAX_ <
    50      # validate data: drop rows where the temperature is out o |         # drop all rows with 'NAN' and '-INF' values
    51      df.drop(df[(df.TEMP_CELSIUS < -90) | (df.TEMP_CELSIUS > 6 |         df = df.dropna()
    52      df.drop(df[(df.MIN_CELSIUS < -90) | (df.MIN_CELSIUS > 60) <
    53      df.drop(df[(df.MAX_CELSIUS < -90) | (df.MAX_CELSIUS > 60) <
    55      # extract feature: store the day of week as separate colu |         # prepare data: convert temperature value from fahren
    56      df['DAY_OF_WEEK'] = df['DATE'].apply(extract_day_of_week) |         df[['TEMP', 'MAX', 'MIN']] = df[['TEMP', 'MAX', 'MIN'
    57                                                                >         df.rename(columns={'TEMP' : 'TEMP_CELSIUS', 'MAX' : '
    59      # record the current row and column count                 |         # validate data: drop rows where the temperature is o
    60      shape = df.shape                                          |         df.drop(df[(df.TEMP_CELSIUS < -90) | (df.TEMP_CELSIUS
    61      row_count = shape[0]                                      |         df.drop(df[(df.MIN_CELSIUS < -90) | (df.MIN_CELSIUS >
    62      column_count = shape[1]                                   |         df.drop(df[(df.MAX_CELSIUS < -90) | (df.MAX_CELSIUS >
    64      # don't write the row index                               |         # extract feature: store the day of week as separate 
    65      file_content = df.to_csv(index=False)                     |         df['DAY_OF_WEEK'] = df['DATE'].apply(extract_day_of_w
    67      # add a custom AWS CloudWatch metric to track number of s |         # record the current row and column count
    68      metrics.add_metric(name="SuccessfulDatasetPreparation", u |         shape = df.shape
    69                                                                >         row_count = row_count + shape[0]
    70                                                                >         column_count = shape[1]
    72      event['File']['Body'] = file_content                      |         # don't write the row index
    73      event['InitialColumnCount'] = initial_column_count        |         file_content = file_content + df.to_csv(index=False, 
    74      event['ColumnCount'] = column_count                       <
    75      event['InitialRowCount'] = initial_row_count              <
    76      event['RowCount'] = row_count                             <
    78      return event                                              |         # add a custom AWS CloudWatch metric to track number 
    79                                                                >         metrics.add_metric(name="SuccessfulDatasetPreparation
    80                                                                > 
    81                                                                >     key = f"prepared-dataset/{str(uuid.uuid4())}.csv"
    83                                                                >         Bucket=s3_target_bucket,
    84                                                                >         Key=key,
    85                                                                >         Body=file_content
    86                                                                >     )
    87                                                                > 
    88                                                                >     result = {
    89                                                                >         'Key': key,
    90                                                                >         'InitialColumnCount': initial_column_count,
    91                                                                >         'ColumnCount': column_count,
    92                                                                >         'InitialRowCount': initial_row_count,
    93                                                                >         'RowCount': row_count
    94                                                                >     }
    95                                                                > 
    96                                                                >     return result
```
</details>

Deploy your changes by running:
```bash
sam build \
&& sam deploy \
    --region us-east-1 \
    --stack-name reinvent2023-api312 \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset
```

Finally, your updated Step Functions statemachine should look like this one:

![stepfunctions_graph_v2.png](images%2Fstepfunctions_graph_v3.png)

Now it's time to rerun the dataset from 2001 to verify, that we could speed up the execution again:
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"2001/\"}" \
  | jq -r ".executionArn")
```

Take again a look at the execution status of this Step Functions execution and rerun this command until the `status` shows `SUCCEEDED`:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

Now the statemachine execution is down from almost 5 minutes to 15 seconds!  


## Optimize for maximum throughput (v4)

---
> **HINT**: We have prepared this version for you in the `[functions/v4](functions%2Fv4)` and `[statemachine/v4](statemachine%2Fv4)`, in case you want to straight execute the updated version.
---

First, make following changes:
- Step Functions statemachine definition: update the `MaxConcurrency` configuration to 1000
- Step Functions statemachine definition: update the `MaxItemsPerBatch` configuration to 100

<details>
<summary>Expand to see the detailed changes</summary>

```txt
     2    "Comment": "AWS re:invent 2023 API312 - v3",                |   "Comment": "AWS re:invent 2023 API312 - v4",
     7        "MaxConcurrency": 500,                                  |       "MaxConcurrency": 1000,
     9          "MaxItemsPerBatch": 20                                |         "MaxItemsPerBatch": 100
```
</details>

Deploy your changes by running:
```bash
sam build \
&& sam deploy \
    --region us-east-1 \
    --stack-name reinvent2023-api312 \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset
```

Go to your [AWS Step Functions Console](https://console.aws.amazon.com/states/home?#/statemachines) and navigate to the statemachine where the name starts with `MarketDataMLPipelineStateMachine`. Click on the button `Start Execution`, provide the input json from below and click on `Start execution`.

```json
{
  "Prefix": ""
}
```

Quickly scroll down on this page and click on `Map Run`. You will observe that it takes about a minute, until the first executions start. This delay comes from the S3 `listObjectsV2` operations, which only returns at maximum 1,000 file names. Therefore, Step Functions has to iterate more than 570 times, until it has a complete file inventory for this dataset:

![s3_list_delay.png](images%2Fs3_list_delay.png)

To avoid this delay, you can configure Step Functions distributed Map to read an [Amazon S3 inventory file](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-inventory.html) in CSV format. As the last step in optimizing your throughput, you have to make the following changes:
- Step Functions statemachine definition: update the `ReaderConfig` to use the `arn:aws:states:::s3:getObject` resource and read the Amazon S3 inventory MANIFEST file

<details>
<summary>Expand to see the detailed changes</summary>

Run the below diff command to get the detailed list of changes you have to do in the Step Functions statemachine definition:
```bash
sdiff -l statemachine/v3/sfn-template.asl.json statemachine/v4/sfn-template.asl.json | cat -n | grep -v -e '($'
```

You should see the following output:
```txt
    12          "Resource": "arn:aws:states:::s3:listObjectsV2",      |         "Resource": "arn:aws:states:::s3:getObject",
    15            "Prefix.$": "$.Prefix"                              |           "Key.$": "$.Key"
    16                                                                >         },
    17                                                                >         "ReaderConfig": {
    18                                                                >           "InputType": "MANIFEST"
    25            "Prefix.$": "States.Format('summary/{}', $.Prefix)" |           "Prefix.$": "States.Format('summary/{}', $.Key)"
```
</details>

Deploy your changes by running:
```bash
sam build \
&& sam deploy \
    --region us-east-1 \
    --stack-name reinvent2023-api312 \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset
```
 
Now it's finally time to run the Step Functions statemachine with the complete dataset of more than 570,000 files, leveraging the Amazon S3 inventory file:  
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Key\": \"<S3 KEY TO THE S3 INVENTORY FILE>\"}" \
  | jq -r ".executionArn")
```

---
> **NOTE**: You can determine the size of the entire dataset by running `aws s3 ls --summarize --recursive s3://$SOURCE_S3_BUCKET_NAME/ | tail -2`.
---

Take again a look at the execution status of this Step Functions execution and rerun this command until the `status` shows `SUCCEEDED`:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

You managed to prepare more than 570,000 files in just about 2 minutes! Check you CloudWatch dashboard as well, and you will see a peak throughput of about 440,000 files per minute!

![final_execution_result.png](images%2Ffinal_execution_result.png)


## Redrive from failures (v5)

---
> **HINT**: We have prepared this version for you in the `[functions/v5](functions%2Fv5)` and `[statemachine/v5](statemachine%2Fv5)`, in case you want to straight execute the updated version.
---

Now that you've fixed the problem when working with large datasets, let's see what else Step Functions distributed map has to offer.  
Intermediate failures due to the unavailability of downstream services can become an issue, while working on large datasets. Image you processed a large dataset for hours and just because a single execution failed, you have to rerun the entire statemachine.

Fortunately, in November 2023 AWS introduced [AWS Step Functions redrive to recover from failures more easily](https://aws.amazon.com/blogs/compute/introducing-aws-step-functions-redrive-a-new-way-to-restart-workflows/). This allows you to only rerun the failed executions, which will help you to save time and money. To try this out, you have to make the following changes:
- Step Functions statemachine definition: update the `MaxConcurrency` configuration to 20
- Step Functions statemachine definition: update the `MaxItemsPerBatch` configuration to 20
- Step Functions statemachine definition: update the `ReaderConfig` to use the `arn:aws:states:::s3:listObjectsV2` resource
- AWS Lambda function pass_through: update the function so that it fails every 20th execution.

<details>
<summary>Expand to see the detailed changes</summary>

Run the below diff command to get the detailed list of changes you have to do in the Step Functions statemachine definition:
```bash
sdiff -l statemachine/v4/sfn-template.asl.json statemachine/v5/sfn-template.asl.json | cat -n | grep -v -e '($'
```

You should see the following output:
```txt
     2    "Comment": "AWS re:invent 2023 API312 - v4",                       |   "Comment": "AWS re:invent 2023 API312 - v5",
     7        "MaxConcurrency": 1000,                                        |       "MaxConcurrency": 20,
     9          "MaxItemsPerBatch": 100                                      |         "MaxItemsPerBatch": 20
    12          "Resource": "arn:aws:states:::s3:getObject",                 |         "Resource": "arn:aws:states:::s3:listObjectsV2",
    15            "Key.$": "$.Key"                                           |           "Prefix.$": "$.Prefix"
    16          },                                                           <
    17          "ReaderConfig": {                                            <
    18            "InputType": "MANIFEST"                                    <
    25            "Prefix.$": "States.Format('execution-summary/{}', $.Key)" |           "Prefix.$": "States.Format('execution-summary/{}', $.Prefix)"
```

Run the below diff command to get the detailed list of changes you have to do in the pass_through Lambda function:
```bash
sdiff -l functions/v4/pass_through/app.py functions/v5/pass_through/app.py | cat -n | grep -v -e '($'
```

You should see the following output:
```txt
     1                                                                > execution_counter = 0
     2                                                                > 
     4                                                                >     global execution_counter
     5                                                                >     execution_counter = execution_counter + 1
     7                                                                >     if (execution_counter % 20 == 0):
     8                                                                >         raise Exception("Pre-processing failed, as the backend system didn't respond in time!")
     9                                                                > 
```
</details>

Deploy your changes by running:
```bash
sam build \
&& sam deploy \
    --region us-east-1 \
    --stack-name reinvent2023-api312 \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset
```

Run the statemachine with the dataset from 1945 (containing 1021 files):
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"1945/\"}" \
  | jq -r ".executionArn")
```

Take again a look at the execution status of this Step Functions execution and rerun this command until the `status` shows `FAILED`:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

Take a look into your [S3 Console](https://s3.console.aws.amazon.com/s3/buckets) and navigate to the bucket which starts with the name `reinvent2023-api312-marketdatatargets3bucket`. Navigate to the prefix `execution-summary/1945/<UUID>/`. You should see a similar result like this (your result may vary a bit):  

![redrive_test_result.png](images%2Fredrive_test_result.png)

Explore the 4 files to understand the content and structure.  

Now redrive the statemachine execution from where it failed:
```bash
aws stepfunctions redrive-execution \
  --execution-arn $EXECUTION_ARN
```

Check again the execution status of this Step Functions execution and rerun this command until the `status` shows `SUCCEEDED`:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

Go back to you S3 bucket `reinvent2023-api312-marketdatatargets3bucket` and navigate again to the prefix `execution-summary/1945/<UUID>/`. You will find a new prefix `Redrive-1/`. Explore the newly created files during the redrive.  
This time, you should only see the files `manifest.json` and `SUCCEEDED_0.json`, which is an indication that the execution finished successful.

![redrive_test_final_result.png](images%2Fredrive_test_final_result.png)


## Handling intermediate failures (v6)

---
> **HINT**: We have prepared this version for you in the `[functions/v6](functions%2Fv6)` and `[statemachine/v6](statemachine%2Fv6)`, in case you want to straight execute the updated version.
---

Finally, you will tackle the challenge that the preparation of certain files is failing due to different reasons, but you want to tolerate these failures as long as they stay below a certain threshold. 

Fortunately, in November 2023 AWS introduced [AWS Step Functions redrive to recover from failures more easily](https://aws.amazon.com/blogs/compute/introducing-aws-step-functions-redrive-a-new-way-to-restart-workflows/). This allows you to only rerun the failed executions, which will help you to save time and money. To try this out, you have to make the following changes:
- Step Functions statemachine definition: add the `ToleratedFailurePercentage` configuration with the value 5

<details>
<summary>Expand to see the detailed changes</summary>

Run the below diff command to get the detailed list of changes you have to do in the Step Functions statemachine definition:
```bash
sdiff -l statemachine/v5/sfn-template.asl.json statemachine/v6/sfn-template.asl.json | cat -n | grep -v -e '($'
```

You should see the following output:
```txt
     2    "Comment": "AWS re:invent 2023 API312 - v5",                |   "Comment": "AWS re:invent 2023 API312 - v6",
     8                                                                >       "ToleratedFailurePercentage": 5,
```
</details>

Deploy your changes by running:
```bash
sam build \
&& sam deploy \
    --region us-east-1 \
    --stack-name reinvent2023-api312 \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --no-confirm-changeset
```

Run the statemachine with the dataset from 1945 (containing 1021 files):
```bash
export EXECUTION_ARN=$(aws stepfunctions start-execution \
  --state-machine-arn $STEP_FUNCTIONS_ARN \
  --input "{\"Prefix\": \"1945/\"}" \
  | jq -r ".executionArn")
```

Take again a look at the execution status of this Step Functions execution and rerun this command until the `status` shows `SUCCEEDED`:
```bash
aws stepfunctions describe-execution \
  --execution-arn $EXECUTION_ARN
```

```bash
aws stepfunctions describe-map-run \
  --map-run-arn <COPY MAP RUN FROM OUTPUT OF PREVIOUS describe-execution>
```

Your output should look similar to the one below.  
Please take attention to the `failed` attribute in `itemCounts` and `executionCounts` as well. This shows that one batch with 20 items (files) failed, but because it is below the `toleratedFailurePercentage` of 5%, it finished successfully.
```
{
    "mapRunArn": "arn:aws:states:us-east-1:...",
    "executionArn": "arn:aws:states:us-east-1:...",
    "status": "SUCCEEDED",
    "startDate": "2023-11-27T11:17:25.142000-08:00",
    "stopDate": "2023-11-27T11:17:33.813000-08:00",
    "maxConcurrency": 20,
    "toleratedFailurePercentage": 5.0,
    "toleratedFailureCount": 0,
    "itemCounts": {
        "pending": 0,
        "running": 0,
        "succeeded": 1001,
        "failed": 20,
        "timedOut": 0,
        "aborted": 0,
        "total": 1021,
        "resultsWritten": 1021,
        "failuresNotRedrivable": 0,
        "pendingRedrive": 0
    },
    "executionCounts": {
        "pending": 0,
        "running": 0,
        "succeeded": 51,
        "failed": 1,
        "timedOut": 0,
        "aborted": 0,
        "total": 52,
        "resultsWritten": 52,
        "failuresNotRedrivable": 0,
        "pendingRedrive": 0
    },
    "redriveCount": 0
}
```

Navigate to the [Step Functions Console](https://console.aws.amazon.com/states/home?#/statemachines), select your statemachine which starts with `MarketDataMLPipelineStateMachine` and select the last statemachine execution. In the `Graph view`, select the `Prepare Sourced Data` state and click on the `Map Run` button which appears on the right side. It also highlights, that the distributed map run finished successfully, but with some failed executions:

![tolerated_failure.png](images%2Ftolerated_failure.png)

Congrats, you made it to the end! We really hope you learned something new.
If you are interested in additional related resources, we would be pleased if you visit us at [Serverlessland.com](https://serverlessland.com/explore/reinvent2023-api312).


# License
This sample is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
