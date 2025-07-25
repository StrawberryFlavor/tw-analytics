"""Enhanced async task executor for running async tasks in sync context."""

import asyncio
import threading
from typing import Any, Coroutine, Optional
import logging
from concurrent.futures import Future, TimeoutError
import weakref


class AsyncRunner:
    """Thread-safe async task executor with enhanced error handling."""
    
    _instances = weakref.WeakValueDictionary()
    _lock = threading.Lock()
    
    def __init__(self, name: str = "default"):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._start_event_loop()
    
    @classmethod
    def get_instance(cls, name: str = "default") -> "AsyncRunner":
        """Get or create AsyncRunner instance by name."""
        with cls._lock:
            if name not in cls._instances:
                cls._instances[name] = cls(name)
            return cls._instances[name]
    
    def _start_event_loop(self):
        """Start event loop in separate thread."""
        def run_loop():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self.logger.info(f"AsyncRunner '{self.name}' event loop started")
                self._loop.run_forever()
            except Exception as e:
                self.logger.error(f"Event loop error in '{self.name}': {e}")
            finally:
                self.logger.info(f"AsyncRunner '{self.name}' event loop stopped")
        
        self._thread = threading.Thread(
            target=run_loop, 
            name=f"AsyncRunner-{self.name}",
            daemon=True
        )
        self._thread.start()
        
        # Wait for event loop to start
        max_wait = 5.0  # seconds
        wait_interval = 0.01
        waited = 0
        
        while (self._loop is None or not self._loop.is_running()) and waited < max_wait:
            threading.Event().wait(wait_interval)
            waited += wait_interval
        
        if self._loop is None or not self._loop.is_running():
            raise RuntimeError(f"Failed to start event loop for AsyncRunner '{self.name}'")
    
    def run(self, coro: Coroutine, timeout: Optional[float] = None) -> Any:
        """
        Run coroutine in event loop and return result.
        
        Args:
            coro: Coroutine to run
            timeout: Optional timeout in seconds
            
        Returns:
            Result of the coroutine
            
        Raises:
            RuntimeError: If event loop is not running
            TimeoutError: If operation times out
            Exception: Any exception raised by the coroutine
        """
        if not self._loop or not self._loop.is_running():
            raise RuntimeError(f"Event loop not running for AsyncRunner '{self.name}'")
        
        if self._shutdown_event.is_set():
            raise RuntimeError(f"AsyncRunner '{self.name}' is shutting down")
        
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=timeout)
        except TimeoutError:
            self.logger.warning(f"Operation timed out after {timeout}s in '{self.name}'")
            raise
        except Exception as e:
            self.logger.error(f"Error running coroutine in '{self.name}': {e}")
            raise
    
    def run_async(self, coro: Coroutine) -> Future:
        """
        Run coroutine asynchronously and return Future.
        
        Args:
            coro: Coroutine to run
            
        Returns:
            Future object that can be used to get the result
        """
        if not self._loop or not self._loop.is_running():
            raise RuntimeError(f"Event loop not running for AsyncRunner '{self.name}'")
        
        return asyncio.run_coroutine_threadsafe(coro, self._loop)
    
    def is_running(self) -> bool:
        """Check if the runner is active."""
        return (
            self._loop is not None and 
            self._loop.is_running() and 
            not self._shutdown_event.is_set()
        )
    
    def shutdown(self, timeout: float = 5.0):
        """
        Gracefully shutdown the async runner.
        
        Args:
            timeout: Maximum time to wait for shutdown
        """
        if self._shutdown_event.is_set():
            return
        
        self._shutdown_event.set()
        
        if self._loop and self._loop.is_running():
            self.logger.info(f"Shutting down AsyncRunner '{self.name}'...")
            
            # Stop the event loop
            self._loop.call_soon_threadsafe(self._loop.stop)
            
            # Wait for thread to finish
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
                
                if self._thread.is_alive():
                    self.logger.warning(f"AsyncRunner '{self.name}' thread did not stop within timeout")
                else:
                    self.logger.info(f"AsyncRunner '{self.name}' shutdown complete")


# Global default instance
_default_runner: Optional[AsyncRunner] = None
_default_lock = threading.Lock()


def get_async_runner(name: str = "default") -> AsyncRunner:
    """
    Get the async runner instance.
    
    Args:
        name: Name of the runner instance
        
    Returns:
        AsyncRunner instance
    """
    global _default_runner
    
    if name == "default":
        with _default_lock:
            if _default_runner is None:
                _default_runner = AsyncRunner("default")
            return _default_runner
    else:
        return AsyncRunner.get_instance(name)