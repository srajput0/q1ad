from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import queue
import time
import psutil
import asyncio
from typing import Dict, Optional, List, Union
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
    retries: int = 0
    max_retries: int = 3

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
        self.stats = {
            'total_sent': 0,
            'failed_attempts': 0,
            'retry_success': 0
        }
        self.accepting_new = True
        self.worker_thread.start()
        logger.info("QuizThreadManager initialized with %d workers", max_workers)

    def pause_new_quizzes(self, duration: int = 60):
        """Temporarily pause accepting new quizzes"""
        self.accepting_new = False
        threading.Timer(duration, self._resume_new_quizzes).start()
        logger.info(f"Paused new quizzes for {duration} seconds")

    def _resume_new_quizzes(self):
        """Resume accepting new quizzes"""
        self.accepting_new = True
        logger.info("Resumed accepting new quizzes")

    async def schedule_quiz_batch(self, tasks: List[QuizTask]):
        """Schedule a batch of quizzes with rate limiting and monitoring"""
        if not self.accepting_new:
            logger.warning("Not accepting new quizzes at the moment")
            return

        # Monitor queue size
        if self.quiz_queue.qsize() > 5000:  # Warning threshold
            logger.warning(f"Queue size exceeds 5000: {self.quiz_queue.qsize()}")
            
        for task in tasks:
            current_time = time.time()
            if current_time - self.last_sent < 1/self.rate_limit:
                await asyncio.sleep(1/self.rate_limit - (current_time - self.last_sent))
                
            try:
                self.quiz_queue.put((task.priority, task))
                self.last_sent = time.time()
                
                with self.lock:
                    if task.chat_id not in self.active_chats:
                        self.active_chats[task.chat_id] = threading.Event()
                        
            except Exception as e:
                logger.error(f"Error scheduling quiz for chat {task.chat_id}: {e}")

    def _process_queue(self):
        """Process queued quiz tasks with memory management and monitoring"""
        while self.is_running:
            try:
                tasks = []
                # Collect batch_size tasks or wait for 1 second
                batch_start = time.time()
                
                while len(tasks) < self.batch_size:
                    try:
                        _, task = self.quiz_queue.get(timeout=1)
                        tasks.append(task)
                    except queue.Empty:
                        break

                if tasks:
                    # Monitor batch processing time
                    process_start = time.time()
                    
                    # Process batch with error handling
                    for task in tasks:
                        future = self.executor.submit(self._send_quiz_task, task)
                        future.add_done_callback(self._handle_task_result)
                        self.quiz_queue.task_done()
                    
                    # Performance monitoring
                    batch_time = time.time() - process_start
                    if batch_time > 5:  # Warning threshold
                        logger.warning(f"Batch processing took {batch_time:.2f} seconds")
                    
                    # Memory cleanup after large batches
                    if len(tasks) >= self.batch_size:
                        import gc
                        gc.collect()
                
            except Exception as e:
                logger.error(f"Error in queue processing: {e}")
                time.sleep(1)  # Prevent tight error loops

    def _handle_task_result(self, future):
        """Handle the result of a quiz task"""
        try:
            result = future.result()
            if result:
                self.stats['total_sent'] += 1
                if result.get('was_retry'):
                    self.stats['retry_success'] += 1
        except Exception as e:
            self.stats['failed_attempts'] += 1
            logger.error(f"Task execution failed: {e}")

    def _send_quiz_task(self, task: QuizTask) -> Dict[str, Union[bool, bool]]:
        """Execute the quiz sending task with retries and error handling"""
        try:
            from quiz_handler import send_quiz_logic
            
            # Add exponential backoff for retries
            retry_delay = 1
            while task.retries < task.max_retries:
                try:
                    send_quiz_logic(task.context, task.chat_id)
                    return {'success': True, 'was_retry': task.retries > 0}
                except Exception as e:
                    task.retries += 1
                    if task.retries < task.max_retries:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        logger.warning(f"Retry {task.retries} for chat {task.chat_id}: {e}")
                    else:
                        raise
                        
            raise Exception(f"Max retries ({task.max_retries}) exceeded")
            
        except Exception as e:
            logger.error(f"Error sending quiz to chat {task.chat_id}: {e}")
            return {'success': False, 'was_retry': task.retries > 0}
        finally:
            with self.lock:
                if task.chat_id in self.active_chats:
                    self.active_chats[task.chat_id].set()

    def clear_queue(self):
        """Clear the quiz queue in emergency situations"""
        cleared_count = 0
        while not self.quiz_queue.empty():
            try:
                self.quiz_queue.get_nowait()
                cleared_count += 1
            except queue.Empty:
                break
        logger.warning(f"Cleared {cleared_count} items from quiz queue")

    def clear_caches(self):
        """Clear internal caches"""
        with self.lock:
            self.active_chats.clear()
        logger.info("Cleared internal caches")

    def pause_all_operations(self):
        """Pause all operations in emergency situations"""
        self.is_running = False
        self.clear_queue()
        self.executor.shutdown(wait=False)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.is_running = True
        logger.warning("Paused and reset all operations")

    def get_stats(self):
        """Get detailed statistics about the thread manager"""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            'active_threads': len(self.executor._threads),
            'queued_tasks': self.quiz_queue.qsize(),
            'active_chats': len(self.active_chats),
            'memory_usage_mb': memory_info.rss / (1024 * 1024),
            'cpu_percent': process.cpu_percent(),
            'total_sent': self.stats['total_sent'],
            'failed_attempts': self.stats['failed_attempts'],
            'retry_success': self.stats['retry_success'],
            'accepting_new': self.accepting_new
        }

    def stop(self):
        """Stop the thread manager and cleanup"""
        logger.info("Stopping QuizThreadManager...")
        self.is_running = False
        self.worker_thread.join(timeout=30)
        self.executor.shutdown(wait=True)
        logger.info("QuizThreadManager stopped successfully")

        
# Initialize the quiz thread manager with optimal workers for 8GB RAM
quiz_thread_manager = QuizThreadManager(max_workers=8)
