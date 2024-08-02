import time
import os
import csv
from datetime import datetime as dt_datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import glob

# Define the path to the folder containing the CSV file
folder_path = r'C:\Users\omkar\Downloads'

# Delete all files in the folder (optional: uncomment the next lines to actually delete files)
files = glob.glob(os.path.join(folder_path, '*'))
for file in files:
    try:
        os.remove(file)
        print(f"Deleted: {file}")
    except Exception as e:
        print(f"Error deleting {file}: {e}")

def download_csv(chrome_driver_path, login_url, username, password, csv_file_name, target_datetime_str):
    # Initialize Chrome WebDriver
    service = Service(chrome_driver_path)
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        # Open the login URL
        driver.get(login_url)
        time.sleep(2)
        
        # Locate the username and password fields and enter the credentials
        username_field = driver.find_element(By.NAME, "email")
        password_field = driver.find_element(By.NAME, "password")
        username_field.send_keys(username)
        password_field.send_keys(password)
        password_field.send_keys(Keys.RETURN)
        time.sleep(2)
        
        # Click on the button to navigate to the correct page
        button1 = driver.find_element(By.XPATH, "//*[@class='table table-striped']//tr[8]//a")
        button1.click()
        time.sleep(2)
        
        # Click on the download button with the new XPath
        download_button = driver.find_element(By.XPATH, '//*[@id="backtest-container"]/div[2]/a')
        download_button.click()
        time.sleep(5)  # Wait for the download to complete; adjust if needed

        # Define the path to the CSV file in the Downloads folder
        csv_file_path = os.path.join(folder_path, csv_file_name)
        
        # Check if the CSV file exists
        if not os.path.exists(csv_file_path):
            print(f"CSV file not found: {csv_file_path}")
            return []
        
        # Define the target datetime
        target_datetime = dt_datetime.strptime(target_datetime_str, '%d-%m-%Y %I:%M %p')
        
        # Function to parse datetime with error handling
        def parse_datetime(date_str):
            try:
                return dt_datetime.strptime(date_str.strip(), '%d-%m-%Y %I:%M %p')
            except ValueError:
                return None
        
        # Read the CSV file and retrieve stock list
        stockList = []
        with open(csv_file_path, mode='r', newline='', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader)  # Skip the header if there is one
            for row in reader:
                if len(row) > 0:
                    cell_value = row[0].strip()
                    cell_datetime = parse_datetime(cell_value)
                    if cell_datetime and cell_datetime == target_datetime:
                        if len(row) > 1:
                            stockList.append(f"{row[1]}-EQ")
        
        return stockList
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return []
    
    finally:
        driver.quit()

# Example usage
chrome_driver_path = r'C:\Users\omkar\AppData\Local\Google\Chrome\User Data\Default\chromedriver-win64\chromedriver.exe'
login_url = "https://chartink.com/login"
username = "akashkharade.760@gmail.com"
password = "7030232281"
csv_file_name = "Backtest BB Blast_Omk, Technical Analysis Scanner.csv"
target_datetime_str = dt_datetime.today().strftime('%d-%m-%Y') + " 10:15 am"

# Call the function
stock_list = download_csv(chrome_driver_path, login_url, username, password, csv_file_name, target_datetime_str)
print(stock_list)
