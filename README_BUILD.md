# Building JARVIS Standalone Application

This guide explains how to build JARVIS into a standalone executable that can be distributed and run without Python..installation.

## Prerequisites

1. **Python 3.8+** installed
2. **Virtual environment** set up
3. **API Keys** configured in `.env` file

## Quick Build

1. **Install dependencies:**
   ```bash
   pip install -r requirements-build.txt
   ```

2. **Run the build script:**
   ```bash
   build_app.bat
   ```

3. **Find your executable:**
   - Built executable: `dist/JARVIS.exe`
   - Ready to distribute!

## Manual Build Process

If you prefer to build manually:

### 1. Setup Environment
```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements-build.txt
```

### 2. Configure API Keys
Create a `.env` file in the project root:
```env
GROQ_API_KEY=your_groq_api_key_here
# Other optional settings...
```

### 3. Build with PyInstaller
```bash
# Clean build
pyinstaller build/jarvis.spec --clean --noconfirm
```

## Distribution Package

The build process creates:
- `dist/JARVIS.exe` - The standalone executable
- `dist/` folder - Contains all bundled dependencies

### What to Distribute
1. **JARVIS.exe** - The main executable
2. **.env.example** - Template for configuration
3. **README.md** - Instructions for end users

### End User Setup
Users need to:
1. Copy `JARVIS.exe` to their desired location
2. Create a `.env` file with their API keys (copy from `.env.example`)
3. Run `JARVIS.exe`

## Build Configuration

### Spec File Options
The `build/jarvis.spec` file contains:
- **Included modules**: All Python packages needed
- **Data files**: Configuration, modules, and assets
- **Hidden imports**: Dependencies PyInstaller might miss
- **Exclusions**: Unnecessary modules to reduce size

### Optimization Features
- **UPX compression**: Reduces executable size (requires UPX installation)
- **Console mode**: Keeps terminal interface
- **Bundled dependencies**: No separate Python installation needed

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError**
   - Add missing modules to `hiddenimports` in `jarvis.spec`
   - Rebuild with `--clean` flag

2. **Large executable size**
   - Install UPX and add to PATH
   - Add more modules to `excludes` in spec file

3. **Audio/voice issues**
   - Ensure Windows audio drivers are up to date
   - Check microphone permissions

4. **API connection errors**
   - Verify `.env` file is correctly configured
   - Check internet connection

### Debug Mode
For debugging build issues:
```bash
pyinstaller build/jarvis.spec --debug=all --noconfirm
```

## Advanced Options

### Custom Icon
Add an icon file to the spec:
```python
exe = EXE(
    # ... other options ...
    icon='assets/jarvis.ico',  # Add your icon file
)
```

### One-File Mode (Alternative)
For a single executable (slower startup):
```python
exe = EXE(
    # ... 
    onefile=True,  # Instead of onedir
)
```

## Performance Notes

- **First run**: Slower as dependencies extract
- **Subsequent runs**: Normal performance
- **Memory usage**: Higher than Python script due to bundling
- **Size**: Typically 50-100MB depending on dependencies

## Support

For build issues:
1. Check PyInstaller documentation
2. Review the console output for specific errors
3. Ensure all dependencies are listed in requirements-build.txt
