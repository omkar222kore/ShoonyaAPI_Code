import datetime
import subprocess
import os
import time

def wait_until(target_time):
    """Wait until the specified target time."""
    now = datetime.datetime.now()
    target_time = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    
    # If the target time is earlier today, schedule for tomorrow
    if target_time < now:
        target_time += datetime.timedelta(days=1)

    sleep_duration = (target_time - now).total_seconds()
    print(f"Waiting for {sleep_duration / 60:.2f} minutes until {target_time}.")
    time.sleep(sleep_duration)

def run_python_script(script_path, is_direct=False):
    """Run a Python script using subprocess or exec."""
    if is_direct:
        # Execute script content directly
        try:
            print(f"Running script directly: {script_path}")
            with open(script_path, 'r') as file:
                script_content = file.read()
            exec(script_content, globals())
        except Exception as e:
            print(f"An error occurred while running {script_path}: {e}")
    else:
        # Execute script using subprocess
        try:
            print(f"Running script: {script_path}")
            result = subprocess.run(["python", script_path], check=True, text=True, capture_output=True)
            print(f"Output of {script_path}: {result.stdout}")
            if result.stderr:
                print(f"Error output of {script_path}: {result.stderr}")
        except subprocess.CalledProcessError as e:
            print(f"An error occurred while running {script_path}: {e}")

def clear_csv_files(directory):
    """Delete all CSV files in the specified directory."""
    print(f"Clearing CSV files in directory: {directory}")
    for file_name in os.listdir(directory):
        if file_name.endswith('.csv'):
            file_path = os.path.join(directory, file_name)
            try:
                os.remove(file_path)
                print(f"Deleted {file_path}")
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")

def check_file_exists(file_path):
    """Check if the file exists."""
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return False
    print(f"File exists: {file_path}")
    return True

def main():
    # Define paths to the Python scripts
    script1 = "E:\\Z_algo_Script\\downloadCSV.py"
    script2 = "E:\\Z_algo_Script\\punch_orders.py"
    script3 = "E:\\Z_algo_Script\\bookOrder.py"  # Path to the new script
    downloads_folder = "C:\\Users\\omkar\\Downloads"

    print("Starting main function...")

    # Check if scripts exist
    if not all(check_file_exists(script) for script in [script1, script2, script3]):
        print("One or more scripts are missing. Exiting...")
        return

    # Set target time and wait duration
    target_hour = 23  # Set to the desired hour (24-hour format)
    target_minute = 7  # Set to the desired minute
    wait_seconds = 2  # Set wait duration in seconds

    # Wait until the specified target time
    print("Waiting until the target time...")
    wait_until(datetime.time(target_hour, target_minute))

    # Run the first script
    print(f"Running {script1}...")
    run_python_script(script1)
    print(f"Completed running {script1}")

    # Wait for the specified duration
    print(f"Waiting for {wait_seconds} seconds...")
    time.sleep(wait_seconds)

    # Run the second script
    print(f"Running {script2}...")
    run_python_script(script2)
    print(f"Completed running {script2}")

    # Wait for the specified duration before running the third script
    print(f"Waiting for {wait_seconds} seconds...")
    time.sleep(wait_seconds)

    # Run the third script directly
    print(f"Running {script3} directly...")
    run_python_script(script3, is_direct=True)
    print(f"Completed running {script3}")

    # Clear CSV files in the Downloads folder
    print("Clearing CSV files in Downloads folder...")
    clear_csv_files(downloads_folder)
    print("Completed clearing CSV files.")

    print("Main function completed.")

if __name__ == "__main__":
    main()
