import asyncio
from nats.aio.client import Client as NATS
from logging_config import logger  # Assuming logger is shared across files

# Module 1: Connect to NATS server
async def connect_nats(nats_server_url):
    """
    Connect to the NATS server.

    Args:
        nats_server_url (str): URL of the NATS server.

    Returns:
        NATS: An instance of the connected NATS client.
    """
    nc = NATS()
    try:
        await nc.connect(nats_server_url)
        logger.info(f"Connected to NATS server at {nats_server_url}")
        return nc
    except Exception as e:
        logger.error(f"Failed to connect to NATS server: {e}")
        raise

# Module 2: Subscribe to a topic
async def subscribe_to_topic(nc, topic, message_handler):
    """
    Subscribe to a NATS topic and set up a message handler.

    Args:
        nc (NATS): An instance of the connected NATS client.
        topic (str): The topic to subscribe to.
        message_handler (callable): The handler function for processing messages.
    """
    try:
        await nc.subscribe(topic, cb=message_handler)
        logger.info(f"Subscribed to NATS topic: {topic}")
    except Exception as e:
        logger.error(f"Error subscribing to topic '{topic}': {e}")
        raise

# Main NATS subscription logic
async def nats_subscriber(config):
    """
    NATS subscription logic.
    """
    nats_server_url = config['NATS_Config']['server_url']
    nats_topic = config['NATS_Config']['topic']

    try:
        # Connect to NATS
        nc = await connect_nats(nats_server_url)

        # Define the message handler
        async def message_handler(msg):
            subject = msg.subject
            data = msg.data.decode()
            logger.info(f"Received a message on '{subject}': {data}")

            if subject == nats_topic:
                logger.info(f"Handling message: {data}")

        # Subscribe to the topic
        await subscribe_to_topic(nc, nats_topic, message_handler)

        # Keep the connection alive
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Error in NATS subscription: {e}")

    finally:
        await nc.drain()

# Function to run the subscriber in a separate thread
def run_nats_subscriber(config):
    """
    Run the NATS subscriber in a separate thread.
    """
    logger.info(f"Starting NATS subscriber...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nats_subscriber(config))
    loop.run_forever()
