#!/usr/bin/env python3
import click
import signal
import sys
import time
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from filesystem.payment_detector import PaymentDetector
from filesystem.payment_checker import PaymentConfidenceChecker
from filesystem.message_sender import InterAgentMessage
from state.ledger import Ledger

# Setup logging
def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path.home() / ".cache" / "novotechno-collections"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "payment-watcher.log")
        ]
    )

@click.command()
@click.option("--watch-path", multiple=True, help="Paths to watch for payments")
@click.option("--once", is_flag=True, help="Run once and exit")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(watch_path: tuple, once: bool, verbose: bool):
    """Payment Watcher - Real-time payment detection"""
    
    # Initialize logging
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize state manager (Ledger)
        state_manager = Ledger()
        
        # Initialize components
        confidence_checker = PaymentConfidenceChecker(state_manager)
        message_sender = InterAgentMessage()
        detector = PaymentDetector(state_manager, confidence_checker)
        
        # Default watch paths
        paths = list(watch_path) or [
            str(Path.home() / "Documents" / "Invoices" / "paid"),
            str(Path.home() / "Downloads"),
            str(Path.home() / "Desktop"),
        ]
        
        # Filter out non-existent paths (with warning)
        valid_paths = []
        for path in paths:
            if Path(path).exists():
                valid_paths.append(path)
            else:
                logger.warning(f"⚠️ Path does not exist, skipping: {path}")
        
        if not valid_paths:
            logger.error("❌ No valid watch paths provided")
            sys.exit(1)
        
        def shutdown_handler(signum, frame):
            logger.info("\n🛑 Shutting down payment watcher...")
            detector.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)
        
        click.echo(f"🚀 Payment Watcher started")
        click.echo(f"👀 Watching: {', '.join(valid_paths)}")
        
        try:
            unpaid_count = len(state_manager.list_unpaid_invoices())
            click.echo(f"📊 Monitoring {unpaid_count} unpaid invoices")
        except:
            click.echo(f"📊 Monitoring invoices (count unavailable)")
        
        logger.info(f"Payment watcher started with paths: {valid_paths}")
        
        detector.start(valid_paths)
        
        if once:
            # Just run one cycle
            logger.info("Running in --once mode")
            click.echo("💤 Running for 5 seconds then exiting...")
            time.sleep(5)
            detector.stop()
            click.echo("✅ Done")
            return
        
        # Keep running
        logger.info("Entering main monitoring loop")
        while True:
            time.sleep(60)  # Heartbeat
            try:
                unpaid_count = len(state_manager.list_unpaid_invoices())
                logger.debug(f"Heartbeat - {unpaid_count} unpaid invoices being monitored")
            except:
                logger.debug("Heartbeat - monitoring invoices")
    
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        try:
            detector.stop()
        except:
            pass
        click.echo("\n🛑 Stopped by user")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        click.echo(f"❌ Fatal error: {e}", err=True)
        try:
            detector.stop()
        except:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()