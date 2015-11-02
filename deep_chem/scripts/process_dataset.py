"""
Process an input dataset into a format suitable for machine learning.
"""
import os
import cPickle as pickle
import gzip
import pandas as pd
import openpyxl as px
import numpy as np
import argparse
import csv
from rdkit import Chem
import subprocess
from vs_utils.utils import SmilesGenerator

def parse_args(input_args=None):
  """Parse command-line arguments."""
  parser = argparse.ArgumentParser()
  parser.add_argument("--input-file", required=1,
                      help="Input file with data.")
  parser.add_argument("--input-type", default="csv",
                      choices=["csv", "pandas", "sdf"],
                      help="Type of input file. If pandas, input must be a pkl.gz\n"
                           "containing a pandas dataframe. If sdf, should be in\n"
                           "gzipped sdf.gz file.")
  parser.add_argument("--fields", required=1, nargs="+",
                      help = "Names of fields.")
  parser.add_argument("--field-types", required=1, nargs="+",
                      choices=["string", "float", "list-string", "list-float", "ndarray"],
                      help="Type of data in fields.")
  parser.add_argument("--name", required=1,
                      help="Name of the dataset.")
  parser.add_argument("--out", required=1,
                      help="Folder to generate processed dataset in.")
  parser.add_argument("--prediction-endpoint", type=str, required=1,
                      help="Name of measured endpoint to predict.")
  parser.add_argument("--threshold", type=float, default=None,
                      help="Used to turn real-valued data into binary.")
  return parser.parse_args(input_args)

def generate_directories(name, out):
  """Generate processed dataset."""
  dataset_dir = os.path.join(out, name)
  if not os.path.exists(dataset_dir):
    os.makedirs(dataset_dir)
  fingerprint_dir = os.path.join(dataset_dir, "fingerprints")
  if not os.path.exists(fingerprint_dir):
    os.makedirs(fingerprint_dir)
  descriptor_dir = os.path.join(dataset_dir, "descriptors")
  if not os.path.exists(descriptor_dir):
    os.makedirs(descriptor_dir)
  target_dir = os.path.join(dataset_dir, "targets")
  if not os.path.exists(target_dir):
    os.makedirs(target_dir)
  shards_dir = os.path.join(dataset_dir, "shards")
  if not os.path.exists(shards_dir):
    os.makedirs(shards_dir)

  # Return names of files to be generated
  out_pkl = os.path.join(target_dir, "%s.pkl.gz" % name)
  out_sdf = os.path.join(shards_dir, "%s-0.sdf.gz" % name)
  return out_pkl, out_sdf

def parse_float_input(val):
  """Safely parses a float input."""
  # TODO(rbharath): Correctly parse float ranges.
  try:
    if val is None:
      return val
    else:
      fval = float(val)
      return fval
  except ValueError:
    if ">" in val or "<" in val or "-" in val:
      return np.nan

def generate_fingerprints(name, out):
  """Generates circular fingerprints for dataset."""
  dataset_dir = os.path.join(out, name)
  fingerprint_dir = os.path.join(dataset_dir, "fingerprints")
  shards_dir = os.path.join(dataset_dir, "shards")
  sdf = os.path.join(shards_dir, "%s-0.sdf.gz" % name)
  fingerprints = os.path.join(fingerprint_dir,
      "%s-fingerprints.pkl.gz" % name)
  subprocess.call(["python", "-m", "vs_utils.scripts.featurize",
                   "--scaffolds", "--smiles",
                   sdf, fingerprints,
                   "circular", "--size", "1024"])

def generate_descriptors(name, out):
  """Generates molecular descriptors for dataset."""
  dataset_dir = os.path.join(out, name)
  fingerprint_dir = os.path.join(dataset_dir, "descriptors")
  shards_dir = os.path.join(dataset_dir, "shards")
  sdf = os.path.join(shards_dir, "%s-0.sdf.gz" % name)
  descriptors = os.path.join(fingerprint_dir,
      "%s-descriptors.pkl.gz" % name)
  subprocess.call(["python", "-m", "vs_utils.scripts.featurize",
                   "--scaffolds", "--smiles",
                   sdf, descriptors,
                   "descriptors"])

def get_rows(input_file, input_type):
  """Returns an iterator over all rows in input_file"""
  # TODO(rbharath): This function loads into memory, which can be painful. The
  # right option here might be to create a class which internally handles data
  # loading.
  if input_type == "xlsx":
    W = px.load_workbook(xlsx_file, use_iterators=True)
    p = W.get_sheet_by_name(name="Sheet1")
    return p.iter_rows()
  elif input_type == "csv":
    with open(csv_file, "rb") as f:
      reader = csv.reader(f, delimiter="\t")
    return [row for row in reader]
  elif input_type == "pandas":
    with gzip.open(input_file) as f:
      df = pickle.load(f)
    return df.iterrows()
  elif input_type == "sdf":
    if ".gz" in input_file:
      with gzip.open(input_file) as f:
        supp = Chem.ForwardSDMolSupplier(f)
        mols = [mol for mol in supp if mol is not None]
      return mols
    else:
      with open(input_file) as f:
        supp  = Chem.ForwardSDMolSupplier(f)
        mols = [mol for mol in supp if mol is not None]
      return mols

def get_row_data(row, input_type, fields, field_types):
  """Extract information from row data."""
  if input_type == "xlsx":
    return [cell.internal_value for cell in row]
  elif input_type == "csv":
    return row 
  elif input_type == "pandas":
    # pandas rows are tuples (row_num, row_info)
    row, row_data = row[1], {}
    # pandas rows are keyed by field-name. Change to key by index to match
    # csv/xlsx handling
    for ind, field in enumerate(fields):
      row_data[ind] = row[field]
    return row_data
  elif input_type == "sdf":
    row_data, mol = {}, row
    for ind, (field, field_type) in enumerate(zip(fields, field_types)):
      # TODO(rbharath): SDF files typically don't have smiles, so we manually
      # generate smiles in this case. This is a kludgey solution...
      if field == "smiles":
        row_data[ind] = Chem.MolToSmiles(mol)
        continue
      if not mol.HasProp(field):
        row_data[ind] = None
      else:
        row_data[ind] = mol.GetProp(field)
    return row_data

def process_field(data, field_type):
  """Parse data in a field."""
  if field_type == "string":
    return data 
  elif field_type == "float":
    return parse_float_input(data)
  elif field_type == "list-string":
    return data.split(",")
  elif field_type == "list-float":
    return np.array(data.split(","))
  elif field_type == "ndarray":
    return data 

def generate_targets(input_file, input_type, fields, field_types, out_pkl,
    out_sdf, prediction_endpoint, threshold):
  """Process input data file."""
  rows, mols, smiles = [], [], SmilesGenerator()
  for row_index, raw_row in enumerate(get_rows(input_file, input_type)):
    print row_index
    # Skip row labels.
    if row_index == 0 or raw_row is None:
      continue
    row, row_data = {}, get_row_data(raw_row, input_type, fields, field_types)
    for ind, (field, field_type) in enumerate(zip(fields, field_types)):
      if field == prediction_endpoint and threshold is not None:
        raw_val = process_field(row_data[ind], field_type)
        row[field] = 1 if raw_val > threshold else 0 
      else:
        row[field] = process_field(row_data[ind], field_type)
    # TODO(rbharath): This patch is only in place until the smiles/sequence
    # support is fixed.
    if row["smiles"] is None:
      # This multiplication kludge guarantees unique smiles.
      mol = Chem.MolFromSmiles("C"*row_index)
    else:
      mol = Chem.MolFromSmiles(row["smiles"])
    row["smiles"] = smiles.get_smiles(mol)
    mols.append(mol)
    rows.append(row)
  df = pd.DataFrame(rows)
  # Write pkl.gz file
  with gzip.open(out_pkl, "wb") as f:
    pickle.dump(df, f, pickle.HIGHEST_PROTOCOL)
  # Write sdf.gz file
  with gzip.open(out_sdf, "wb") as gz:
    w = Chem.SDWriter(gz)
    for mol in mols:
      w.write(mol)
    w.close()

def main():
  args = parse_args()
  out_pkl, out_sdf = generate_directories(args.name, args.out)
  generate_targets(args.input_file, args.input_type, args.fields,
      args.field_types, out_pkl, out_sdf, args.prediction_endpoint, args.threshold)
  generate_fingerprints(args.name, args.out)
  generate_descriptors(args.name, args.out)

if __name__ == "__main__":
  main()
