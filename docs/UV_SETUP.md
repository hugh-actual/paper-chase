# UV Setup Instructions

## Current Status

✓ `uv` v0.9.18 is installed at: `/Users/hw/.local/bin/uv`

## Quick Setup

To use `uv` commands without typing the full path, add it to your PATH:

### For zsh (macOS default):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### For bash:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
```

## Verify Installation

After adding to PATH, verify with:

```bash
uv --version
```

Should output: `uv 0.9.18 (0cee76417 2025-12-16)`

## Using uv with This Project

### First-Time Setup

1. **Configure environment variables:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your actual paths
   ```

2. **Install dependencies:**
   ```bash
   uv pip install python-dotenv pypdf2
   ```

### Option 1: After adding to PATH (recommended)

```bash
cd /Users/hw/Docs/document-processor
uv run python script_name.py
```

### Option 2: Using full path (works now)

```bash
cd /Users/hw/Docs/document-processor
/Users/hw/.local/bin/uv run python script_name.py
```

### Option 3: Without uv (always works)

```bash
cd /Users/hw/Docs/document-processor
.venv/bin/python3 script_name.py
```

## Examples

### Run verification script:

```bash
# With uv in PATH:
uv run python verify_files_and_metadata.py

# With full path:
/Users/hw/.local/bin/uv run python verify_files_and_metadata.py

# Without uv:
.venv/bin/python3 verify_files_and_metadata.py
```

### Extract PDF metadata:

```bash
# With uv in PATH:
uv run python extract_metadata.py "/Users/hw/Docs/reference/some_file.pdf"

# With full path:
/Users/hw/.local/bin/uv run python extract_metadata.py "/Users/hw/Docs/reference/some_file.pdf"

# Without uv:
.venv/bin/python3 extract_metadata.py "/Users/hw/Docs/reference/some_file.pdf"
```

---

**All three methods work perfectly!** Choose whichever is most convenient for you.
