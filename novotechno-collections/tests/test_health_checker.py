import unittest
import json
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from supervisor.health_checker import AgentHealthStatus, HealthChecker, StateConsistencyChecker


class TestAgentHealthStatus(unittest.TestCase):
    """Test AgentHealthStatus class"""
    
    def setUp(self):
        self.agent = AgentHealthStatus("test-agent")
    
    def test_initial_state(self):
        """Test initial agent state"""
        self.assertIsNone(self.agent.last_heartbeat)
        self.assertEqual(self.agent.status, "unknown")
        self.assertEqual(self.agent.restarts, 0)
        self.assertEqual(self.agent.errors, [])
    
    def test_update_heartbeat(self):
        """Test updating heartbeat"""
        self.agent.update_heartbeat()
        self.assertIsNotNone(self.agent.last_heartbeat)
        self.assertEqual(self.agent.status, "healthy")
        self.assertEqual(self.agent.errors, [])
    
    def test_mark_unhealthy(self):
        """Test marking agent unhealthy"""
        self.agent.mark_unhealthy("Test error")
        self.assertEqual(self.agent.status, "unhealthy")
        self.assertEqual(len(self.agent.errors), 1)
        self.assertEqual(self.agent.errors[0]["reason"], "Test error")
    
    def test_is_stale(self):
        """Test stale detection"""
        # Initially should be stale (no heartbeat)
        self.assertTrue(self.agent.is_stale())
        
        # Add recent heartbeat
        self.agent.update_heartbeat()
        self.assertFalse(self.agent.is_stale())
        


class TestHealthChecker(unittest.TestCase):
    """Test HealthChecker class"""
    
    def setUp(self):
        self.agents = ["collections-emailer", "payment-watcher"]
        self.health_checker = HealthChecker(self.agents)
    
    def test_init(self):
        """Test health checker initialization"""
        self.assertEqual(len(self.health_checker.agents), 2)
        self.assertIn("collections-emailer", self.health_checker.agents)
        self.assertIn("payment-watcher", self.health_checker.agents)
        
    def test_check_all_new_agents(self):
        """Test checking all agents with no heartbeats"""
        results = self.health_checker.check_all()
        
        for agent_name, status in results.items():
            self.assertIn(agent_name, self.agents)
            # Should be unhealthy since no heartbeats
            self.assertEqual(status["status"], "unhealthy")
            self.assertIsNone(status["last_heartbeat"])
    
    def test_check_healthy_agent(self):
        """Test checking a healthy agent"""
        # Simulate a heartbeat
        self.health_checker.agents["collections-emailer"].update_heartbeat()
        
        results = self.health_checker.check_all()
        emailer_status = results["collections-emailer"]
        
        self.assertEqual(emailer_status["status"], "healthy")
        self.assertIsNotNone(emailer_status["last_heartbeat"])
        self.assertEqual(len(emailer_status["errors"]), 0)
    
    def test_check_agent_stale(self):
        """Test checking a stale agent"""
        # Update heartbeat but make it old via monkeypatch
        self.health_checker.agents["collections-emailer"].last_heartbeat = datetime.utcnow() - timedelta(hours=2)
        self.health_checker.agents["collections-emailer"].status = "healthy"
        
        # Should now be detected as stale/unhealthy
        results = self.health_checker.check_all()
        status = results["collections-emailer"]
        
        self.assertEqual(status["status"], ["unhealthy", "escalated", "restarting"][0])
        self.assertTrue(len(status["errors"]) > 0)


class TestStateConsistencyChecker(unittest.TestCase):
    """Test StateConsistencyChecker class"""
    
    def setUp(self):
        # Create temporary directory for state files
        self.temp_dir = tempfile.mkdtemp()
        self.checker = StateConsistencyChecker(self.temp_dir)
    
    def tearDown(self):
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init(self):
        """Test state consistency checker initialization"""
        self.assertEqual(self.checker.state_dir, Path(self.temp_dir))
    
    def test_reconcile_invoices_empty(self):
        """Test invoice reconciliation with empty directory"""
        result = self.checker._reconcile_invoices()
        
        self.assertEqual(result["unpaid_total"], 0)
        self.assertEqual(result["paid_total"], 0)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["errors"], [])
    
    def test_reconcile_invoices_with_data(self):
        """Test invoice reconciliation with sample data"""
        # Create sample invoice files
        invoices = [
            {"id": "inv1", "amount": 100, "status": "unpaid"},
            {"id": "inv2", "amount": 200, "status": "paid"},
            {"id": "inv3", "amount": 150, "status": "unpaid"}
        ]
        
        for i, invoice in enumerate(invoices):
            filepath = Path(self.temp_dir) / f"invoice_{i}.json"
            with open(filepath, 'w') as f:
                json.dump(invoice, f)
        
        result = self.checker._reconcile_invoices()
        
        self.assertEqual(result["unpaid_total"], 250)  # 100 + 150
        self.assertEqual(result["paid_total"], 200)
        self.assertEqual(result["error_count"], 0)
    
    def test_reconcile_invoices_malformed(self):
        """Test invoice reconciliation with malformed files"""
        # Create a malformed JSON file
        filepath = Path(self.temp_dir) / "malformed.json"
        with open(filepath, 'w') as f:
            f.write("not json")
        
        result = self.checker._reconcile_invoices()
        
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(len(result["errors"]), 1)
    
    def test_check_queue_health_no_queue(self):
        """Test queue health check when no queue exists"""
        result = self.checker._check_queue_health()
        
        self.assertTrue(result["healthy"])
        self.assertEqual(result["queues"], [])
    
    def test_reconcile_all(self):
        """Test full reconciliation"""
        result = self.checker.reconcile_all()
        
        self.assertIn("invoices", result)
        self.assertIn("ledger", result)
        self.assertIn("queue", result)
        self.assertIn("timestamp", result)
        
        # Check timestamp is valid ISO format
        datetime.fromisoformat(result["timestamp"].replace('Z', '+00:00'))


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""
    
    def test_empty_agent_list(self):
        """Test health checker with empty agent list"""
        health_checker = HealthChecker([])
        self.assertEqual(len(health_checker.agents), 0)
        
        results = health_checker.check_all()
        self.assertEqual(len(results), 0)
    
    def test_count_missed_heartbeats_no_log(self):
        """Test counting missed heartbeats when no log exists"""
        health_checker = HealthChecker(["test-agent"])
        
        # No log file means no previous checks - return 0
        count = health_checker._count_missed_heartbeats("test-agent")
        self.assertEqual(count, 0)
    
    def test_notify_caine_logs(self):
        """Test that notification logs correctly"""
        health_checker = HealthChecker(["test-agent"])
        
        # Should not raise error
        health_checker._notify_caine({"test": "message"})
    
    def test_auto_restart_logs(self):
        """Test that auto-restart logs correctly"""
        health_checker = HealthChecker(["test-agent"])
        
        # Should not raise error
        health_checker._try_auto_restart("test-agent")


class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    def test_health_check_integration(self):
        """Test complete health check flow"""
        # Create temp state dir
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Setup
            agents = ["agent1", "agent2"]
            health_checker = HealthChecker(agents)
            checker = StateConsistencyChecker(temp_dir)
            
            # Create some test data
            with open(Path(temp_dir) / "test.json", 'w') as f:
                json.dump({"amount": 100, "status": "unpaid"}, f)
            
            # Run health check
            results = health_checker.check_all()
            
            # Both should be unhealthy (no heartbeats)
            for agent_name in agents:
                self.assertEqual(results[agent_name]["status"], "unhealthy")
                self.assertGreater(len(results[agent_name]["errors"]), 0)
            
            # Run reconciliation
            consistency = checker.reconcile_all()
            self.assertIsNotNone(consistency["invoices"]["unpaid_total"])
            
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
