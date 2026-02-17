#!/bin/bash
# Setup and quick test script for Copilot Proxy Python

set -e

echo "🚀 Copilot Proxy Python - Setup Script"
echo "======================================"
echo ""

cd "$(dirname "$0")"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed"
    echo "Install from: https://github.com/astral-sh/uv"
    exit 1
fi

echo "✓ uv found: $(uv --version)"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
uv sync
echo "✓ Dependencies installed"
echo ""

# Run basic tests
echo "🧪 Running basic tests..."
uv run python test_basic.py
echo ""

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo ""
echo "1. 🔐 Authenticate with GitHub:"
echo "   uv run run_proxy.py authenticate"
echo ""
echo "2. 🚀 Start the server:"
echo "   uv run run_proxy.py start-server --verbose"
echo ""
echo "3. ✅ Test endpoints:"
echo "   curl http://localhost:4141/health"
echo "   curl http://localhost:4141/v1/models"
echo ""
echo "4. 📖 View documentation:"
echo "   cat README.md"
echo "   cat IMPLEMENTATION.md"
echo ""
