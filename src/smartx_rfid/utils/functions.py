import asyncio
from typing import Callable, Any, Awaitable, Union


async def delayed_function(func: Union[Callable, Awaitable], delay: float, *args, **kwargs) -> Any:
    """
    Executes a function or coroutine after a specified delay, always asynchronously.
    :param func: Synchronous function or coroutine to be executed
    :param delay: Delay time in seconds
    :param args: Positional arguments for the function
    :param kwargs: Keyword arguments for the function
    :return: The result of the function or coroutine
    """
    await asyncio.sleep(delay)
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)
