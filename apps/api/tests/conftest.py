import os

os.environ["APP_ENV"] = "test"
os.environ["API_TOKEN"] = "test-token-" + "a" * 48
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
