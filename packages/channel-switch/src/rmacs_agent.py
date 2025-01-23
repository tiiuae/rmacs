import asyncio
from nats.aio.client import Client as NATS
from logging_config import logger  # Assuming logger is shared across files

async def nats_subscriber(config):
    """
    NATS subscription logic.
    """
    nc = NATS()
    nats_server_url = config['NATS_Config']['server_url']
    nats_topic = config['NATS_Config']['topic']

    try:
        await nc.connect(nats_server_url)

        async def message_handler(msg):
            subject = msg.subject
            data = msg.data.decode()
            logger.info(f"Received a message on '{subject}': {data}")

            # Example: Handle parameter updates or trigger other actions
            if subject == nats_topic:
                logger.info(f"Handling message: {data}")

        await nc.subscribe(nats_topic, cb=message_handler)
        logger.info(f"Subscribed to NATS topic: {nats_topic}")

        while True:
            await asyncio.sleep(1)  # Keep the connection alive

    except Exception as e:
        logger.error(f"Error in NATS subscription: {e}")

    finally:
        await nc.drain()


def run_nats_subscriber(config):
    """
    Run the NATS subscriber in a separate thread.
    """
    logger.info(f"Started nats sub.....")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(nats_subscriber(config))
    loop.run_forever()
