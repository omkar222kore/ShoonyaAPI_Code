import csv
from datetime import datetime as dt_datetime

def extract_stock_list_from_csv(csv_file_path, target_datetime_str):
    stockList = []
    
    try:
        # Define the target datetime
        target_datetime = dt_datetime.strptime(target_datetime_str, '%d-%m-%Y %I:%M %p')
        
        # Function to parse datetime with error handling
        def parse_datetime(date_str):
            try:
                return dt_datetime.strptime(date_str.strip(), '%d-%m-%Y %I:%M %p')
            except ValueError:
                return None
        
        # Open the CSV file and read its content
        with open(csv_file_path, mode='r', newline='', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader)  # Read the header row
        
            # Iterate through each row in the CSV
            for row in reader:
                if len(row) > 0:
                    cell_value = row[0].strip()  # Assuming the datetime is in the first column
                    cell_datetime = parse_datetime(cell_value)
                    
                    # Check if the cell datetime matches the target datetime exactly
                    if cell_datetime and cell_datetime == target_datetime:
                        # Append the symbol (assuming it's in the second column) to stockList
                        if len(row) > 1:
                            stockList.append(f"{row[1]}-EQ")  # Append "-EQ" to each symbol
        
    except Exception as e:
        print(f"An error occurred: {e}")
    
    # Return the list of symbols matching the target datetime
    return stockList

def print_stock_list():
    # Define paths and parameters
    csv_file_path = "C:/Users/omkar/Downloads/Backtest BB Blast_Omk, Technical Analysis Scanner.csv"
    target_datetime_str = dt_datetime.today().strftime('%d-%m-%Y') + " 10:15 am"
    
    # Extract stock list from CSV
    stockList = extract_stock_list_from_csv(csv_file_path, target_datetime_str)
    
    # Print the stock list
    print('Symbols matching the target datetime:')
    print(stockList)

# Call the function to print the stock list
print_stock_list()



def place_orders():
    global stocksList, completed_orders, all_orders_completed, slArray, PlaceQtyForEachStockArray
    
    # Define paths and parameters
    csv_file_path = "C:/Users/omkar/Downloads/Backtest BB Blast_Omk, Technical Analysis Scanner.csv"
    target_datetime_str = dt_datetime.today().strftime('%d-%m-%Y') + " 10:15 am"
    
    # Extract stock list from CSV
    stocksList = extract_stock_list_from_csv(csv_file_path, target_datetime_str)
    
    # Filter out symbols to remove
    stocksList = [symbol for symbol in stocksList if symbol not in remove_stocks]
    
    print('Symbols matching the target datetime:')
    print(stocksList)
    
    qtyGet = len(stocksList)
    print(f"Number of stocks selected: {qtyGet}")
    
    # Example logic for calculating capital per stock
    capUsed = 18000
    if qtyGet <= 2:
        capForEachStock = 20000
    elif qtyGet == 3:
        capForEachStock = 25000
    else:
        capForEachStock = int(capUsed * 5 / qtyGet)
        
    print(f"Capital for each stock: {capForEachStock}")
    
    if len(stocksList) <= 5:
        # Iterate over each symbol and retrieve data
        for symbol in stocksList:
            try:
                # Retrieve quote for the current symbol using the API (replace with actual API call)
                quote = api.get_quotes(exchange='NSE', token=symbol)
                LTP = float(quote["lp"])
                
                # Calculate quantity to place for each stock
                PlaceQtyForEachStock = int(capForEachStock / LTP)
                PlaceQtyForEachStockArray.append(PlaceQtyForEachStock)
                slArray.append(LTP)
                
                # Example: Place order (replace with actual order placement code)
                api.place_order(buy_or_sell='S', product_type='I', exchange='NSE', tradingsymbol=symbol,
                                quantity=PlaceQtyForEachStock, discloseqty=0, price_type='MKT',
                                trigger_price=None, retention='DAY', remarks='stop_loss_order')
            
            except Exception as e:
                # Handle any errors that occur
                print(f"Error occurred for symbol {symbol}: {e}")
    else:
        # If the length of stocksList is greater than 5, set stocksList to an empty array
        stocksList = []
        print("Stock list has more than 5 stocks. It has been set to an empty array.")

        