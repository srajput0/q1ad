from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import queue
from typing import Dict, Optional
from telegram.ext import CallbackContext
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class QuizTask:
    chat_id: str
    category: str
    context: CallbackContext
    priority: int = 1
    timestamp: float = datetime.now().timestamp()

class QuizThreadManager:
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.quiz_queue = queue.PriorityQueue()
        self.active_chats: Dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
    
    def schedule_quiz(self, chat_id: str, context: CallbackContext, category: str, priority: int = 1):
        """Schedule a quiz to be sent via the thread pool"""
        task = QuizTask(chat_id=chat_id, context=context, category=category, priority=priority)
        self.quiz_queue.put((priority, task))
        
        with self.lock:
            if chat_id not in self.active_chats:
                self.active_chats[chat_id] = threading.Event()
    
    def _process_queue(self):
        """Process queued quiz tasks"""
        while self.is_running:
            try:
                _, task = self.quiz_queue.get(timeout=1)
                self.executor.submit(self._send_quiz_task, task)
                self.quiz_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing quiz queue: {e}")
    
    def _send_quiz_task(self, task: QuizTask):
        """Execute the quiz sending task"""
        try:
            from quiz_handler import send_quiz_logic  # Import here to avoid circular import
            send_quiz_logic(task.context, task.chat_id)
        except Exception as e:
            logger.error(f"Error sending quiz to chat {task.chat_id}: {e}")
        finally:
            with self.lock:
                if task.chat_id in self.active_chats:
                    self.active_chats[task.chat_id].set()
    
    def stop(self):
        """Stop the thread manager and cleanup"""
        self.is_running = False
        self.worker_thread.join()
        self.executor.shutdown(wait=True)
    
    def is_chat_active(self, chat_id: str) -> bool:
        """Check if a chat is currently being processed"""
        with self.lock:
            return chat_id in self.active_chats
    
    def wait_for_chat(self, chat_id: str, timeout: Optional[float] = None) -> bool:
        """Wait for a chat's quiz to complete"""
        with self.lock:
            event = self.active_chats.get(chat_id)
            if not event:
                return True
        return event.wait(timeout=timeout)
