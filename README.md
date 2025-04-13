# TheInternCalc

TheInternCalc is a Python script that computes yearly capital gains for assets using three methodologies: FIFO, LIFO, and Average Cost (ACB). It reads a CSV file of historical transactions, processes these transactions, and generates a capital gains report as well as an optional enhanced transactions report.

## Input CSV File Requirements

Your input CSV file **must** include the following columns (with no headers, footers, extra rows, or comments):

- **UTC Timestamp** – Date and time of the transaction in UTC (parseable by Python).
- **Transaction Type** – Either `"BUY"` or `"SELL"` (case insensitive).
- **Asset** – The asset name (e.g., `BTC`, `ETH`, etc.).
- **Quantity** – Quantity of the asset transacted (numeric value).
- **Asset Price in CAD** – Unit price in Canadian Dollars at the time of the transaction.
- **Transaction Value in CAD** – Total value of the transaction in CAD.

## Capital Gains Methodologies

1. **FIFO (First-In-First-Out)**  
   - Matches sell transactions with the earliest available buy transactions.
   - Unmatched portions (if any) are assumed to have a purchase cost of zero.

2. **LIFO (Last-In-First-Out)**  
   - Matches sell transactions with the most recent buy transactions.
   - Unmatched portions are treated similarly by assuming zero cost.

3. **Average Cost (ACB)**  
   - Calculates the average cost per unit based on total cost and quantity.
   - Capital gains are computed as the difference between the sale price and the average cost.
   - As assets are sold, the average cost and remaining total cost are updated accordingly.

## How to Use the Script

### Step 1: Prepare Your CSV File
- Ensure your CSV file follows the structure described above.
- Place your CSV file (e.g., `transactions.csv`) in the project directory or specify its path when running the script.

### Step 2: Install Dependencies
- This project uses [Poetry](https://python-poetry.org/) for dependency management.
- Verify that you have Python (>=3.13) installed.
- Run the following command in your project directory:

  ```sh
  poetry install
    ```

### Step 3: Run the Script
To generate the capital gains report, use the command:

For detailed (verbose) logging, add the --verbose flag:

### Step 4: Review the Outputs
Capital Gains Report:
The report is saved under the reports folder with the run date appended (e.g., capital_gains_report_20250406.csv).

#### Enhanced Transactions Report:
If any sell transactions could not be fully matched with previous buys, they are recorded separately in a CSV file (e.g., enhanced_transactions_20250406.csv) in the reports folder.

#### Logs:
All logs are written to the logs folder. Check these for any informational messages, warnings, or errors in case of issues.

### Step 5: Troubleshooting
#### Invalid Input:
If required columns are missing or the CSV file is empty, the script will raise an error. Ensure that your CSV meets the criteria.

#### File Not Found:
Verify the file path provided to the --csv-file option exists.

#### For More Details:
Check the log files stored in the logs folder to help diagnose any issues.

## Additional Information
The script sorts transactions by UTC Timestamp to ensure chronological processing.
Command line parameters allow you to customize the input and output file paths.

For further insights on the code and the underlying implementation details, review:
calculator.py
pyproject.toml

## License
This software is released under a Non-Commercial Software License and Disclaimer. See the LICENSE file for details.

Happy Calculating!