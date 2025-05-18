import psutil
import threading
import logging
import time
from datetime import datetime
from typing import Dict, Optional
import gc
from telegram.ext import CallbackContext
from telegram import Update

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ResourceMonitor:
    def __init__(self, quiz_thread_manager=None, broadcast_manager=None):
        """
        Initialize the resource monitor
        :param quiz_thread_manager: QuizThreadManager instance
        :param broadcast_manager: BroadcastManager instance
        """
        self.quiz_manager = quiz_thread_manager
        self.broadcast_manager = broadcast_manager
        
        # Memory thresholds (in bytes)
        self.warning_threshold = 6 * 1024 * 1024 * 1024    # 6GB
        self.critical_threshold = 7 * 1024 * 1024 * 1024   # 7GB
        self.emergency_threshold = 7.5 * 1024 * 1024 * 1024  # 7.5GB
        
        # CPU thresholds (percentage)
        self.cpu_warning = 70
        self.cpu_critical = 85
        
        # Monitoring state
        self.monitoring = True
        self.is_throttled = False
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
        
        # Performance history
        self.performance_history = []
        self.max_history_size = 100
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(
            target=self._monitor_resources, 
            daemon=True,
            name="ResourceMonitorThread"
        )
        self.monitor_thread.start()
        logger.info("Resource monitor initialized and started")

    def _monitor_resources(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                self._check_resources()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                time.sleep(60)  # Wait longer if there's an error

    def _check_resources(self):
        """Check system resources and take appropriate action"""
        process = psutil.Process()
        
        # Get memory usage
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        
        # Get CPU usage
        cpu_percent = process.cpu_percent(interval=1)
        
        # Record metrics
        self._record_performance_metrics({
            'timestamp': datetime.utcnow(),
            'memory_used': memory_info.rss,
            'memory_percent': memory_percent,
            'cpu_percent': cpu_percent,
            'thread_count': threading.active_count()
        })
        
        # Check memory thresholds
        if memory_info.rss > self.emergency_threshold:
            self._handle_emergency_memory(memory_info.rss)
        elif memory_info.rss > self.critical_threshold:
            self._handle_critical_memory(memory_info.rss)
        elif memory_info.rss > self.warning_threshold:
            self._handle_warning_memory(memory_info.rss)
        
        # Check CPU thresholds
        if cpu_percent > self.cpu_critical:
            self._handle_critical_cpu(cpu_percent)
        elif cpu_percent > self.cpu_warning:
            self._handle_warning_cpu(cpu_percent)
        
        # Regular cleanup if needed
        self._check_periodic_cleanup()

    def _handle_warning_memory(self, current_memory):
        """Handle warning level memory usage"""
        logger.warning(f"High memory usage: {current_memory / (1024**3):.2f} GB")
        
        if self.quiz_manager:
            # Reduce batch sizes
            self.quiz_manager.batch_size = max(50, self.quiz_manager.batch_size // 2)
            self.quiz_manager.rate_limit = max(20, self.quiz_manager.rate_limit - 5)
        
        if not self.is_throttled:
            self._perform_light_cleanup()

    def _handle_critical_memory(self, current_memory):
        """Handle critical level memory usage"""
        logger.error(f"Critical memory usage: {current_memory / (1024**3):.2f} GB")
        
        if self.quiz_manager:
            # Severely restrict operations
            self.quiz_manager.batch_size = 25
            self.quiz_manager.rate_limit = 10
            self.quiz_manager.pause_new_quizzes(duration=60)
        
        self._perform_full_cleanup()
        self.is_throttled = True

    def _handle_emergency_memory(self, current_memory):
        """Handle emergency level memory usage"""
        logger.critical(f"Emergency memory usage: {current_memory / (1024**3):.2f} GB")
        
        if self.quiz_manager:
            # Emergency measures
            self.quiz_manager.pause_all_operations()
            self.quiz_manager.clear_queue()
        
        self._perform_emergency_cleanup()
        
        # Log detailed memory usage
        self._log_detailed_memory_usage()

    def _handle_warning_cpu(self, cpu_percent):
        """Handle warning level CPU usage"""
        logger.warning(f"High CPU usage: {cpu_percent}%")
        
        if self.quiz_manager:
            self.quiz_manager.rate_limit = max(15, self.quiz_manager.rate_limit - 5)

    def _handle_critical_cpu(self, cpu_percent):
        """Handle critical level CPU usage"""
        logger.error(f"Critical CPU usage: {cpu_percent}%")
        
        if self.quiz_manager:
            self.quiz_manager.pause_new_quizzes(duration=30)
            self.quiz_manager.rate_limit = 10

    def _perform_light_cleanup(self):
        """Perform light cleanup operations"""
        gc.collect()
        logger.info("Performed light cleanup")

    def _perform_full_cleanup(self):
        """Perform full cleanup operations"""
        gc.collect()
        gc.collect()
        self._clear_caches()
        logger.info("Performed full cleanup")

    def _perform_emergency_cleanup(self):
        """Perform emergency cleanup operations"""
        self._perform_full_cleanup()
        if self.quiz_manager:
            self.quiz_manager.clear_queue()
        logger.warning("Performed emergency cleanup")

    def _clear_caches(self):
        """Clear various caches in the system"""
        if self.quiz_manager:
            self.quiz_manager.clear_caches()
        
        # Clear any module-level caches
        import sys
        for module in list(sys.modules.values()):
            if hasattr(module, 'cache_clear'):
                try:
                    module.cache_clear()
                except:
                    pass

    def _check_periodic_cleanup(self):
        """Check if periodic cleanup is needed"""
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._perform_light_cleanup()
            self.last_cleanup = current_time

    def _record_performance_metrics(self, metrics: Dict):
        """Record performance metrics for monitoring"""
        self.performance_history.append(metrics)
        
        # Maintain history size
        if len(self.performance_history) > self.max_history_size:
            self.performance_history.pop(0)

    def _log_detailed_memory_usage(self):
        """Log detailed memory usage information"""
        process = psutil.Process()
        
        # Memory maps
        logger.info("=== Detailed Memory Usage ===")
        for mmap in process.memory_maps():
            logger.info(f"Path: {mmap.path}, RSS: {mmap.rss / 1024 / 1024:.2f} MB")
        
        # Open files
        logger.info("=== Open Files ===")
        for file in process.open_files():
            logger.info(f"File: {file.path}, Mode: {file.mode}")
        
        # Threads
        logger.info("=== Active Threads ===")
        for thread in threading.enumerate():
            logger.info(f"Thread: {thread.name}, Daemon: {thread.daemon}")

    def get_performance_stats(self) -> Dict:
        """Get current performance statistics"""
        if not self.performance_history:
            return {}
        
        latest = self.performance_history[-1]
        return {
            'timestamp': latest['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'memory_used_gb': latest['memory_used'] / (1024**3),
            'memory_percent': latest['memory_percent'],
            'cpu_percent': latest['cpu_percent'],
            'thread_count': latest['thread_count'],
            'is_throttled': self.is_throttled
        }

    def stop(self):
        """Stop the resource monitor"""
        self.monitoring = False
        self.monitor_thread.join(timeout=5)
        logger.info("Resource monitor stopped")

# Command handler for checking performance
def check_performance(update: Update, context: CallbackContext):
    """Handler for the /performance command"""
    if not hasattr(context.bot_data, 'resource_monitor'):
        update.message.reply_text("Resource monitoring is not enabled.")
        return

    stats = context.bot_data['resource_monitor'].get_performance_stats()
    if not stats:
        update.message.reply_text("No performance data available yet.")
        return

    message = (
        "📊 *System Performance*\n\n"
        f"🕒 Time: {stats['timestamp']}\n"
        f"💾 Memory Usage: {stats['memory_used_gb']:.2f} GB ({stats['memory_percent']:.1f}%)\n"
        f"⚡ CPU Usage: {stats['cpu_percent']:.1f}%\n"
        f"🧵 Active Threads: {stats['thread_count']}\n"
        f"🚥 Status: {'⚠️ Throttled' if stats['is_throttled'] else '✅ Normal'}"
    )
    
    update.message.reply_text(message, parse_mode='Markdown')
