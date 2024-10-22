import pandas as pd
import numpy as np
import requests
from datetime import datetime
import argparse
import sys
import logging
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def read_transactions(file_path):
    try:
        df = pd.read_excel(file_path, skiprows=4) # todo: too specific to my input file type where the data table started from the 5th row, skip_rows needs to be modified
        
        logging.info(f"Columns in the file: {df.columns.tolist()}")
        
        column_mappings = {
            'Sr. No.': ['Sr. No.', 'Sr No', 'Serial No'],
            'Transaction Date': ['Transaction Date', 'Date'],
            'Scheme': ['Scheme', 'Fund Name'],
            'Units': ['Units'],
            'Gross Amount': ['Gross Amount', 'Amount']
        }
        
        actual_columns = {}
        for expected_col, possible_names in column_mappings.items():
            found = False
            for name in possible_names:
                if name in df.columns:
                    actual_columns[expected_col] = name
                    found = True
                    break
            if not found:
                raise ValueError(f"Could not find a column matching '{expected_col}'")
        
        df = df.rename(columns={v: k for k, v in actual_columns.items()})
        
        df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], format='%d-%m-%Y', errors='coerce')
        df['Units'] = pd.to_numeric(df['Units'], errors='coerce')
        df['Gross Amount'] = pd.to_numeric(df['Gross Amount'], errors='coerce')
        
        df = df.dropna(subset=['Transaction Date', 'Units', 'Gross Amount'])
        
        if df.empty:
            raise ValueError("No valid data remaining after removing null values")
        
        return df
    except Exception as e:
        logging.error(f"Error reading transaction file: {e}")
        return None

def fetch_nav_data(api_url):
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        
        nav_data = pd.DataFrame(data['data'])
        nav_data['date'] = pd.to_datetime(nav_data['date'], format='%d-%m-%Y')
        nav_data['nav'] = pd.to_numeric(nav_data['nav'])
        nav_data = nav_data.sort_values('date')
        
        meta_data = data['meta']
        logging.info(f"Fetched data for: {meta_data['scheme_name']}")
        
        return nav_data, meta_data['scheme_name']
    except requests.RequestException as e:
        logging.error(f"Error fetching NAV data: {e}")
        return None, None

def calculate_portfolio_value(transactions, nav_data, is_potential=False):
    if transactions.empty or nav_data.empty:
        logging.error("Empty transactions or NAV data")
        return 0, pd.DataFrame()
    
    merged = pd.merge_asof(transactions.sort_values('Transaction Date'),
                           nav_data.sort_values('date'),
                           left_on='Transaction Date',
                           right_on='date',
                           direction='forward')
    
    if merged.empty:
        logging.error("No matching dates found between transactions and NAV data")
        return 0, pd.DataFrame()
    
    current_nav = nav_data.iloc[-1]['nav']
    
    merged['Current NAV'] = current_nav
    merged['Current Value'] = merged['Units'] * current_nav
    
    if is_potential:
        merged['Original Units'] = merged['Gross Amount'] / merged['nav']
        merged['Units Difference'] = merged['Units'] - merged['Original Units']
        merged['Value Difference'] = merged['Current Value'] - merged['Gross Amount']
    
    total_value = merged['Current Value'].sum()
    
    return total_value, merged

def fuzzy_match_scheme(scheme_name, transactions_schemes, threshold=70):
    best_match = process.extractOne(scheme_name, transactions_schemes, scorer=fuzz.token_sort_ratio)
    if best_match and best_match[1] >= threshold:
        return best_match[0]
    return None

def compare_portfolios(transactions, my_stock_api, potential_stock_api):
    my_nav_data, my_scheme_name = fetch_nav_data(my_stock_api)
    potential_nav_data, potential_scheme_name = fetch_nav_data(potential_stock_api)
    
    if my_nav_data is None or potential_nav_data is None:
        return None, None, None
    
    unique_schemes = transactions['Scheme'].unique()
    matched_scheme = fuzzy_match_scheme(my_scheme_name, unique_schemes)
    
    if matched_scheme is None:
        logging.error(f"No matching scheme found for: {my_scheme_name}")
        logging.info(f"Available schemes in transactions: {unique_schemes}")
        return None, None, None
    
    logging.info(f"Matched API scheme '{my_scheme_name}' to transaction scheme '{matched_scheme}'")
    
    input_transactions = transactions[transactions['Scheme'] == matched_scheme]
    
    if input_transactions.empty:
        logging.error(f"No transactions found for the matched scheme: {matched_scheme}")
        return None, None, None
    
    my_portfolio_value, my_detailed_calc = calculate_portfolio_value(input_transactions, my_nav_data)
    
    transactions_potential = input_transactions.copy()
    potential_navs = potential_nav_data.set_index('date')['nav']
    transactions_potential['Units'] = transactions_potential.apply(
        lambda row: row['Gross Amount'] / potential_navs.loc[row['Transaction Date']:].iloc[0],
        axis=1
    )
    potential_portfolio_value, potential_detailed_calc = calculate_portfolio_value(transactions_potential, potential_nav_data, is_potential=True)
    
    comparison = {
        'Input Stock/MF (API)': my_scheme_name,
        'Input Stock/MF (Matched)': matched_scheme,
        'Potential Stock/MF': potential_scheme_name,
        'Input Portfolio Value': my_portfolio_value,
        'Potential Portfolio Value': potential_portfolio_value,
        'Difference': potential_portfolio_value - my_portfolio_value
    }
    
    return comparison, my_detailed_calc, potential_detailed_calc

def save_results(comparison, my_detailed_calc, potential_detailed_calc, output_file):
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        pd.DataFrame([comparison]).to_excel(writer, sheet_name='Summary', index=False)
        my_detailed_calc.to_excel(writer, sheet_name='Input Portfolio', index=False)
        potential_detailed_calc.to_excel(writer, sheet_name='Potential Portfolio', index=False)
    
    logging.info(f"Comparison results and detailed calculations saved to {output_file}")

def parse_arguments():
    parser = argparse.ArgumentParser(description='Compare specific stock/MF with a potential alternative based on transaction history.')
    parser.add_argument('input_file', help='Path to the input Excel file containing transaction data')
    parser.add_argument('my_stock_api', help='API URL for your current stock/MF')
    parser.add_argument('potential_stock_api', help='API URL for the potential stock/MF to compare')
    parser.add_argument('--output', default='portfolio_comparison.xlsx', help='Path for the output Excel file (default: portfolio_comparison.xlsx)')
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    transactions = read_transactions(args.input_file)
    if transactions is None or transactions.empty:
        logging.error("No valid transaction data. Exiting.")
        sys.exit(1)
    
    logging.info(f"First few rows of the processed DataFrame:\n{transactions.head()}")
    
    comparison, my_detailed_calc, potential_detailed_calc = compare_portfolios(transactions, args.my_stock_api, args.potential_stock_api)
    if comparison is None:
        logging.error("Failed to compare portfolios. Exiting.")
        sys.exit(1)
    
    save_results(comparison, my_detailed_calc, potential_detailed_calc, args.output)

if __name__ == "__main__":
    main()
