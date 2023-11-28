execution_counter = 0

def lambda_handler(event, context):
    global execution_counter
    execution_counter = execution_counter + 1

    if (execution_counter % 20 == 0):
        raise Exception("Pre-processing failed, as the backend system didn't respond in time!")

    return event
