import sys
import time
import logging
import threading

logger = logging.getLogger(__name__)


def background(f):
    """
    a threading decorator
    use @background above the function you want to run in the background
    """

    def backgrnd_func(*a, **kw):
        threading.Thread(target=f, args=a, kwargs=kw).start()

    return backgrnd_func
