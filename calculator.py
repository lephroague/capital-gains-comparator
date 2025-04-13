#!/usr/bin/env python3
"""
Compute yearly capital gains for assets using FIFO, LIFO, and Average Cost methods.

Reads a CSV file of historical transactions and writes a report as a CSV file.
Note:
    To produce a compliant transactions.csv file, you need to export to CSV all of your
    transactions from your exchange. You should then retain the asset name and quantity
    transacted. Then you need to classify each transaction type as either BUY or SELL.
    Finally, you need to convert the asset price and transaction value to CAD.

    The CSV file should have the following columns:
    - UTC Timestamp: The date and time of the transaction in UTC.
    - Transaction Type: The type of transaction, either "BUY" or "SELL".
    - Asset: The name of the asset (e.g., "BTC", "ETH").
    - Quantity: The quantity of the asset transacted.
    - Asset Price in CAD: The price of the asset in CAD at the time of the transaction.
    - Transaction Value in CAD: The total value of the transaction in CAD.
    - Comments:
        - The CSV file should not contain any header rows or footers.
        - The CSV file should not contain any empty rows.
        - The CSV file should not contain any comments.
        - The CSV file should not contain any blank lines.
        - The CSV file should not contain any extra columns.

The script uses Poetry for dependency management and can be run from the command line.
Usage:
    python calculator.py --csv-file transactions.csv --output-file capital_gains_report.csv
    python calculator.py --csv-file transactions.csv --output-file capital_gains_report.csv --verbose

Additional Output:
    All logs (including warnings) will be written to a log file in the 'logs' folder,
    and the output report will be written in the 'reports' folder (with run date suffix).
    A separate CSV file will also be generated in the 'reports' folder listing the enhanced
    SELL transactions where the purchase price was assumed to be 0.
"""

import argparse
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

# Constants
DEFAULT_CSV_PATH = "transactions.csv"
DEFAULT_OUTPUT_BASENAME = "capital_gains_report.csv"
REQUIRED_COLUMNS = [
    "UTC Timestamp",
    "Transaction Type",
    "Asset",
    "Quantity",
    "Asset Price in CAD",
    "Transaction Value in CAD",
]

LOGS_FOLDER = "logs"
REPORTS_FOLDER = "reports"

# Configure logging early so it's available everywhere.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CapitalGainsError(Exception):
    """Base exception for capital gains calculation errors."""
    pass


class InvalidDataError(CapitalGainsError):
    """Raised when input data is invalid."""
    pass


def validate_dataframe(df: pd.DataFrame) -> None:
    """Validate that the DataFrame has the required columns and is not empty."""
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise InvalidDataError(f"Missing required columns: {', '.join(missing_cols)}")
    if df.empty:
        raise InvalidDataError("Input file contains no data")


def process_buy(row: pd.Series, buy_lots_fifo: dict, buy_lots_lifo: dict, avg_totals: dict) -> None:
    """Process a BUY transaction."""
    ts = row["UTC Timestamp"]
    asset = row["Asset"]
    quantity = float(row["Quantity"])
    unit_price = float(row["Asset Price in CAD"])
    total_value = float(row["Transaction Value in CAD"])
    lot = {"quantity": quantity, "price": unit_price, "timestamp": ts}
    buy_lots_fifo[asset].append(lot.copy())
    buy_lots_lifo[asset].append(lot.copy())
    avg_totals[asset]["total_cost"] += total_value
    avg_totals[asset]["quantity"] += quantity


def process_sell(
    row: pd.Series,
    buy_lots_fifo: dict,
    buy_lots_lifo: dict,
    avg_totals: dict,
    fifo_gains: dict,
    lifo_gains: dict,
    avg_cost_gains: dict,
    enhanced_transactions: List[Dict]
) -> None:
    """Process a SELL transaction, handling missing BUY data by assuming cost=0 for unmatched quantity."""
    ts = row["UTC Timestamp"]
    year = ts.year
    asset = row["Asset"]
    quantity = float(row["Quantity"])
    total_value = float(row["Transaction Value in CAD"])
    sale_price = total_value / quantity

    # For FIFO: determine available matched quantity.
    available_fifo = sum(lot["quantity"] for lot in buy_lots_fifo[asset])
    matched_fifo = min(quantity, available_fifo)
    remaining_fifo = matched_fifo
    while remaining_fifo > 0 and buy_lots_fifo[asset]:
        lot = buy_lots_fifo[asset][0]
        if lot["quantity"] > remaining_fifo:
            cost_basis = remaining_fifo * lot["price"]
            fifo_gains[asset][year] += remaining_fifo * sale_price - cost_basis
            lot["quantity"] -= remaining_fifo
            remaining_fifo = 0
        else:
            cost_basis = lot["quantity"] * lot["price"]
            fifo_gains[asset][year] += lot["quantity"] * sale_price - cost_basis
            remaining_fifo -= lot["quantity"]
            buy_lots_fifo[asset].pop(0)
    # Enhanced portion for FIFO.
    enhanced_qty = quantity - matched_fifo
    if enhanced_qty > 0:
        fifo_gains[asset][year] += enhanced_qty * sale_price  # cost basis assumed 0
        # Record enhanced transaction (recorded only once per SELL).
        enhanced_transactions.append({
            "UTC Timestamp": row["UTC Timestamp"],
            "Asset": asset,
            "Transaction Type": row["Transaction Type"],
            "Quantity": quantity,
            "Matched Quantity": matched_fifo,
            "Enhanced Quantity": enhanced_qty,
            "Sale Price in CAD": sale_price,
            "Enhanced Transaction Value in CAD": enhanced_qty * sale_price,
            "Data Status": "enhanced",
        })

    # For LIFO: process similarly.
    available_lifo = sum(lot["quantity"] for lot in buy_lots_lifo[asset])
    matched_lifo = min(quantity, available_lifo)
    remaining_lifo = matched_lifo
    while remaining_lifo > 0 and buy_lots_lifo[asset]:
        lot = buy_lots_lifo[asset][-1]
        if lot["quantity"] > remaining_lifo:
            cost_basis = remaining_lifo * lot["price"]
            lifo_gains[asset][year] += remaining_lifo * sale_price - cost_basis
            lot["quantity"] -= remaining_lifo
            remaining_lifo = 0
        else:
            cost_basis = lot["quantity"] * lot["price"]
            lifo_gains[asset][year] += lot["quantity"] * sale_price - cost_basis
            remaining_lifo -= lot["quantity"]
            buy_lots_lifo[asset].pop()

    if quantity - matched_lifo > 0:
        lifo_gains[asset][year] += (quantity - matched_lifo) * sale_price

    # For Average Cost:
    available_avg = avg_totals[asset]["quantity"]
    matched_avg = min(quantity, available_avg)
    # If no holdings, assume cost=0.
    avg_cost = (avg_totals[asset]["total_cost"] / available_avg) if available_avg > 0 else 0.0
    avg_cost_gains[asset][year] += quantity * (sale_price - avg_cost)
    # Update average totals.
    avg_totals[asset]["quantity"] = max(0, avg_totals[asset]["quantity"] - quantity)
    avg_totals[asset]["total_cost"] = max(0, avg_totals[asset]["total_cost"] - matched_avg * avg_cost)


def process_transactions(
    df: pd.DataFrame,
) -> Tuple[Dict[str, Dict[int, float]], Dict[str, Dict[int, float]], Dict[str, Dict[int, float]], List[Dict]]:
    """
    Process transactions to calculate yearly capital gains using FIFO, LIFO, and Average Cost methods.

    This function delegates BUY and SELL transactions to dedicated helper functions.
    If a SELL transaction cannot be fully matched to prior BUYs, the missing portion is assumed to have a cost of 0.
    Enhanced SELL transactions are recorded for further validation.

    Args:
        df: DataFrame containing transactions with required columns.

    Returns:
        Tuple of (fifo_gains, lifo_gains, avg_cost_gains, enhanced_transactions).
    """
    validate_dataframe(df)
    logger.info("Starting transaction processing")
    df.sort_values("UTC Timestamp", inplace=True)

    fifo_gains = defaultdict(lambda: defaultdict(float))
    lifo_gains = defaultdict(lambda: defaultdict(float))
    avg_cost_gains = defaultdict(lambda: defaultdict(float))

    buy_lots_fifo = defaultdict(list)
    buy_lots_lifo = defaultdict(list)
    avg_totals = defaultdict(lambda: {"quantity": 0.0, "total_cost": 0.0})
    enhanced_transactions: List[Dict] = []

    for _, row in df.iterrows():
        ttype = row["Transaction Type"].strip().upper()
        if ttype == "BUY":
            process_buy(row, buy_lots_fifo, buy_lots_lifo, avg_totals)
        elif ttype == "SELL":
            process_sell(row, buy_lots_fifo, buy_lots_lifo, avg_totals,
                         fifo_gains, lifo_gains, avg_cost_gains, enhanced_transactions)

    logger.info("Completed processing transactions")
    return fifo_gains, lifo_gains, avg_cost_gains, enhanced_transactions


def generate_report_df(
    fifo_gains: Dict[str, Dict[int, float]],
    lifo_gains: Dict[str, Dict[int, float]],
    avg_cost_gains: Dict[str, Dict[int, float]],
) -> pd.DataFrame:
    """
    Generate a DataFrame report comparing FIFO, LIFO, and Average Cost gains per asset and per year.

    The DataFrame will have columns: Year, Asset, LIFO G&L, FIFO G&L, ACB G&L.

    Returns:
        Report DataFrame.
    """
    rows = []
    assets = sorted(set(list(fifo_gains.keys()) + list(lifo_gains.keys()) + list(avg_cost_gains.keys())))
    for asset in assets:
        years = set(fifo_gains[asset].keys()).union(lifo_gains[asset].keys(), avg_cost_gains[asset].keys())
        for year in sorted(years):
            rows.append({
                "Year": year,
                "Asset": asset,
                "LIFO G&L": lifo_gains[asset].get(year, 0.0),
                "FIFO G&L": fifo_gains[asset].get(year, 0.0),
                "ACB G&L": avg_cost_gains[asset].get(year, 0.0),
            })
    df_report = pd.DataFrame(rows, columns=["Year", "Asset", "LIFO G&L", "FIFO G&L", "ACB G&L"])
    df_report.sort_values(by=["Year", "Asset"], ascending=[False, True], inplace=True)
    return df_report


def setup_logging(run_date: str) -> None:
    """Configure logging to output to both console and a file with the run date."""
    os.makedirs(LOGS_FOLDER, exist_ok=True)
    log_filename = os.path.join(LOGS_FOLDER, f"calculator_{run_date}.log")
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info(f"Logging initialized. Log file: {log_filename}")


def main() -> None:
    """
    Parse arguments, process transactions, and write the capital gains report to a CSV file.
    Also writes enhanced transactions (with assumed purchase price 0) to a separate CSV file for validation.
    """
    parser = argparse.ArgumentParser(
        description="Compute yearly capital gains using FIFO, LIFO, and Average Cost methods."
    )
    parser.add_argument(
        "--csv-file",
        default=DEFAULT_CSV_PATH,
        help=f"Path to CSV file containing transactions (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--output-file",
        default=DEFAULT_OUTPUT_BASENAME,
        help=f"Base name for output CSV report (default: {DEFAULT_OUTPUT_BASENAME})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging for detailed output.",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")

    # Determine run date and set up output filenames.
    run_date = datetime.now().strftime("%Y%m%d")
    os.makedirs(REPORTS_FOLDER, exist_ok=True)
    base_name, ext = os.path.splitext(args.output_file)
    report_filename = f"{base_name}_{run_date}{ext}"
    report_path = Path(REPORTS_FOLDER) / report_filename
    enhanced_filename = f"enhanced_transactions_{run_date}.csv"
    enhanced_path = Path(REPORTS_FOLDER) / enhanced_filename

    setup_logging(run_date)

    csv_path = Path(args.csv_file)
    try:
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        logger.info(f"Reading transactions from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["UTC Timestamp"])

        fifo_gains, lifo_gains, avg_cost_gains, enhanced_transactions = process_transactions(df)
        report_df = generate_report_df(fifo_gains, lifo_gains, avg_cost_gains)
        report_df.to_csv(report_path, index=False)
        logger.info(f"Capital gains report written to {report_path}")
        print(f"Report written to {report_path}")

        # Write enhanced transactions to separate CSV if any exist.
        if enhanced_transactions:
            enhanced_df = pd.DataFrame(enhanced_transactions)
            enhanced_df.to_csv(enhanced_path, index=False)
            logger.info(f"Enhanced transactions report written to {enhanced_path}")
            print(f"Enhanced transactions report written to {enhanced_path}")
        else:
            logger.info("No enhanced transactions to report.")

    except (FileNotFoundError, pd.errors.EmptyDataError) as e:
        logger.error(f"File error: {e}")
        print(f"\nError: {e}")
    except InvalidDataError as e:
        logger.error(f"Data validation error: {e}")
        print(f"\nError: {e}")
    except CapitalGainsError as e:
        logger.error(f"Processing error: {e}")
        print(f"\nError: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print("\nAn unexpected error occurred. Check the logs for details.")


if __name__ == "__main__":
    main()
