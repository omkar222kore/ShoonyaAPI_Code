
#this is code whre you need to paste in ('13-09-2024 10:00', 'MANAPPURAM'), this way and make sure all 
# the stocks are placed in folder whih will give the output with backtest .

import pandas as pd
import os

# Set the directory where the Excel sheets are stored
excel_directory = 'D:\\AlgoRepo\\ShoonyaAPI_Code\\Testing_Use\\Stocks_DATA'

# Stock info in format: (entry time, stock symbol)
stocks_info = [
    ('01-02-2025 09:45', 'TRITURBINE'),
    ('03-02-2025 10:00', 'SUVENPHAR'),
    ('06-02-2025 10:00', 'DRREDDY'),
    ('06-02-2025 10:45', 'DEEPAKNTR'),
    ('06-02-2025 10:45', 'JUSTDIAL'),
    ('07-02-2025 10:00', 'TATASTEEL'),
    ('13-02-2025 10:00', 'KOTAKBANK'),
    ('13-02-2025 10:00', 'EMCURE'),
    ('20-02-2025 10:00', 'TATATECH'),
    ('20-02-2025 10:00', 'JUSTDIAL'),
    ('25-02-2025 10:00', 'GLAND'),
    ('27-02-2025 10:00', 'SHRIRAMFIN'),
    ('27-02-2025 10:00', 'BANDHANBNK'),
    ('06-03-2025 10:45', 'ADANIENSOL'),
    ('12-03-2025 10:00', 'HINDPETRO'),
    ('12-03-2025 10:00', 'NLCINDIA'),
    ('12-03-2025 10:00', 'IOC'),
    ('17-03-2025 09:45', 'MAHSEAMLES'),
    ('17-03-2025 10:00', 'SRF'),
    ('20-03-2025 09:45', 'IRFC'),
    ('20-03-2025 09:45', 'PNCINFRA'),
    ('24-03-2025 10:00', 'BEML'),
    ('24-03-2025 10:00', 'HYUNDAI'),
    ('24-03-2025 10:00', 'GSPL'),
    ('25-03-2025 10:00', 'CARBORUNIV'),
    ('26-03-2025 10:00', 'MARICO'),
    ('28-03-2025 10:00', 'NIVABUPA'),
    ('01-04-2025 10:00', 'SUMICHEM'),
    ('04-04-2025 10:00', 'CASTROLIND'),
    ('11-04-2025 09:45', 'HUDCO'),
    ('15-04-2025 10:45', 'RADICO'),
    ('16-04-2025 10:00', 'FEDERALBNK'),
    ('16-04-2025 10:00', 'BANKINDIA'),
    ('16-04-2025 10:00', 'PNB'),
    ('17-04-2025 10:00', 'INDIACEM'),
    ('21-04-2025 10:00', 'UNIONBANK'),
    ('25-04-2025 10:00', 'SBILIFE'),
    ('25-04-2025 10:00', 'IEX'),
    ('28-04-2025 10:00', 'KALYANKJIL'),
    ('29-04-2025 09:45', 'GODIGIT'),
    ('29-04-2025 09:45', 'NBCC'),
    ('29-04-2025 10:00', 'IGL'),
    ('30-04-2025 10:00', 'PRESTIGE'),
    ('02-05-2025 10:00', 'PNBHOUSING'),
    ('05-05-2025 10:00', 'INDHOTEL'),
    ('06-05-2025 10:00', 'HEROMOTOCO'),
    ('06-05-2025 10:00', 'M&M'),
    ('06-05-2025 10:00', 'HAL'),
    ('08-05-2025 10:00', 'KOTAKBANK'),
    ('08-05-2025 10:00', 'MOTHERSON'),
    ('12-05-2025 09:45', 'KANSAINER'),
    ('12-05-2025 09:45', 'TATAMOTORS'),
    ('12-05-2025 10:00', 'PCBL'),
    ('12-05-2025 10:00', 'RKFORGE'),
    ('12-05-2025 10:00', 'RHIM'),
    ('13-05-2025 09:45', 'HEROMOTOCO'),
    ('15-05-2025 09:45', 'FINPIPE'),
    ('15-05-2025 09:45', 'KPIL'),
    ('15-05-2025 10:00', 'CREDITACC'),
    ('15-05-2025 10:00', 'CYIENT'),
    ('15-05-2025 10:45', 'ASTERDM'),
    ('19-05-2025 09:45', 'DATAPATTNS'),
    ('19-05-2025 10:45', 'SARDAEN'),
    ('19-05-2025 10:45', 'APLLTD'),
    ('21-05-2025 10:00', 'METROPOLIS'),
    ('22-05-2025 10:00', 'RRKABEL'),
    ('22-05-2025 10:00', 'NTPCGREEN'),
    ('23-05-2025 10:00', 'HEROMOTOCO'),
    ('23-05-2025 10:00', 'VBL')
]

# Result storage
results = []

# Initial investment per stock
initial_investment = 200000

# Define 15:15 time for cutting positions
cutoff_time = pd.to_datetime('11-10-2024 15:15', format='%d-%m-%Y %H:%M')

# Iterate over each stock and its respective entry time
for entry_time_str, stock_name in stocks_info:

    excel_file_name = f"{stock_name}-EQ.xlsx"
    excel_file_path = os.path.join(excel_directory, excel_file_name)

    try:
        # Load stock data
        stock_data = pd.read_excel(excel_file_path, usecols=['time', 'intc'])
        stock_data['time'] = pd.to_datetime(stock_data['time'], format='%d-%m-%Y %H:%M:%S', errors='coerce')

        # Sort the data, ensuring latest data is processed correctly
        stock_data.sort_values(by='time', ascending=True, inplace=True)

        # Convert entry_time_str to timestamp
        entry_time = pd.to_datetime(entry_time_str, format='%d-%m-%Y %H:%M')

        # Add 15 minutes to the entry time
        testing_start_time = entry_time + pd.Timedelta(minutes=2)

        # Find the entry row
        entry_row = stock_data[stock_data['time'] == testing_start_time]

        if not entry_row.empty:
            entry_price = entry_row['intc'].values[0]
            qty = int(initial_investment / entry_price)  # Calculate quantity of stocks

            # Set stop loss and target prices
            profit_target = entry_price * 0.985  # 0.8% profit target
            stop_loss = entry_price * 1.006    # 0.5% stop loss

            # Filter subsequent data (after the testing start time)
            subsequent_data = stock_data[stock_data['time'] > testing_start_time]

            stop_or_tgt_hit = False
            for index, row in subsequent_data.iterrows():
                current_price = row['intc']
                current_time = row['time']

                # Check stop loss first to capture the loss
                if current_price > stop_loss:
                    profit_loss_amount = -((current_price - entry_price) * qty)
                    results.append([stock_name, entry_time, current_time, current_price, 'Loss', profit_loss_amount])
                    print(f"Stop loss hit at {current_time}: {current_price:.2f}, Loss: {profit_loss_amount:.2f}")
                    stop_or_tgt_hit = True
                    break

                # Check profit target after stop loss
                elif current_price < profit_target:
                    profit_loss_amount = -((current_price - entry_price) * qty)
                    results.append([stock_name, entry_time, current_time, current_price, 'Profit', profit_loss_amount])
                    print(f"Profit target hit at {current_time}: {current_price:.2f}, Profit: {profit_loss_amount:.2f}")
                    stop_or_tgt_hit = True
                    break

            # Ensure the trade is closed at cutoff time if no stop-loss or target is hit
            cutoff_row = stock_data[stock_data['time'] == cutoff_time]
            if not stop_or_tgt_hit and not cutoff_row.empty:
                cutoff_price = cutoff_row['intc'].values[0]
                profit_loss_amount = -((cutoff_price - entry_price) * qty)
                results.append([stock_name, entry_time, cutoff_time, cutoff_price, 'Cut at 15:15', profit_loss_amount])
                print(f"No SL or TGT hit. Position closed at {cutoff_time}: {cutoff_price:.2f}, PnL: {profit_loss_amount:.2f}")
            elif not stop_or_tgt_hit and cutoff_row.empty:
                print(f"No data found for {stock_name} at the cutoff time (15:15).")

        else:
            print(f"No entry found for {stock_name} at {testing_start_time}")

    except Exception as e:
        print(f"An error occurred for {stock_name}: {e}")

# Create a DataFrame for the results
results_df = pd.DataFrame(results, columns=['Stock Name', 'Entry Time', 'Hit/Exit Time', 'Price', 'Status', 'Profit/Loss Amount'])

# Save the results to an Excel file
output_file_path = 'C:\\Users\\omkar\\Downloads\\stock_results_New_0930TO11_spec.xlsx'
results_df.to_excel(output_file_path, index=False)

print(f"Results saved to {output_file_path}")
print(f"Total results: {len(results)}")
