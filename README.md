# Mutual Fund Evaluator & Simulator
Have always wondered how to evaluate my investment advisor's performance, is he picking the right MFs in the category? Are they even beating the benchmark index? Are they beating their peers (alpha)? If not, do they have lesser volatility (beta)?

Existing platforms all talk in absolute terms and give 1Y, 3Y, and 5Y returns comparison, but what if I wanted to simulate an alternate MF purchase to know how much difference it would have had in my specific context for my purchase window?

- Input 1: MF transaction history
- Input 2: API endpoint of the MF in my portfolio I wanted to simulate (kudos to api.mfapi.in for free data access)
- Input 3: API endpoint of the peer MF (identified from step 2) I want to compare against to pull their date-specific NAVs

## How to find historic MF NAV data?
https://www.mfapi.in/

## How to run?
python run.py [-h] [--output OUTPUT] input_file my_stock_api potential_stock_api

Compare specific stock/MF with a potential alternative based on transaction history.

positional arguments:
  input_file           Path to the input Excel file containing transaction data
  my_stock_api         API URL for your current stock/MF
  potential_stock_api  API URL for the potential stock/MF to compare

options:
  -h, --help           show this help message and exit
  --output OUTPUT      Path for the output Excel file (default: portfolio_comparison.xlsx)

e.g.: python run.py input.xlsx https://api.mfapi.in/mf/104908 https://api.mfapi.in/mf/101065
