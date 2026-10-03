# IT Diagnostic Toolkit

A comprehensive Windows diagnostic and repair toolkit designed for both IT professionals and everyday users. This application provides basic system health checks, hardware scanning, and automated troubleshooting.

## Overview

The IT Diagnostic Toolkit is a user-friendly application that simplifies complex system diagnostics and repairs. Whether you're an IT professional servicing multiple machines or a home user troubleshooting your own PC, this toolkit provides essential diagnostic capabilities without requiring technical expertise.

**This is an actively developed project** - more features and improvements will be added based on user feedback and testing.

## Features

### 1. Hardware Scan
Generates a comprehensive hardware report including:
- System information (OS edition, version, hostname, IP address)
- CPU, GPU and RAM details
- BIOS information
- Secure Boot status
- Disk health monitoring with SMART data

### 2. System File Repair (DISM + SFC)
Automatically runs Windows system file integrity checks and repairs:
- **DISM CheckHealth**: Quick corruption detection
- **DISM ScanHealth**: Deep component store analysis
- **DISM RestoreHealth**: Automated repair of corrupted system files
- **SFC /scannow**: System File Checker verification and repair

### 3. Reliability History
Quick access to Windows Reliability Monitor for tracking system stability and identifying recurring issues.

### 4. Event Viewer
Direct access to Windows Event Viewer for detailed system log analysis.

## System Requirements

- **Operating System**: Windows 10/11 recommended
- **Privileges**: Administrator rights required for system diagnostics
- **Python** (if running from source): Python 3.8 or later

## Installation

### Option 1: Download Pre-built Executable (Recommended)

1. Go to the [Releases](../../releases) page
2. Download the latest `toolkit_launcher_v0.2.0.exe`
3. Run the executable - no installation required

### Option 2: Run from Source

1. Clone this repository:
```bash
   git clone https://github.com/DimitriosNossis/Toolkit.git
   cd Toolkit
```

2. Install dependencies:
```bash
   pip install -r requirements.txt
```

3. Run the toolkit:
```bash
   python toolkit_launcher.py
```

## Building from Source

To create your own executable:

1. Install PyInstaller:
```bash
   pip install pyinstaller
```

2. Build the executable (bundling the cat artwork and fonts):
```bash
   pyinstaller --onefile --windowed --add-data "assets;assets" toolkit_launcher.py
```

3. The executable will be created in the `dist/` folder

### Automatic builds (GitHub Actions)

The workflow in `.github/workflows/build-exe.yml` builds the executable on GitHub's Windows machines:

- **Every push to `main` and every pull request**: open the **Actions** tab, click the run, and download the `.exe` from **Artifacts** at the bottom of the page.
- **Version tags** (for example `v0.2.0`): the `.exe` is also published as a GitHub **Release**:
```bash
   git tag v0.2.0
   git push origin v0.2.0
```
- **On demand**: Actions tab → **Build .exe** → **Run workflow**.

## Usage

1. **Launch the application** - Run as Administrator (the toolkit will prompt for elevation if needed)

2. **Select an option** - click a card in the toolkit window, or press its number:
   - Press `1` for Hardware Scan
   - Press `2` for System File Repair
   - Press `3` to open Reliability History
   - Press `4` to open Event Viewer
   - Press `0` to Exit

   A cat naps on top of the window. When you pick a tool it wakes up, bats a couple of the other cards out of line, and taps yours. Hardware Scan and System File Repair run inside the window, with a progress bar, live output and the finished report on screen; reports are still saved to `reports/`. A little after a tool finishes, the cat drifts back to sleep.

   Click the cat to pet it: it closes its eyes, leans into your hand and little hearts float up.

   The window has its own title bar: drag it (or the cat) to move the window, and use the buttons on the right to minimise or close it.

   Prefer the classic text menu? Start the toolkit with `--console`:
```bash
   python toolkit_launcher.py --console
```

3. **View reports** - All diagnostic reports are saved in the `reports/` folder next to the executable:
   - `hardware_scan_report.txt` - Complete hardware inventory
   - `fix_corrupted_report.txt` - System repair results

## For Beginners

This toolkit is designed to be accessible for users without technical backgrounds:

- **Clear menu system**: Simple numbered options guide you through each function
- **Automated diagnostics**: The toolkit handles complex commands automatically
- **Plain language reports**: Results are presented in easy-to-understand format
- **Safe operations**: All scans are read-only except the repair function, which uses Windows' built-in repair tools
- **No configuration required**: Works out of the box with sensible defaults

### What do the tools do?

- **Hardware Scan**: Takes a snapshot of your computer's components and health status - useful for documentation or when seeking technical support
- **System File Repair**: Fixes corrupted Windows system files that may cause errors, crashes, or performance issues
- **Reliability History**: Shows a timeline of system events, crashes, and updates to help identify patterns
- **Event Viewer**: Provides detailed logs for troubleshooting specific issues (more technical)

## For IT Professionals

### Features for Professional Use

- **Detailed logging**: Comprehensive reports for documentation and compliance
- **No user interaction required**: Hardware scan runs silently with report generation
- **In-app repair**: System File Repair (DISM + SFC) runs inside the toolkit window with live progress (in `--console` mode it still opens its own console window)
- **SMART health monitoring**: Physical disk health status for proactive maintenance

## Technical Details

### Architecture

The toolkit consists of three main modules:

- `toolkit_launcher.py`: Entry point, admin elevation, console menu and application orchestration
- `toolkit_gui.py`: Graphical menu window (Tkinter) with the sleeping cat
- `assets/`: Cat artwork and the bundled Zen Maru Gothic / JetBrains Mono fonts (SIL Open Font License, see `assets/fonts/`)
- `hardware_scan.py`: System information gathering
- `fix_corrupted.py`: DISM and SFC automation with progress tracking

### Dependencies

- **psutil**: Cross-platform system and process utilities
- **tqdm**: Progress bar library for visual feedback
- **Pillow**: Image handling for the graphical menu (cat animation)

### Compatibility

- Tested on Windows 10 and Windows 11

## Report Format

All reports are generated as plain text files for easy sharing and documentation:
```
reports/
├── hardware_scan_report.txt
└── fix_corrupted_report.txt
```

Reports include timestamps and are overwritten on subsequent runs to prevent clutter.

## Troubleshooting

**Issue**: "Access Denied" errors
- **Solution**: Ensure you're running the toolkit as Administrator

**Issue**: Progress bar shows unusual characters
- **Solution**: This is a console encoding issue and doesn't affect functionality. The toolkit uses Unicode for smooth progress bars, which may not render correctly in older console windows.

**Issue**: Hardware scan shows incomplete disk information
- **Solution**: Some disk information requires SMART support. Older drives or USB-connected drives may not provide full health data.

**Issue**: System File Repair window closes immediately
- **Solution**: This occurs when no issues are found or repair completes quickly. Check the generated report for results.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This toolkit uses Windows built-in diagnostic and repair utilities. While these tools are safe and widely used, always ensure you have backups before performing system repairs. 

**This is an early release (v0.2.0) and further testing is ongoing.** While the toolkit has been tested on various Windows 10 and 11 systems, users should exercise caution and report any issues encountered.

The authors are not responsible for any system changes or data loss resulting from the use of this toolkit.

## Support

For issues, questions, or suggestions, please open an issue on the GitHub repository.

---

**Version**: 0.2.0  
**Last Updated**: October 2026
