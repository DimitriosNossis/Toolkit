import subprocess
import os
import sys
import datetime
import ctypes
from tqdm import tqdm


def is_admin():
    """Check if the script is running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def relaunch_as_admin():
    """Relaunch this script/exe with Administrator privileges (for standalone use)."""
    if getattr(sys, "frozen", False):
        exe_path = sys.executable
        params = ""
    else:
        exe_path = sys.executable
        params = f'"{os.path.abspath(__file__)}"'

    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        exe_path,
        params,
        None,
        1
    )


def get_base_dir():
    """Return the folder where the .py or .exe resides."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def run_command(cmd):
    """
    Run a command and stream its output live to the console with tqdm progress bars.
    """
    print(f"\n=== Running: {cmd} ===\n")

    cmd_lower = cmd.lower()
    is_sfc = "sfc" in cmd_lower and "/scannow" in cmd_lower
    is_dism = "dism" in cmd_lower
    
    # SFC outputs in UTF-16LE, other tools use UTF-8
    encoding = "utf-16-le" if is_sfc else "utf-8"

    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=encoding,
        errors="ignore",
    )

    raw_output_lines = []
    pbar = None
    last_percent = -1

    # Create progress bar with Unicode block characters (smooth bar)
    if is_sfc:
        pbar = tqdm(
            total=100,
            desc="SFC Verification",
            unit="%",
            bar_format='{desc}: {percentage:3.0f}%|{bar}|'
        )
    elif is_dism and any(x in cmd_lower for x in ["scanhealth", "restorehealth"]):
        pbar = tqdm(
            total=100,
            desc="DISM Progress",
            unit="%",
            bar_format='{desc}: {percentage:3.0f}%|{bar}|'
        )

    # Stream output
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if not line:
            continue

        stripped = line.strip()
        lower_stripped = stripped.lower()
        
        # SFC handling
        if is_sfc:
            # Skip informational messages
            if any(phrase in lower_stripped for phrase in [
                "beginning system scan",
                "beginning verification phase",
                "this process will take some time"
            ]):
                raw_output_lines.append(line)
                continue
            
            # Update progress bar from verification percentage
            if "verification" in lower_stripped and "%" in stripped and "complete" in lower_stripped:
                try:
                    percent_str = stripped.split("%")[0].split()[-1]
                    current_percent = int(percent_str)
                    
                    if current_percent != last_percent and pbar:
                        pbar.n = current_percent
                        pbar.refresh()
                        last_percent = current_percent
                except:
                    pass
                raw_output_lines.append(line)
                continue
            
            # Final result - show after progress bar
            if "windows resource protection" in lower_stripped:
                if pbar:
                    pbar.close()
                    pbar = None
                print(f"\n{stripped}\n")
        
        # DISM handling
        elif is_dism:
            # Update progress bar from DISM percentage
            if "%" in stripped and "[" in stripped and "]" in stripped:
                try:
                    # Extract percentage from [====== XX.X% ======]
                    percent_str = stripped.split("%")[0].split()[-1]
                    current_percent = float(percent_str)
                    
                    if pbar and current_percent != last_percent:
                        pbar.n = int(current_percent)
                        pbar.refresh()
                        last_percent = current_percent
                except:
                    pass
                raw_output_lines.append(line)
                continue
            
            # Non-progress DISM output
            if pbar and "operation completed successfully" in lower_stripped:
                pbar.n = 100
                pbar.close()
                pbar = None
            
            # Show important messages
            if not pbar or any(keyword in lower_stripped for keyword in [
                "deployment image",
                "version:",
                "image version:",
                "no component store corruption",
                "operation completed",
                "restore operation"
            ]):
                if pbar:
                    # Temporarily clear progress bar to show message
                    tqdm.write(stripped)
                else:
                    print(stripped)
        else:
            # Other commands - just print normally
            print(line, end="")
        
        raw_output_lines.append(line)

    # Close progress bar if still open
    if pbar:
        pbar.close()

    # Combine & clean raw output for the report
    result = "".join(raw_output_lines)
    result = result.replace("\x00", "")  # remove weird null chars from SFC

    # --- Special handling for sfc /scannow in the report ---
    if is_sfc:
        # Only keep the final Windows Resource Protection message
        final_msg = None

        for line in result.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if "Windows Resource Protection" in stripped:
                final_msg = stripped
                break

        if final_msg:
            return final_msg + "\n"
        else:
            return "SFC scan completed (no result message found)\n"

    # --- Default handling (DISM) for the report ---
    cleaned_lines = []

    for line in result.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Skip ALL DISM progress bar lines
        if "%" in stripped and "[" in stripped and "]" in stripped:
            continue

        cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines) + "\n" if cleaned_lines else ""


def run_fix_corrupted():
    """
    Main logic to run DISM + SFC and write a report.
    Assumes we are already running as Administrator.
    """
    base_dir = get_base_dir()
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, "fix_corrupted_report.txt")

    lines = []
    lines.append("=== SYSTEM FILE REPAIR (DISM + SFC) ===")
    lines.append(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("Commands executed in order:")
    lines.append("1) DISM /Online /Cleanup-Image /CheckHealth")
    lines.append("2) DISM /Online /Cleanup-Image /ScanHealth")
    lines.append("3) DISM /Online /Cleanup-Image /RestoreHealth")
    lines.append("4) sfc /scannow")
    lines.append("")

    print("System File Repair Tool")
    print("-----------------------")
    print("This will run DISM (CheckHealth, ScanHealth, RestoreHealth) and SFC /scannow.")
    print("Depending on system speed, this can take quite a while.\n")

    input("Press Enter to start the repair process, or close this window to cancel...")

    commands = [
        "Dism /Online /Cleanup-Image /CheckHealth",
        "Dism /Online /Cleanup-Image /ScanHealth",
        "Dism /Online /Cleanup-Image /RestoreHealth",
        "sfc /scannow",
    ]

    for cmd in commands:
        lines.append(f"=== Running: {cmd} ===")
        output = run_command(cmd)
        lines.append(output)
        lines.append("")

    lines.append(f"Completed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n" + "="*50)
    print("ALL HEALTH CHECKS FINISHED!")
    print("="*50)
    print(f"Full report saved to: {report_path}")


if __name__ == "__main__":
    if not is_admin():
        relaunch_as_admin()
        sys.exit(0)

    try:
        run_fix_corrupted()
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        input("\nPress Enter to close this window...")
