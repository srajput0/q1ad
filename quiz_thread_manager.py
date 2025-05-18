from concurrent.futures import ThreadPoolExecutor
import queue
import logging
import time
import threading
from typing import Dict, Any
import psutil

logger = logging.getLogger(__name__)

class QuizThreadManager:
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.task_queue = queue.PriorityQueue()
        self.is_running = True
        self.stats = {
            'total_sent': 0,
            'failed_attempts': 0,
            'retry_success': 0,
            'active_threads': 0,
            'queued_tasks': 0,
            'active_chats': set(),
            'memory_usage_mb': 0,
            'cpu_percent': 0,
            'accepting_new': True
        }
        self.lock = threading.Lock()
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        logger.info(f"QuizThreadManager initialized with {max_workers} workers")

    def schedule_quiz(self, chat_id: str, context: Any, category: str, priority: int = 1) -> bool:
        """Schedule a quiz to be sent"""
        try:
            if not self.is_running:
                logger.warning("Quiz thread manager is not running")
                return False

            if not self.stats['accepting_new']:
                logger.warning("Not accepting new quizzes due to high load")
                return False

            task = {
                'chat_id': chat_id,
                'context': context,
                'category': category,
                'timestamp': time.time()
            }

            self.task_queue.put((priority, task))
            with self.lock:
                self.stats['queued_tasks'] = self.task_queue.qsize()
                self.stats['active_chats'].add(chat_id)

            logger.info(f"Scheduled quiz for chat {chat_id} with priority {priority}")
            return True

        except Exception as e:
            logger.error(f"Error scheduling quiz: {e}")
            return False

    def _process_queue(self):
        """Process queued quiz tasks"""
        while self.is_running:
            try:
                # Get task from queue
                priority, task = self.task_queue.get(timeout=1)
                
                # Update stats
                with self.lock:
                    self.stats['active_threads'] = len(self.executor._threads)
                    self.stats['queued_tasks'] = self.task_queue.qsize()
                    
                # Monitor system resources
                process = psutil.Process()
                memory_info = process.memory_info()
                self.stats['memory_usage_mb'] = memory_info.rss / (1024 * 1024)
                self.stats['cpu_percent'] = process.cpu_percent()
                
                # Check if we should accept new tasks
                self.stats['accepting_new'] = (
                    self.stats['memory_usage_mb'] < 7000 and  # Less than 7GB
                    self.stats['queued_tasks'] < 1000 and     # Less than 1000 queued
                    len(self.executor._threads) < self.executor._max_workers
                )

                # Execute the quiz sending
                future = self.executor.submit(
                    self._send_quiz,
                    task['chat_id'],
                    task['context'],
                    task['category']
                )
                
                # Handle completion
                future.add_done_callback(self._task_complete)

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing queue: {e}")
                time.sleep(1)

    def _send_quiz(self, chat_id: str, context: Any, category: str) -> bool:
        """Execute quiz sending"""
        from quiz_handler import send_quiz_logic  # Import here to avoid circular import
        
        try:
            result = send_quiz_logic(context, chat_id)
            
            with self.lock:
                if result:
                    self.stats['total_sent'] += 1
                else:
                    self.stats['failed_attempts'] += 1
                    
            return result
            
        except Exception as e:
            logger.error(f"Error sending quiz to {chat_id}: {e}")
            with self.lock:
                self.stats['failed_attempts'] += 1
            return False

    def _task_complete(self, future):
        """Handle task completion"""
        try:
            result = future.result()
            if result:
                logger.debug("Quiz task completed successfully")
            else:
                logger.warning("Quiz task failed")
        except Exception as e:
            logger.error(f"Error in quiz task: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        with self.lock:
            return {
                'total_sent': self.stats['total_sent'],
                'failed_attempts': self.stats['failed_attempts'],
                'retry_success': self.stats['retry_success'],
                'active_threads': len(self.executor._threads),
                'queued_tasks': self.task_queue.qsize(),
                'active_chats': len(self.stats['active_chats']),
                'memory_usage_mb': self.stats['memory_usage_mb'],
                'cpu_percent': self.stats['cpu_percent'],
                'accepting_new': self.stats['accepting_new']
            }

    def stop(self):
        """Stop the thread manager"""
        logger.info("Stopping QuizThreadManager...")
        self.is_running = False
        self.worker_thread.join(timeout=30)
        self.executor.shutdown(wait=True)
        logger.info("QuizThreadManager stopped")
