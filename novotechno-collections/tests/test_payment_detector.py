import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json
import logging

from src.filesystem.payment_detector import PaymentDetector, PaymentEventHandler
from src.filesystem.payment_checker import PaymentConfidenceChecker

class TestPaymentEventHandler:
    """Test PaymentEventHandler class"""
    
    @pytest.fixture
    def handler(self):
        """Create handler with mocked dependencies"""
        state_manager = Mock()
        confidence_checker = Mock()
        return PaymentEventHandler(state_manager, confidence_checker)
    
    @pytest.fixture
    def temp_file(self):
        """Create a temporary file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
            f.write("test payment content")
            temp_path = f.name
        yield temp_path
        Path(temp_path).unlink(missing_ok=True)
    
    def test_is_payment_file_matching_patterns(self, handler):
        """Test payment file pattern detection"""
        # Test matching patterns
        assert handler._is_payment_file("/path/to/pagado_factura_123.pdf")
        assert handler._is_payment_file("/path/to/payment_confirmation.pdf")
        assert handler._is_payment_file("/path/to/recibo_cliente.pdf")
        assert handler._is_payment_file("/path/to/paid_invoice_456.pdf")
        
        # Test non-matching files
        assert not handler._is_payment_file("/path/to/document.pdf")
        assert not handler._is_payment_file("/path/to/image.jpg")
        assert not handler._is_payment_file("/path/to/readme.txt")
    
    def test_hash_file(self, handler, temp_file):
        """Test file hashing"""
        file_hash = handler._hash_file(temp_file)
        assert isinstance(file_hash, str)
        assert len(file_hash) == 32  # MD5 hash length
        
        # Same file should produce same hash
        file_hash2 = handler._hash_file(temp_file)
        assert file_hash == file_hash2
    
    def test_is_duplicate_detection(self, handler):
        """Test duplicate detection"""
        file_hash = "test_hash_123"
        
        # First time should not be duplicate
        assert not handler._is_duplicate(file_hash)
        
        # Second time within 24h should be duplicate
        assert handler._is_duplicate(file_hash)
        
        # After resetting time (simulating old entry), should not be duplicate
        handler.recent_files[file_hash] = time.time() - 90000  # 25 hours ago
        assert not handler._is_duplicate(file_hash)
    
    def test_process_payment_file_success(self, handler, temp_file):
        """Test successful payment file processing"""
        # Mock dependencies
        handler.check_confidence.return_value = {
            "matches_invoice": True,
            "client": "Test Client",
            "invoice_number": "INV-001",
            "amount": 1000.00,
            "method": "transfer"
        }
        handler.state.mark_paid.return_value = True
        handler.state.archive_invoice.return_value = "/archive/path/inv-001.pdf"
        
        # Process file
        handler._process_payment_file(temp_file)
        
        # Verify calls
        handler.check_confidence.assert_called_once_with(temp_file)
        handler.state.mark_paid.assert_called_once()
        handler.state.archive_invoice.assert_called_once()
    
    def test_process_payment_file_no_match(self, handler, temp_file):
        """Test payment file that doesn't match any invoice"""
        # Mock no match
        handler.check_confidence.return_value = {
            "matches_invoice": False,
            "source_file": temp_file
        }
        
        # Process file
        handler._process_payment_file(temp_file)
        
        # Verify no state changes
        handler.check_confidence.assert_called_once()
        handler.state.mark_paid.assert_not_called()
        handler.state.archive_invoice.assert_not_called()
    
    def test_notify_emailer(self, handler):
        """Test emailer notification - simplified version"""
        # Mock Path.home() to return a temp directory
        with patch('src.filesystem.payment_detector.Path') as mock_path_class:
            # Create a mock that returns our temp directory for home()
            with tempfile.TemporaryDirectory() as tmpdir:
                mock_home = Path(tmpdir)
                mock_path_class.home.return_value = mock_home
                
                # The actual Path() calls in the code need to work
                # Send notification
                handler._notify_emailer("INV-123", "Test Client")
                
                # Check if file was created in the expected location
                expected_file = mock_home / ".cache" / "novotechno-collections" / "payment_queue.json"
                
                # Verify file was created with correct content
                assert expected_file.exists(), f"Queue file not created at {expected_file}"
                content = expected_file.read_text()
                assert "INVOICE_PAID" in content
                assert "INV-123" in content
                assert "Test Client" in content

class TestPaymentDetector:
    """Test PaymentDetector class"""
    
    @pytest.fixture
    def detector(self):
        """Create detector with mocked dependencies"""
        state_manager = Mock()
        confidence_checker = Mock()
        return PaymentDetector(state_manager, confidence_checker)
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_start_watching_paths(self, detector, temp_dir):
        """Test starting to watch paths"""
        paths = [str(temp_dir)]
        
        # Mock observer
        detector.observer.schedule = Mock()
        detector.observer.start = Mock()
        
        # Start detector
        detector.start(paths)
        
        # Verify observer was configured
        detector.observer.schedule.assert_called_once()
        detector.observer.start.assert_called_once()
    
    def test_start_with_nonexistent_path(self, detector):
        """Test starting with non-existent path"""
        paths = ["/nonexistent/path/12345"]
        
        # Mock observer
        detector.observer.schedule = Mock()
        detector.observer.start = Mock()
        
        # Start detector - should log warning but not fail
        detector.start(paths)
        
        # Verify observer was not scheduled for non-existent path
        detector.observer.schedule.assert_not_called()
        detector.observer.start.assert_called_once()
    
    def test_stop_detector(self, detector):
        """Test stopping the detector"""
        # Mock observer methods
        detector.observer.stop = Mock()
        detector.observer.join = Mock()
        
        # Stop detector
        detector.stop()
        
        # Verify observer was stopped
        detector.observer.stop.assert_called_once()
        detector.observer.join.assert_called_once()

class TestIntegration:
    """Integration tests for payment detection flow"""
    
    def test_full_payment_detection_flow(self):
        """Test complete flow from file detection to state update"""
        with tempfile.TemporaryDirectory() as watch_dir:
            # Create test components
            state_manager = Mock()
            confidence_checker = Mock()
            
            # Mock successful payment detection
            confidence_checker.return_value = {
                "matches_invoice": True,
                "client": "Integration Test",
                "invoice_number": "INT-999",
                "amount": 500.00,
                "method": "test"
            }
            
            state_manager.get_all_unpaid.return_value = [
                {"invoice_number": "INT-999", "client": "Integration Test", "amount": 500.00}
            ]
            state_manager.mark_paid.return_value = True
            state_manager.archive_invoice.return_value = "/archive/int-999.pdf"
            
            # Create detector
            detector = PaymentDetector(state_manager, confidence_checker)
            
            # Mock observer to avoid actual file watching
            with patch.object(detector.observer, 'schedule'), \
                 patch.object(detector.observer, 'start'), \
                 patch.object(detector.observer, 'stop'), \
                 patch.object(detector.observer, 'join'):
                
                # Start detector
                detector.start([watch_dir])
                
                # Simulate file creation
                handler = detector.handler
                test_file = Path(watch_dir) / "pagado_factura_INT-999_$500.pdf"
                test_file.write_text("test payment")
                
                # Simulate the event
                handler.on_created(type('Event', (), {
                    'is_directory': False,
                    'src_path': str(test_file)
                })())
                
                # Stop detector
                detector.stop()
                
                # Verify the flow
                confidence_checker.assert_called()
                state_manager.mark_paid.assert_called_once()
                state_manager.archive_invoice.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])