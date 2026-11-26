# pip install redis

import os
import redis
import logging

# Configure structured/standard logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def get_redis_client(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    password=os.getenv('REDIS_PASSWORD', 'admin')
):
    """
    Creates and returns a Redis client instance with exception handling and connection validation.
    """
    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            socket_timeout=5.0
        )
        # Ping to verify connection
        client.ping()
        logger.info("Successfully connected to Redis server at %s:%d", host, port)
        return client
    except redis.AuthenticationError as e:
        logger.error("Redis authentication failed: %s", e)
        raise
    except redis.ConnectionError as e:
        logger.error("Failed to connect to Redis server at %s:%d: %s", host, port, e)
        raise
    except Exception as e:
        logger.error("Unexpected error connecting to Redis: %s", e, exc_info=True)
        raise RuntimeError("Failed to initialize Redis client", e) from e

def main():
    try:
        r = get_redis_client()

        # Set a value
        r.set('my_key', 'my_value')
        logger.info("Successfully set 'my_key'")

        # Get the value
        value = r.get('my_key')
        logger.info("Retrieved value for 'my_key': %s", value)
        print(f"Output: {value}")

    except Exception as e:
        logger.error("An error occurred during Redis operations: %s", e)

if __name__ == '__main__':
    main()
