import os
import sys
import time
import ctypes
import subprocess

import hardware_scan
import fix_corrupted


# ========= Console helpers =========

def clear_screen():
    """Clear the console screen."""
    os.system("cls" if os.name == "nt" else "clear")


def disable_quick_edit():
    """
    Disable QuickEdit mode so that clicking in the console
    does NOT pause the program (which would otherwise make
    DISM/SFC appear 'stuck' until Enter is pressed).
    """
    try:
        kernel32 = ctypes.windll.kernel32
        h_stdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE = -10

        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
            return  # couldn't get mode; just skip

        ENABLE_QUICK_EDIT = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080

        new_mode = mode.value
        # turn off QuickEdit
        new_mode &= ~ENABLE_QUICK_EDIT
        # ensure extended flags are set
        new_mode |= ENABLE_EXTENDED_FLAGS

        kernel32.SetConsoleMode(h_stdin, new_mode)
    except Exception:
        # If anything fails, just leave console as-is.
        pass


# ========= Admin helpers =========

def is_admin():
    """Check if the toolkit is running with Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def relaunch_as_admin():
    """
    Relaunch this toolkit exe (or python) with the same arguments, but elevated.
    Shows a UAC prompt.
    """
    if getattr(sys, "frozen", False):
        exe_path = sys.executable  # PyInstaller exe
        script_path = ""
    else:
        exe_path = sys.executable  # python.exe
        script_path = os.path.abspath(__file__)
        if wants_gui():
            # pythonw.exe runs the window without an extra black console
            pythonw = os.path.join(os.path.dirname(exe_path), "pythonw.exe")
            if os.path.exists(pythonw):
                exe_path = pythonw

    extra_args = " ".join(f'"{arg}"' for arg in sys.argv[1:])

    if script_path:
        params = f'"{script_path}" {extra_args}'.strip()
    else:
        params = extra_args

    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",   # run as administrator
        exe_path,
        params,
        None,
        1         # normal window
    )


# ========= Launch helpers =========

def wants_gui():
    """True unless a console mode was asked for on the command line."""
    args = sys.argv[1:]
    return not any(a in args for a in ("--console", "--fix-corrupted-child"))


def hide_own_console():
    """
    Hide the console window if this process opened it just for itself
    (e.g. a double-clicked .py). A cmd window you started from is left alone.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return
        pids = (ctypes.c_uint * 4)()
        if kernel32.GetConsoleProcessList(pids, 4) <= 1:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def child_command(flag):
    """Command line that re-runs this toolkit (exe or .py) in a child mode."""
    if getattr(sys, "frozen", False):
        return [sys.executable, flag]
    return [sys.executable, os.path.abspath(__file__), flag]


def launch_fix_corrupted_window():
    """Start DISM + SFC in its own console window. Raises on failure."""
    # On Windows, CREATE_NEW_CONSOLE = 0x00000010
    CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    subprocess.Popen(child_command("--fix-corrupted-child"), creationflags=CREATE_NEW_CONSOLE)


def shell_open(target, params=None):
    """Open a Windows tool (e.g. perfmon.exe, eventvwr.msc). Raises on failure."""
    result = ctypes.windll.shell32.ShellExecuteW(None, "open", target, params, None, 1)
    if result <= 32:
        raise OSError(f"ShellExecute error {result}")


def attach_console_streams():
    """
    A windowed (--noconsole) build starts without stdio. Child modes that get
    their own console reconnect to it so print() and input() work.
    """
    if sys.stdout is None or sys.stdin is None:
        try:
            ctypes.windll.kernel32.AllocConsole()  # no-op if we already have one
        except Exception:
            pass
        try:
            sys.stdout = open("CONOUT$", "w", buffering=1)
            sys.stderr = sys.stdout
            sys.stdin = open("CONIN$", "r")
        except OSError:
            pass


# ========= Menu actions =========

def run_hardware_scan_tool():
    clear_screen()
    print("=== Hardware Scan Tool ===\n")
    hardware_scan.run_hardware_scan()
    input("\nPress Enter to close this window...")


def run_fix_corrupted_tool():
    """
    Launch DISM + SFC in a **separate console window** so the main
    IT Toolkit menu stays usable.
    """
    clear_screen()
    print("Launching System File Repair (DISM + SFC) in a new window...\n")

    try:
        launch_fix_corrupted_window()
        print("Repair tool launched in a separate window.")
        print("You can keep using the IT Toolkit menu while the scan runs.")
    except Exception as e:
        print(f"[!] Failed to launch repair tool: {e}")

    print("\nReturning to IT Toolkit menu in 3 seconds...")
    time.sleep(3)

def open_reliability_history():
    clear_screen()
    print("Opening Reliability Monitor...\n")
    try:
        shell_open("perfmon.exe", "/rel")
    except Exception as e:
        print(f"[!] Failed to open Reliability Monitor: {e}")
    print("\nReturning to IT Toolkit menu in 3 seconds...")
    time.sleep(3)


def open_event_viewer():
    clear_screen()
    print("Opening Event Viewer...\n")
    try:
        shell_open("eventvwr.msc")
    except Exception as e:
        print(f"[!] Failed to open Event Viewer: {e}")
    print("\nReturning to IT Toolkit menu in 3 seconds...")
    time.sleep(3)


# ========= Main menu loop =========

def main_menu():
    while True:
        clear_screen()
        print("==============================")
        print("          IT TOOLKIT")
        print("==============================")
        print("1) Run Hardware Scan")
        print("2) Fix Corrupted System Files (DISM + SFC)")
        print("3) Open Reliability History")
        print("4) Open Event Viewer")
        print("0) Exit")
        choice = input("\nSelect an option: ").strip()

        if choice == "1":
            run_hardware_scan_tool()
        elif choice == "2":
            run_fix_corrupted_tool()
        elif choice == "3":
            open_reliability_history()
        elif choice == "4":
            open_event_viewer()
        elif choice == "0":
            print("\nExiting IT Toolkit. Goodbye!\n")
            break
        else:
            print("\nInvalid selection. Please try again.")
            time.sleep(2)


# ========= Entry point =========

def start_gui():
    """Open the graphical toolkit; fall back to the console menu if it can't start."""
    try:
        import toolkit_gui
    except ImportError as e:
        attach_console_streams()
        print(f"Graphical mode unavailable ({e}). Using the console menu.")
        time.sleep(2)
        main_menu()
        return
    toolkit_gui.run()


if __name__ == "__main__":
    disable_quick_edit()

    # Child mode: only run DISM+SFC in this window, no menu
    if "--fix-corrupted-child" in sys.argv[1:]:
        attach_console_streams()
        # Make sure we are admin; if not, relaunch with same arg.
        if not is_admin():
            relaunch_as_admin()
            sys.exit(0)

        clear_screen()
        print("=== System File Repair (DISM + SFC) ===\n")
        try:
            fix_corrupted.run_fix_corrupted()
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
        finally:
            input("\nPress Enter to close this window...")
        sys.exit(0)

    # Normal menu mode
    if not is_admin():
        relaunch_as_admin()
        sys.exit(0)

    if "--console" in sys.argv[1:]:
        attach_console_streams()
        main_menu()
    else:
        hide_own_console()
        start_gui()
