import pandas as pd
from datetime import datetime

def convert_to_stocks_info(input_data):
    """
    Convert DataFrame or CSV data to stocks_info list format.
    
    Input format:
        Index    DateTime                Stock      Category1      Category2
        0        2026-03-20 10:00:00     MRPL       Largecap       Energy
        1        2026-03-20 10:00:00     FINCABLES  Midcap         Industrials
    
    Output format:
        stocks_info = [
            ('20-03-2026 10:00', 'MRPL'),
            ('20-03-2026 10:00', 'FINCABLES'),
        ]
    
    Args:
        input_data: pandas DataFrame or path to CSV file
    
    Returns:
        list: List of tuples (date_time_string, stock_name)
    """
    
    # If input is a string (file path), read it as CSV
    if isinstance(input_data, str):
        df = pd.read_csv(input_data)
    else:
        df = input_data
    
    # Ensure the datetime column is in datetime format
    # The column name might be 'DateTime', 'date', 'time', etc. - adjust as needed
    datetime_column = None
    for col in df.columns:
        if col.lower() in ['datetime', 'date', 'time', 'timestamp']:
            datetime_column = col
            break
    
    if datetime_column is None:
        # If no datetime column found, assume the first column after index is datetime
        datetime_column = df.columns[0]
    
    # Find the stock name column (usually the second column)
    stock_column = df.columns[1]
    
    # Convert datetime to the required format (DD-MM-YYYY HH:MM)
    df[datetime_column] = pd.to_datetime(df[datetime_column])
    
    # Create the stocks_info list
    stocks_info = []
    for idx, row in df.iterrows():
        date_time_str = row[datetime_column].strftime('%d-%m-%Y %H:%M')
        stock_name = row[stock_column].strip()
        stocks_info.append((date_time_str, stock_name))
    
    return stocks_info


# Method 1: If you have the data as a DataFrame
def create_stocks_info_from_dataframe():
    """Example: Converting from a pandas DataFrame"""
    data = {
        'DateTime': [
            '2026-03-20 10:00:00', '2026-03-20 10:00:00', '2026-03-20 10:00:00',
            '2026-03-24 09:45:00', '2026-03-24 10:00:00', '2026-03-24 10:00:00',
            '2026-03-24 10:45:00', '2026-03-25 10:00:00'
        ],
        'Stock': [
            'MRPL', 'FINCABLES', 'UNIONBANK',
            'CANFINHOME', 'UNOMINDA', 'TIINDIA',
            'BLS', 'POLICYBZR'
        ],
        'Category1': ['Largecap', 'Midcap', 'Largecap', 'Midcap', 'Largecap', 'Largecap', 'Midcap', 'Largecap'],
        'Category2': ['Energy', 'Industrials', 'Bank', 'Financials', 'Auto', 'Industrials', 'I.T', 'I.T']
    }
    
    df = pd.DataFrame(data)
    stocks_info = convert_to_stocks_info(df)
    
    return stocks_info


# Method 2: If you have the data as a CSV file
def create_stocks_info_from_csv(csv_file_path):
    """Example: Converting from a CSV file"""
    stocks_info = convert_to_stocks_info(csv_file_path)
    return stocks_info


# Method 3: Manual conversion from text data
def convert_from_text(text_data):
    """Convert from text formatted data"""
    lines = text_data.strip().split('\n')
    stocks_info = []
    
    for line in lines:
        # Split by whitespace and extract relevant columns
        parts = line.split()
        if len(parts) >= 3:
            # parts[0] = index (skip)
            # parts[1] = date (YYYY-MM-DD)
            # parts[2] = time (HH:MM:SS)
            # parts[3] = stock name
            
            date_str = parts[1]  # 2026-03-20
            time_str = parts[2]  # 10:00:00
            stock_name = parts[3]  # MRPL
            
            # Convert date to DD-MM-YYYY format
            date_object = datetime.strptime(date_str, '%Y-%m-%d')
            formatted_date = date_object.strftime('%d-%m-%Y')
            
            # Extract only HH:MM from time
            time_hm = time_str[:5]  # 10:00
            
            stocks_info.append((f'{formatted_date} {time_hm}', stock_name))
    
    return stocks_info


# Usage Example
if __name__ == "__main__":
    
    # Example 1: Using DataFrame
    print("=" * 60)
    print("METHOD 1: Converting from DataFrame")
    print("=" * 60)
    stocks_info_1 = create_stocks_info_from_dataframe()
    print("stocks_info = [")
    for item in stocks_info_1:
        print(f"    {item},")
    print("]")
    
    # Example 2: Using text data
    print("\n" + "=" * 60)
    print("METHOD 2: Converting from text data")
    print("=" * 60)
    text_data = """0 2026-03-20 10:00:00        MRPL      Largecap       Energy
1 2026-03-20 10:00:00   FINCABLES        Midcap  Industrials
2 2026-03-20 10:00:00   UNIONBANK      Largecap         Bank
5 2026-03-24 09:45:00  CANFINHOME        Midcap   Financials
6 2026-03-24 10:00:00    UNOMINDA      Largecap         Auto
7 2026-03-24 10:00:00     TIINDIA      Largecap  Industrials
8 2026-03-24 10:45:00         BLS        Midcap          I.T
9 2026-03-25 10:00:00   POLICYBZR      Largecap          I.T"""
    
    stocks_info_2 = convert_from_text(text_data)
    print("stocks_info = [")
    for item in stocks_info_2:
        print(f"    {item},")
    print("]")
    
    # Example 3: Save to a file
    print("\n" + "=" * 60)
    print("Saving to Python file...")
    print("=" * 60)
    
    with open('stocks_info_output.py', 'w') as f:
        f.write('stocks_info = [\n')
        for date_time, stock in stocks_info_2:
            f.write(f"    ('{date_time}', '{stock}'),\n")
        f.write(']\n')
    
    print("✓ Saved to 'stocks_info_output.py'")
