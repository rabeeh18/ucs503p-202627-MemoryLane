import os

# Test-only Cognito settings, set before backend.config is imported. Real values
# from .env don't apply because load_dotenv never overrides existing variables.
os.environ["COGNITO_REGION"] = "ap-south-1"
os.environ["COGNITO_USER_POOL_ID"] = "ap-south-1_TESTPOOL"
os.environ["COGNITO_APP_CLIENT_ID"] = "test-client-id"
