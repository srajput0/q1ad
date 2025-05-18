from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import queue
from typing import Dict, Optional
from telegram.ext import CallbackContext
from dataclasses import dataclass
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class QuizTask:
    chat_id: str
    category: str
    context: CallbackContext
    priority: int = 1
    timestamp: float = datetime.now().timestamp()

class QuizThreadManager:
    def __init__(self, max_workers: int = 8):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.quiz_queue = queue.PriorityQueue()
        self.active_chats: Dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.is_running = True
        self.batch_size = 100
        self.rate_limit = 30  # quizzes per second
        self.last_sent = time.time()
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        
    async def schedule_quiz_batch(self, tasks: List[QuizTask]):
        """Schedule a batch of quizzes with rate limiting"""
        for task in tasks:
            current_time = time.time()
            if current_time - self.last_sent < 1/self.rate_limit:
                await asyncio.sleep(1/self.rate_limit - (current_time - self.last_sent))
                
            self.quiz_queue.put((task.priority, task))
            self.last_sent = time.time()
            
            with self.lock:
                if task.chat_id not in self.active_chats:
                    self.active_chats[task.chat_id] = threading.Event()
    
    def _process_queue(self):
        """Process queued quiz tasks with memory management"""
        while self.is_running:
            try:
                tasks = []
                # Collect batch_size tasks or wait for 1 second
                while len(tasks) < self.batch_size:
                    try:
                        _, task = self.quiz_queue.get(timeout=1)
                        tasks.append(task)
                    except queue.Empty:
                        break
                
                if tasks:
                    # Process batch
                    for task in tasks:
                        self.executor.submit(self._send_quiz_task, task)
                        self.quiz_queue.task_done()
                    
                    # Memory cleanup after batch
                    if len(tasks) >= self.batch_size:
                        import gc
                        gc.collect()
                
            except Exception as e:
                logger.error(f"Error processing quiz queue: {e}")
    
    def _send_quiz_task(self, task: QuizTask):
        """Execute the quiz sending task with error handling"""
        try:
            from quiz_handler import send_quiz_logic
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
    
    def get_stats(self):
        """Get current statistics"""
        return {
            'active_threads': len(self.executor._threads),
            'queued_tasks': self.quiz_queue.qsize(),
            'active_chats': len(self.active_chats),
            'memory_usage': psutil.Process().memory_info().rss / (1024 * 1024)  # MB
        }

# Initialize the quiz thread manager with optimal workers for 8GB RAM
quiz_thread_manager = QuizThreadManager(max_workers=8)
