# IDE Integration Setup Instructions

## Prerequisites

To enable Gemini integration in your IDE (GitHub Copilot), you need to install Node.js first.

### 1. Install Node.js

**Option A: Using Homebrew (Recommended for macOS)**

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Node.js
brew install node
```

**Option B: Download from official website**

Visit https://nodejs.org/ and download the LTS version for macOS.

### 2. Verify Installation

After installing Node.js, verify the installation:

```bash
node --version
npm --version
npx --version
```

### 3. Install Gemini Skills

Once Node.js is installed, run:

```bash
npx skills add google-gemini/gemini-skills --skill gemini-api-dev
```

### 4. Configure MCP for Gemini Docs

Add the following to your MCP configuration file:

**Location:** `~/.config/claude/mcp_settings.json` (or your IDE's MCP config file)

```json
{
  "mcpServers": {
    "gemini-docs": {
      "command": "npx",
      "args": ["-y", "gemini-docs-mcp"]
    }
  }
}
```

### 5. Restart Your IDE

After completing the above steps, restart your IDE to load the Gemini integration.

---

## What This Enables

- **Gemini API Development**: Access to Gemini API documentation and code snippets directly in your IDE
- **AI-Powered Coding**: Enhanced coding assistance using Gemini models
- **Documentation Access**: Quick access to Gemini API docs through MCP

---

## Troubleshooting

**Issue: Command not found errors**
- Make sure Node.js is properly installed
- Restart your terminal after installation
- Check PATH environment variable includes Node.js

**Issue: MCP server not connecting**
- Verify the MCP config file path is correct
- Check file permissions
- Review IDE logs for connection errors

**Need Help?**
Visit: https://ai.google.dev/gemini-api/docs
