"""
AWS Lambda handler for FastAPI application using Mangum.
Exposes the FastAPI app as a Lambda function compatible with API Gateway.
"""

import logging
from mangum import Mangum
from app.main import app

# Configure logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create the Lambda handler using Mangum adapter
# This wraps the FastAPI app and makes it compatible with AWS Lambda + API Gateway
handler = Mangum(app, lifespan="off")


def lambda_handler(event, context):
    """
    AWS Lambda entry point.
    
    Parameters
    ----------
    event : dict
        API Gateway event object containing the HTTP request details
    context : LambdaContext
        AWS Lambda context object with runtime information
    
    Returns
    -------
    dict
        API Gateway-compatible response with statusCode, headers, and body
    """
    logger.info("Received event: %s", event.get("requestContext", {}).get("requestId", "unknown"))
    
    # Mangum handles the conversion between API Gateway and ASGI
    return handler(event, context)
