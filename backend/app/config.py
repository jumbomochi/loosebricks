from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://loosebricks:loosebricks@localhost:5432/loosebricks"
    jwt_secret_key: str = "change-me-in-production"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    apple_bundle_id: str = "com.loosebricks.app"
    aws_s3_bucket: str = "loosebricks-scans"
    aws_s3_endpoint_url: str | None = None
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    brickognize_api_url: str = "https://api.brickognize.com"
    rebrickable_api_key: str = ""
    confidence_threshold: float = 0.7

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
