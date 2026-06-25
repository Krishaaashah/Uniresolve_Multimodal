import asyncio
import logging
from app.connectors.replay import ReplayConnector
from app.connectors.email_imap import EmailIMAPConnector
from app.connectors.reddit_api import RedditAPIConnector
from app.config import CONNECTOR_POLL_INTERVAL

logger = logging.getLogger(__name__)

ACTIVE_CONNECTORS = [
    ReplayConnector(channel="branch"),
    ReplayConnector(channel="ivr"),
    ReplayConnector(channel="app"),
    EmailIMAPConnector(),
    RedditAPIConnector()
]

async def run_orchestrator():
    """Runs all registered connectors in a loop."""
    logger.info("Initializing multi-channel complaint connectors...")
    # Initial sleep to ensure uvicorn is fully booted and listening
    await asyncio.sleep(5)
    
    loop = asyncio.get_running_loop()
    while True:
        logger.info("Starting connector polling cycle...")
        for connector in ACTIVE_CONNECTORS:
            try:
                # Execute the blocking connector run in a background thread
                await loop.run_in_executor(None, connector.run)
            except Exception as e:
                logger.error(f"Error running connector for channel {connector.channel}: {e}")
        
        logger.info(f"Connector cycle finished. Sleeping for {CONNECTOR_POLL_INTERVAL} seconds.")
        await asyncio.sleep(CONNECTOR_POLL_INTERVAL)
