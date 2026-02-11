import json
import logging
from pathlib import Path
from typing import Dict
import time
import hashlib

class InterAgentMessage:
    """Send messages between agents"""
    
    def __init__(self, queue_dir: str = None):
        self.queue_dir = Path(queue_dir) if queue_dir else Path.home() / ".cache" / "novotechno-collections" / "queues"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.dedupe_window = 86400  # 24 hours
    
    def send(self, recipient: str, message: Dict):
        """Queue message for delivery"""
        queue_file = self.queue_dir / f"{recipient}.jsonl"
        
        # Check deduplication
        if self._is_duplicate(message):
            self.logger.debug(f"⏭️ Duplicate message skipped: {message.get('type', 'unknown')}")
            return
        
        # Write to queue
        try:
            with open(queue_file, 'a') as f:
                f.write(json.dumps({
                    **message,
                    "_queued_at": time.time()
                }) + "\n")
            
            self.logger.info(f"📨 Message queued for {recipient}: {message.get('type', 'unknown')}")
        except Exception as e:
            self.logger.error(f"❌ Failed to queue message: {e}")
    
    def receive(self, recipient: str) -> list:
        """Receive all messages for recipient"""
        queue_file = self.queue_dir / f"{recipient}.jsonl"
        
        if not queue_file.exists():
            return []
        
        messages = []
        try:
            with open(queue_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            messages.append(msg)
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Invalid JSON in queue: {e}")
            
            # Clear queue after reading
            queue_file.unlink()
            self.logger.info(f"📥 Received {len(messages)} messages for {recipient}")
        except Exception as e:
            self.logger.error(f"❌ Failed to receive messages: {e}")
        
        return messages
    
    def peek(self, recipient: str) -> list:
        """Peek at messages without removing them"""
        queue_file = self.queue_dir / f"{recipient}.jsonl"
        
        if not queue_file.exists():
            return []
        
        messages = []
        try:
            with open(queue_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            messages.append(msg)
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Invalid JSON in queue: {e}")
        except Exception as e:
            self.logger.error(f"❌ Failed to peek messages: {e}")
        
        return messages
    
    def _is_duplicate(self, message: Dict) -> bool:
        """Check if message was sent in deduplication window"""
        try:
            msg_hash = self._hash_message(message)
            dedupe_file = self.queue_dir / f"dedupe_{msg_hash}.json"
            
            if dedupe_file.exists():
                age = time.time() - dedupe_file.stat().st_mtime
                if age < self.dedupe_window:
                    return True
                dedupe_file.unlink()
            
            # Record message
            with open(dedupe_file, 'w') as f:
                f.write(json.dumps(message))
            
            return False
        except Exception as e:
            self.logger.warning(f"Error checking duplicate: {e}")
            return False
    
    def _hash_message(self, message: Dict) -> str:
        """Create hash for deduplication"""
        try:
            content = f"{message.get('type')}:{message.get('invoice')}:{message.get('client')}"
            return hashlib.md5(content.encode()).hexdigest()
        except Exception as e:
            self.logger.warning(f"Error hashing message: {e}")
            # Fallback to timestamp-based hash
            return hashlib.md5(str(time.time()).encode()).hexdigest()