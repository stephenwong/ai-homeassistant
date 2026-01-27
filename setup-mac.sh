#!/bin/bash

# Home Assistant Configuration Management - Mac Setup Script
# This script sets up everything you need to get started

set -e  # Exit on any error

echo "🏠 Home Assistant Configuration Management - Mac Setup"
echo "=================================================="
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ This script is for macOS only. Please use setup-windows.bat for Windows."
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo "🔍 Checking prerequisites..."

# Check if Python 3.8+ is available
if ! command_exists python3; then
    echo "❌ Python 3 is not installed."
    echo "Please install Python from https://www.python.org/downloads/"
    echo "Or use Homebrew: brew install python3"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo "❌ Python $PYTHON_VERSION found, but Python 3.8+ is required."
    echo "Please upgrade Python from https://www.python.org/downloads/"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION found"

# Check if git is available
if ! command_exists git; then
    echo "❌ Git is not installed."
    echo "Installing Command Line Tools (includes git)..."
    xcode-select --install
    echo "Please run this script again after installation completes."
    exit 1
fi

echo "✅ Git found"

# Check if make is available
if ! command_exists make; then
    echo "❌ Make is not installed."
    echo "Installing Command Line Tools (includes make)..."
    xcode-select --install
    echo "Please run this script again after installation completes."
    exit 1
fi

echo "✅ Make found"

# Check if ssh is available
if ! command_exists ssh; then
    echo "❌ SSH is not available. This is unusual for macOS."
    exit 1
fi

echo "✅ SSH found"

echo ""
echo "🐍 Setting up Python environment..."

# Check if uv is available
if ! command_exists uv; then
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "✅ uv found"

# Install dependencies
echo "Installing Python dependencies..."
uv sync

echo ""
echo "🔍 Verifying Python environment..."

# Verify critical dependencies are importable
VERIFY_FAILED=false

uv run python3 -c "import yaml" 2>/dev/null || { echo "❌ PyYAML not installed correctly"; VERIFY_FAILED=true; }
uv run python3 -c "import voluptuous" 2>/dev/null || { echo "❌ Voluptuous not installed correctly"; VERIFY_FAILED=true; }
uv run python3 -c "import jsonschema" 2>/dev/null || { echo "❌ jsonschema not installed correctly"; VERIFY_FAILED=true; }
uv run python3 -c "import requests" 2>/dev/null || { echo "❌ requests not installed correctly"; VERIFY_FAILED=true; }

if [ "$VERIFY_FAILED" = true ]; then
    echo ""
    echo "⚠️  Some dependencies failed to install. Try running:"
    echo "   uv sync"
    echo ""
else
    echo "✅ All Python dependencies verified"
fi

echo ""
echo "🔧 Checking project setup..."

# Check if Makefile exists
if [ ! -f "Makefile" ]; then
    echo "❌ Makefile not found. Are you in the correct directory?"
    exit 1
fi

echo "✅ Makefile found"

# Check if Claude Code is available
if command_exists claude; then
    echo "✅ Claude Code found"
else
    echo "⚠️  Claude Code not found"
    echo ""
    echo "Installing Claude Code via Homebrew (recommended)..."

    if command_exists brew; then
        echo "Homebrew found, installing Claude Code..."
        brew install --cask claude

        if [ $? -eq 0 ]; then
            echo "✅ Claude Code installed successfully!"
            echo ""
            echo "Please open Claude from your Applications folder to complete setup,"
            echo "then re-run this script: ./setup-mac.sh"
            exit 0
        else
            echo "❌ Homebrew installation failed"
        fi
    else
        echo "Homebrew not found."
    fi

    echo ""
    echo "📱 Please install Claude Code manually:"
    echo ""
    echo "Option 1 - Homebrew (recommended):"
    echo "   brew install --cask claude"
    echo ""
    echo "Option 2 - Download from website:"
    echo "   Visit: https://claude.com/solutions/coding"
    echo "   Download and install the macOS app"
    echo ""
    echo "After installation:"
    echo "1. Open Claude from Applications and complete setup"
    echo "2. Re-run this script: ./setup-mac.sh"
    echo ""
    echo "Note: You need a Claude Pro/Max subscription or API access."
    exit 0
fi

echo ""
echo "⚙️  Home Assistant Configuration"
echo "==============================="
echo ""
echo "Let's configure your Home Assistant connection!"
echo ""

# Get Home Assistant host
read -p "Enter your Home Assistant hostname or IP address (e.g., homeassistant.local or 192.168.1.100): " HA_HOST
while [ -z "$HA_HOST" ]; do
    echo "❌ Hostname/IP cannot be empty"
    read -p "Enter your Home Assistant hostname or IP address: " HA_HOST
done

echo ""
echo "Testing connection to $HA_HOST..."
if ping -c 1 "$HA_HOST" >/dev/null 2>&1; then
    echo "✅ Host $HA_HOST is reachable"
else
    echo "⚠️  Warning: Cannot reach $HA_HOST - please verify the address"
    read -p "Continue anyway? (y/N): " continue_setup
    if [[ ! "$continue_setup" =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Please check your Home Assistant address and try again."
        exit 1
    fi
fi

echo ""
echo "🔑 SSH Configuration"
echo "==================="
echo ""
echo "For secure access, this tool uses SSH keys. Do you have SSH access configured?"
echo ""
echo "Options:"
echo "1. I already have SSH key access configured"
echo "2. I need help setting up SSH keys"
echo "3. Skip SSH setup for now (manual configuration later)"
echo ""
read -p "Choose option (1-3): " ssh_option

case $ssh_option in
    1)
        # Test SSH connection
        echo ""
        echo "Testing SSH connection to $HA_HOST..."
        if ssh -o ConnectTimeout=5 -o BatchMode=yes "$HA_HOST" exit >/dev/null 2>&1; then
            echo "✅ SSH connection successful!"
            SSH_CONFIGURED=true
        else
            echo "❌ SSH connection failed"
            echo "Please check your SSH configuration and try again"
            echo "Common issues:"
            echo "- SSH keys not added to Home Assistant"
            echo "- Incorrect hostname/IP"
            echo "- SSH addon not enabled in Home Assistant"
            SSH_CONFIGURED=false
        fi
        ;;
    2)
        echo ""
        echo "📚 SSH Setup Help"
        echo "================="
        echo ""
        echo "To set up SSH access to Home Assistant:"
        echo ""
        echo "1. Install the 'SSH & Web Terminal' add-on in Home Assistant"
        echo "2. Generate an SSH key pair if you don't have one:"
        echo "   ssh-keygen -t ed25519 -C \"your-email@example.com\""
        echo ""
        echo "3. Copy your public key to Home Assistant:"
        echo "   ssh-copy-id -i ~/.ssh/id_ed25519.pub root@$HA_HOST"
        echo ""
        echo "4. Test the connection:"
        echo "   ssh root@$HA_HOST"
        echo ""
        echo "For detailed instructions, visit:"
        echo "https://github.com/home-assistant/addons/blob/master/ssh/DOCS.md"
        echo ""
        SSH_CONFIGURED=false
        ;;
    3)
        echo ""
        echo "⏭️  Skipping SSH setup - you can configure this later"
        SSH_CONFIGURED=false
        ;;
    *)
        echo "Invalid option. Skipping SSH setup."
        SSH_CONFIGURED=false
        ;;
esac

# Update Makefile with the provided host
echo ""
echo "📝 Updating Makefile configuration..."
if [ -f "Makefile" ]; then
    # Create backup
    cp Makefile Makefile.backup

    # Update HA_HOST in Makefile
    sed -i.bak "s/^HA_HOST = .*/HA_HOST = $HA_HOST/" Makefile && rm Makefile.bak
    echo "✅ Makefile updated with HA_HOST = $HA_HOST"
else
    echo "❌ Makefile not found - you may need to configure manually"
fi

echo ""
echo "🎉 Setup Complete!"
echo "=================="
echo ""
echo "Configuration Summary:"
echo "- Home Assistant Host: $HA_HOST"
if [ "$SSH_CONFIGURED" = true ]; then
    echo "- SSH Access: ✅ Configured and tested"
else
    echo "- SSH Access: ⚠️  Needs configuration"
fi
echo ""
echo "Next steps:"
if [ "$SSH_CONFIGURED" = true ]; then
    echo "1. Pull your actual configuration:"
    echo "   make pull"
    echo ""
    echo "2. Start creating automations with Claude Code!"
else
    echo "1. Complete SSH setup (see instructions above)"
    echo "2. Pull your actual configuration: make pull"
    echo "3. Start creating automations with Claude Code!"
fi
echo ""
echo "For detailed instructions, see the README.md file."
echo ""
echo "Need help? Check the troubleshooting section in README.md"
echo "or create an issue at: https://github.com/philippb/claude-homeassistant/issues"
