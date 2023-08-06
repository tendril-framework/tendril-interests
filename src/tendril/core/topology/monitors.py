

from tendril.core.mq.aio import with_mq_client
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)

#TODO Create the exchange as well

@with_mq_client
async def create_mq_topology(mq=None):
    logger.info("Creating the Interest Monitors storage worker queue.")
    monitor_publish_queue = await mq.create_work_queue('monitors_raw', topic='im.#')
