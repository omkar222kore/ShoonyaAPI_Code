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

def run_python_script(script_path):
    """Run a Python script using subprocess."""
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
    exists = os.path.isfile(file_path)
    if exists:
        print(f"File exists: {file_path}")
    else:
        print(f"File not found: {file_path}")
    return exists

def main():
    # Define paths to the Python scripts
    script1 = "D:\\AA_trading_Algos\\ShoonyaAPI_Code\\downloadCSV.py"
    script2 = "D:\\AA_trading_Algos\\ShoonyaAPI_Code\\punch_orderUp.py"
    script3 = "D:\\AA_trading_Algos\\ShoonyaAPI_Code\\book_order.py"  # The new one-time run script
    downloads_folder = "C:\\Users\\omkar\\Downloads"

    # Define the start time and end time for running the first two scripts
    start_time = datetime.time(21, 33)  # Specify the start time
    end_time = datetime.time(21, 45)  # Specify the end time
    interval_minutes = 15  # Set the interval to 15 minutes

    # Time to run script3 (10:15 AM)
    script3_run_time = datetime.time(21, 33)
    script3_executed = False  # To ensure it runs only once

    while True:
        now = datetime.datetime.now().time()

        # Run script3 at the specified time only once
        if now >= script3_run_time and not script3_executed:
            if check_file_exists(script3):
                print(f"Running {script3} at 21:17...")
                run_python_script(script3)
                print(f"Completed running {script3}")
                script3_executed = True  # Mark script3 as executed
            else:
                print(f"{script3} not found. Skipping execution.")

        # Continue running the first two scripts within the specified time window
        if start_time <= now <= end_time:
            # Check if scripts exist
            if not all(check_file_exists(script) for script in [script1, script2]):
                print("One or more scripts are missing. Exiting...")
                return

            # Run the first script
            print(f"Running {script1}...")
            run_python_script(script1)
            print(f"Completed running {script1}")

            # Run the second script
            print(f"Running {script2}...")
            run_python_script(script2)
            print(f"Completed running {script2}")

            # Wait for the next interval
            next_interval_time = datetime.datetime.combine(datetime.date.today(), now) + datetime.timedelta(minutes=interval_minutes)
            next_interval_time = next_interval_time.time()
            print(f"Waiting for the next interval ({interval_minutes} minutes)...")
            wait_until(next_interval_time)
        else:
            print("Outside of the execution window. Waiting until the next execution window...")
            # Calculate the time to sleep until the next execution window
            next_execution_time = datetime.datetime.combine(datetime.date.today(), start_time)
            if now > end_time:
                # If the current time is past the end time, schedule for the next day
                next_execution_time += datetime.timedelta(days=1)
            elif now > start_time:
                # If the current time is between the start and end time, schedule for the next interval
                next_execution_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)

            time_to_sleep = (next_execution_time - datetime.datetime.now()).total_seconds()
            time.sleep(time_to_sleep)

    # Clear CSV files in the Downloads folder
    print("Clearing CSV files in Downloads folder...")
    clear_csv_files(downloads_folder)
    print("Completed clearing CSV files.")

    print("Main function completed.")

if __name__ == "__main__":
    main()
