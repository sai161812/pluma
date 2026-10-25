"""Keep owned-desktop assertions off pytest's potentially COM-bound thread."""
from concurrent.futures import ThreadPoolExecutor
from functools import wraps


def desktop_thread(test):
    @wraps(test)
    def run(*args, **kwargs):
        # Every body completes (including its finally blocks) before the test
        # returns and pytest tears down its fixtures. No detached test branch.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='p11-desktop') as pool:
            return pool.submit(test, *args, **kwargs).result()
    return run
