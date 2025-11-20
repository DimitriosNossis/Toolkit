import platform
import socket
import shutil
import os
import datetime
import subprocess
import sys
import psutil  # make sure this is installed


def get_ip_address():
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        return hostname, ip
    except Exception:
        return socket.gethostname(), "Unknown"


def get_cpu_model():
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-command",
                "Get-CimInstance Win32_Processor | "
                "Select-Object -ExpandProperty Name",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.strip()
    except Exception:
        return platform.processor()


def get_windows_edition():
    """Get the specific Windows edition (e.g., Windows 11 Pro, Windows 10 Home)"""
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-command",
                "(Get-CimInstance Win32_OperatingSystem).Caption",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.strip()
    except Exception:
        return f"{platform.system()} {platform.release()}"


def get_ram_info():
    """Get total RAM in GB"""
    try:
        total_ram = psutil.virtual_memory().total
        ram_gb = total_ram / (1024 ** 3)
        return f"{ram_gb:.2f} GB"
    except Exception:
        return "Unknown"


def get_secure_boot_status():
    """Check if Secure Boot is enabled"""
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-command",
                "Confirm-SecureBootUEFI",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        # PowerShell returns "True" or "False"
        return "Enabled" if "True" in result else "Disabled"
    except subprocess.CalledProcessError:
        # If command fails, Secure Boot is likely not supported or disabled
        return "Not Supported or Disabled"
    except Exception:
        return "Unable to determine"


def get_bios_info():
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-command",
                "Get-CimInstance Win32_BIOS | "
                "Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate | "
                "Format-List",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.strip()
    except Exception:
        return "BIOS information unavailable"


def get_gpu_models():
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object -ExpandProperty Name",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        gpus = [line.strip() for line in result.splitlines() if line.strip()]
        return gpus if gpus else ["Unknown GPU"]
    except Exception:
        return ["GPU information unavailable"]


def get_physical_disk_to_partition_mapping():
    """
    Map physical disks to their logical partitions.
    Returns dict: {physical_disk_number: [list of drive letters]}
    """
    mapping = {}
    try:
        # Get partition to disk mapping
        result = subprocess.check_output(
            [
                "powershell",
                "-command",
                "Get-Partition | Select-Object DiskNumber, DriveLetter | ConvertTo-Json",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        
        import json
        partitions = json.loads(result)
        
        # Handle single partition case (not a list)
        if isinstance(partitions, dict):
            partitions = [partitions]
        
        for part in partitions:
            disk_num = part.get('DiskNumber')
            drive_letter = part.get('DriveLetter')
            
            if disk_num is not None:
                if disk_num not in mapping:
                    mapping[disk_num] = []
                if drive_letter:
                    mapping[disk_num].append(f"{drive_letter}:")
        
    except Exception:
        pass
    
    return mapping


def get_disk_health():
    """
    Get disk health status using Get-PhysicalDisk.
    Returns a list of tuples: (disk_number, model, status, health)
    """
    disk_health_info = []
    
    try:
        # Try using Get-PhysicalDisk (Windows 8+)
        result = subprocess.check_output(
            [
                "powershell",
                "-command",
                "Get-PhysicalDisk | Select-Object DeviceID, FriendlyName, OperationalStatus, HealthStatus | ConvertTo-Json",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        
        import json
        disks = json.loads(result)
        
        # Handle single disk case (not a list)
        if isinstance(disks, dict):
            disks = [disks]
        
        for disk in disks:
            device_id = disk.get('DeviceID', 'N/A')
            friendly_name = disk.get('FriendlyName', 'Unknown')
            operational_status = disk.get('OperationalStatus', 'Unknown')
            health_status = disk.get('HealthStatus', 'Unknown')
            disk_health_info.append((device_id, friendly_name, operational_status, health_status))
        
        return disk_health_info if disk_health_info else [("N/A", "Unable to retrieve disk health", "Unknown", "Unknown")]
        
    except Exception:
        return [("N/A", "Unable to retrieve disk health", "Unknown", "Unknown")]


def get_all_disks():
    disks_info = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks_info.append((part.device, usage.total, usage.used, usage.free))
        except PermissionError:
            continue
    return disks_info


def get_base_dir():
    if getattr(sys, "frozen", False):  # running as .exe
        return os.path.dirname(sys.executable)
    else:  # running as .py
        return os.path.dirname(os.path.abspath(__file__))


def main():
    lines = []

    lines.append("=== HARDWARE SCAN REPORT ===")
    lines.append(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # System info
    hostname, ip = get_ip_address()
    lines.append("=== SYSTEM INFO ===")
    lines.append(f"Hostname: {hostname}")
    lines.append(f"IP Address: {ip}")
    lines.append(f"Operating System: {get_windows_edition()}")
    lines.append(f"OS Version: {platform.version()}")
    lines.append(f"RAM: {get_ram_info()}")
    lines.append(f"Secure Boot: {get_secure_boot_status()}")
    lines.append(f"Processor: {get_cpu_model()}")
    for gpu in get_gpu_models():
        lines.append(f"GPU: {gpu}")
    lines.append("")

    # BIOS info
    lines.append("=== BIOS INFO ===")
    lines.append(get_bios_info())
    lines.append("")

    # Disk Health and Partitions (merged)
    lines.append("=== DISK HEALTH & PARTITIONS ===")
    
    # Get physical disk health
    disk_health = get_disk_health()
    
    # Get mapping of physical disks to partitions
    disk_to_partitions = get_physical_disk_to_partition_mapping()
    
    # Get partition usage info
    partition_usage = {}
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            # Store with the drive letter format (e.g., "C:")
            drive_letter = part.device.rstrip("\\")
            partition_usage[drive_letter] = usage
        except:
            pass
    
    gb = 1024 ** 3
    
    for disk_id, model, operational_status, health_status in disk_health:
        # Get drive letters for this disk
        partitions = disk_to_partitions.get(disk_id, [])
        drive_letters = ", ".join(partitions) if partitions else ""
        
        # Format the disk header with drive letters if available
        if drive_letters:
            lines.append(f"Disk {disk_id} ({drive_letters}): {model}")
        else:
            lines.append(f"Disk {disk_id}: {model}")
        
        lines.append(f"  Health Status: {health_status}")
        lines.append(f"  Operational Status: {operational_status}")
        
        # Show partitions for this physical disk
        if partitions:
            lines.append(f"  Partitions:")
            for partition in partitions:
                if partition in partition_usage:
                    usage = partition_usage[partition]
                    lines.append(f"    {partition}")
                    lines.append(f"      Total: {usage.total / gb:.2f} GB")
                    lines.append(f"      Used:  {usage.used / gb:.2f} GB")
                    lines.append(f"      Free:  {usage.free / gb:.2f} GB")
                else:
                    lines.append(f"    {partition}")
        
        lines.append("")

    # Environment
    lines.append("=== ENVIRONMENT (partial) ===")
    for key in ("USERNAME", "USERDOMAIN", "COMPUTERNAME"):
        value = os.getenv(key, "Not set")
        lines.append(f"{key}: {value}")
    lines.append("")

    # Save into reports/ folder next to .py or .exe
    base_dir = get_base_dir()
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    report_path = os.path.join(reports_dir, "hardware_scan_report.txt")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("Hardware scan completed.")
    print(f"Report saved to: {report_path}")


def run_hardware_scan():
    main()  # just call your existing main()


if __name__ == "__main__":
    run_hardware_scan()