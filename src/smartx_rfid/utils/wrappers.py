import time
import logging
import functools
import asyncio
from typing import Callable, Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def elapsed_time(func: F) -> F:
    """
    Wrapper para medir e logar o tempo de execução de funções sync e async.
    Adiciona o campo 'elapsed_time' no log.
    """
    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                logging.info(f"[elapsed] {func.__qualname__} - {elapsed}", extra={"elapsed_time": elapsed})

        return async_wrapper  # type: ignore
    else:

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                logging.info(f"[elapsed] {func.__qualname__} - {elapsed}", extra={"elapsed_time": elapsed})

        return sync_wrapper  # type: ignore
