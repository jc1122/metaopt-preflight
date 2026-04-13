"""
Shared pytest fixtures and configuration for metaopt-preflight test suite.
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path for all tests
sys.path.insert(0, str(Path(__file__).parent))
