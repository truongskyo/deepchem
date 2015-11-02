"""
Utility functions to preprocess datasets before building models.
"""
__author__ = "Bharath Ramsundar"
__copyright__ = "Copyright 2015, Stanford University"
__license__ = "LGPL"

import numpy as np
import warnings
from deep_chem.utils.analysis import summarize_distribution

def to_arrays(train, test, datatype):
  """Turns train/test into numpy array."""
  if datatype == "vector":
    X_train, y_train, W_train = dataset_to_numpy(train)
    X_test, y_test, W_test = dataset_to_numpy(test)
  elif datatype == "tensor":
    X_train, y_train, W_train = tensor_dataset_to_numpy(train)
    X_test, y_test, W_test = tensor_dataset_to_numpy(test)
  else:
    raise ValueError("Improper datatype.")
  return (train, X_train, y_train, W_train), (test, X_test, y_test, W_test)

def transform_inputs(X, input_transforms):
  """Transform the input feature data."""
  (n_samples, n_features) = np.shape(X)
  Z = np.zeros(np.shape(X))
  # Meant to be done after normalize
  trunc = 10
  for feature in range(n_features):
    feature_data = X[:, feature]
    for input_transform in input_transforms:
      # TODO(rbharath): This code isn't really normalizing. It's doing
      # something trickier to ensure that the binary fingerprints aren't
      # normalized while real-valued descriptors are. Refactor/Rename this to
      # make this distinction clearer.
      if input_transform == "normalize":
        if np.amax(feature_data) > trunc or np.amin(feature_data) < -trunc:
          mean, std = np.mean(feature_data), np.std(feature_data)
          feature_data = feature_data - mean 
          if std != 0.:
            feature_data = feature_data / std
          feature_data[feature_data > trunc] = trunc 
          feature_data[feature_data < -trunc] = -trunc
          if np.amax(feature_data) > trunc or np.amin(feature_data) < -trunc:
            raise ValueError("Truncation failed on feature %d" % feature)
      else:
        raise ValueError("Unsupported Input Transform")
    Z[:, feature] = feature_data
  return Z

def transform_outputs(y, W, output_transforms, weight_positives=True):
  """Tranform the provided outputs

  Parameters
  ----------
  y: ndarray 
    Labels
  W: ndarray
    Weights 
  output_transforms: dict 
    dict mapping target names to list of label transforms. Each list
    element must be "1+max-val", "log", "normalize". The transformations are
    performed in the order specified. An empty list
    corresponds to no transformations. Only for regression outputs.
  """
  sorted_targets = sorted(output_transforms.keys())
  endpoints = sorted_targets
  transforms = output_transforms.copy()
  for task, target in enumerate(endpoints):
    output_transforms = transforms[target]
    for output_transform in output_transforms:
      if output_transform == "log":
        y[:, task] = np.log(y[:, task])
      elif output_transform == "1+max-val":
        maxval = np.amax(y[:, task])
        y[:, task] = 1 + maxval - y[:, task]
      elif output_transform == "normalize":
        task_data = y[:, task]
        if task < len(sorted_targets):
          # Only elements of y with nonzero weight in W are true labels.
          nonzero = (W[:, task] != 0)
        else:
          nonzero = np.ones(np.shape(y[:, task]), dtype=bool)
        # Set mean and std of present elements
        mean = np.mean(task_data[nonzero])
        std = np.std(task_data[nonzero])
        task_data[nonzero] = task_data[nonzero] - mean
        # Set standard deviation to one
        if std == 0.:
          print "Variance normalization skipped for task %d due to 0 stdev" % task
          continue
        task_data[nonzero] = task_data[nonzero] / std
      else:
        raise ValueError("Unsupported Output transform")
  return y

def to_one_hot(y):
  """Transforms label vector into one-hot encoding.

  Turns y into vector of shape [n_samples, 2] (assuming binary labels).

  y: np.ndarray
    A vector of shape [n_samples, 1]
  """
  n_samples = np.shape(y)[0]
  y_hot = np.zeros((n_samples, 2))
  for index, val in enumerate(y):
    if val == 0:
      y_hot[index] = np.array([1, 0])
    elif val == 1:
      y_hot[index] = np.array([0, 1])
  return y_hot

def balance_positives(y, W):
  """Ensure that positive and negative examples have equal weight."""
  n_samples, n_targets = np.shape(y)
  for target_ind in range(n_targets):
    positive_inds, negative_inds = [], []
    to_next_target = False
    for sample_ind in range(n_samples):
      label = y[sample_ind, target_ind]
      if label == 1:
        positive_inds.append(sample_ind)
      elif label == 0:
        negative_inds.append(sample_ind)
      elif label == -1:  # Case of missing label
        continue
      else:
        warnings.warn("Labels must be 0/1 or -1 " +
                      "(missing data) for balance_positives target %d. " % target_ind +
                      "Continuing without balancing.")
        to_next_target = True
        break 
    if to_next_target:
      continue
    n_positives, n_negatives = len(positive_inds), len(negative_inds)
    print "For target %d, n_positives: %d, n_negatives: %d" % (
        target_ind, n_positives, n_negatives)
    # TODO(rbharath): This results since the coarse train/test split doesn't
    # guarantee that the test set actually has any positives for targets. FIX
    # THIS BEFORE RELEASE!
    if n_positives == 0:
      pos_weight = 0
    else:
      pos_weight = float(n_negatives)/float(n_positives)
    W[positive_inds, target_ind] = pos_weight
    W[negative_inds, target_ind] = 1
  return W

def tensor_dataset_to_numpy(dataset, feature_endpoint="fingerprint",
    labels_endpoint="labels"):
  """Transforms a set of tensor data into numpy arrays (X, y)"""
  n_samples = len(dataset.keys())
  sample_datapoint = dataset.itervalues().next()
  feature_shape = np.shape(sample_datapoint[feature_endpoint])
  n_targets = 1 # TODO(rbharath): Generalize this later
  X = np.zeros((n_samples,) + feature_shape)
  y = np.zeros((n_samples, n_targets))
  W = np.ones((n_samples, n_targets))
  sorted_ids = sorted(dataset.keys())
  for index, smiles in enumerate(dataset.keys()):
    datapoint = dataset[smiles]
    fingerprint, labels = (datapoint[feature_endpoint],
      datapoint[labels_endpoint])
    X[index] = fingerprint
    # TODO(rbharath): The label is a dict for some reason?!? Figure this out
    # and fix it.
    y[index] = labels["3d_core_pdbbind"]
  return (X, y, W)

def dataset_to_numpy(dataset, feature_endpoint="fingerprint",
    labels_endpoint="labels", weight_positives=True):
  """Transforms a loaded dataset into numpy arrays (X, y).

  Transforms provided dict into feature matrix X (of dimensions [n_samples,
  n_features]) and label matrix y (of dimensions [n_samples,
  n_targets+n_desc]), where n_targets is the number of assays in the
  provided datset and n_desc is the number of computed descriptors we'd
  like to predict.

  Note that this function transforms missing data into negative examples
  (this is relatively safe since the ratio of positive to negative examples
  is on the order 1/100)

  Parameters
  ----------
  dataset: dict 
    A dictionary of type produced by load_datasets. 
  """
  n_samples = len(dataset.keys())
  sample_datapoint = dataset.itervalues().next()
  n_features = len(sample_datapoint[feature_endpoint])
  n_targets = len(sample_datapoint[labels_endpoint])
  X = np.zeros((n_samples, n_features))
  y = np.zeros((n_samples, n_targets))
  W = np.ones((n_samples, n_targets))
  sorted_smiles = sorted(dataset.keys())
  for index, smiles in enumerate(sorted_smiles):
    datapoint = dataset[smiles] 
    fingerprint, labels  = (datapoint[feature_endpoint],
        datapoint[labels_endpoint])
    X[index] = np.array(fingerprint)
    sorted_targets = sorted(labels.keys())
    # Set labels from measurements
    for t_ind, target in enumerate(sorted_targets):
      if labels[target] == -1:
        y[index][t_ind] = -1
        W[index][t_ind] = 0
      else:
        y[index][t_ind] = labels[target]
  if weight_positives:
    W = balance_positives(y, W)
  return X, y, W

def multitask_to_singletask(dataset):
  """Transforms a multitask dataset to a singletask dataset.

  Returns a dictionary which maps target names to datasets, where each
  dataset is itself a dict that maps identifiers to
  (fingerprint, scaffold, dict) tuples.

  Parameters
  ----------
  dataset: dict
    Dictionary of type produced by load_datasets
  """
  # Generate single-task data structures
  labels = dataset.itervalues().next()["labels"]
  sorted_targets = sorted(labels.keys())
  singletask = {target: {} for target in sorted_targets}
  # Populate the singletask datastructures
  sorted_smiles = sorted(dataset.keys())
  for index, smiles in enumerate(sorted_smiles):
    datapoint = dataset[smiles]
    labels = datapoint["labels"]
    for t_ind, target in enumerate(sorted_targets):
      if labels[target] == -1:
        continue
      else:
        datapoint_copy = datapoint.copy()
        datapoint_copy["labels"] = {target: labels[target]}
        singletask[target][smiles] = datapoint_copy 
  return singletask

def split_dataset(dataset, splittype):
  """Split provided data using specified method."""
  if splittype == "random":
    train, test = train_test_random_split(dataset, seed=seed)
  elif splittype == "scaffold":
    train, test = train_test_scaffold_split(dataset)
  elif splittype == "specified":
    train, test = train_test_specified_split(dataset)
  else:
    raise ValueError("Improper splittype.")
  return train, test

def train_test_specified_split(dataset):
  """Split provided data due to splits in origin data."""
  train, test = {}, {}
  for smiles, datapoint in dataset.iteritems():
    if "split" not in datapoint:
      raise ValueError("Missing required split information.")
    if datapoint["split"].lower() == "train" or datapoint["split"].lower() == "valid":
      train[smiles] = datapoint
    # TODO(rbharath): Add support for validation sets.
    elif datapoint["split"].lower() == "test":
      test[smiles] = datapoint
    else:
      raise ValueError("Improper split specified.")
  return train, test

def train_test_random_split(dataset, frac_train=.8, seed=None):
  """Splits provided data into train/test splits randomly.

  Performs a random 80/20 split of the data into train/test. Returns two
  dictionaries

  Parameters
  ----------
  dataset: dict 
    A dictionary of type produced by load_datasets. 
  frac_train: float
    Proportion of data in train set.
  seed: int (optional)
    Seed to initialize np.random.
  """
  np.random.seed(seed)
  shuffled = np.random.permutation(dataset.keys())
  train_cutoff = np.floor(frac_train * len(shuffled))
  train_keys, test_keys = shuffled[:train_cutoff], shuffled[train_cutoff:]
  train, test = {}, {}
  for key in train_keys:
    train[key] = dataset[key]
  for key in test_keys:
    test[key] = dataset[key]
  return train, test

def train_test_scaffold_split(dataset, frac_train=.8):
  """Splits provided data into train/test splits by scaffold.

  Groups the largest scaffolds into the train set until the size of the
  train set equals frac_train * len(dataset). Adds remaining scaffolds
  to test set. The idea is that the test set contains outlier scaffolds,
  and thus serves as a hard test of generalization capability for the
  model.

  Parameters
  ----------
  dataset: dict 
    A dictionary of type produced by load_datasets. 
  frac_train: float
    The fraction (between 0 and 1) of the data to use for train set.
  """
  scaffolds = scaffold_separate(dataset)
  train_size = frac_train * len(dataset)
  train, test= {}, {}
  for scaffold, elements in scaffolds:
    # If adding this scaffold makes the train_set too big, add to test set.
    if len(train) + len(elements) > train_size:
      for elt in elements:
        test[elt] = dataset[elt]
    else:
      for elt in elements:
        train[elt] = dataset[elt]
  return train, test

def scaffold_separate(dataset):
  """Splits provided data by compound scaffolds.

  Returns a list of pairs (scaffold, [identifiers]), where each pair
  contains a scaffold and a list of all identifiers for compounds that
  share that scaffold. The list will be sorted in decreasing order of
  number of compounds.

  Parameters
  ----------
  dataset: dict 
    A dictionary of type produced by load_datasets. 
  """
  scaffolds = {}
  for smiles in dataset:
    datapoint = dataset[smiles]
    scaffold = datapoint["scaffold"]
    if scaffold not in scaffolds:
      scaffolds[scaffold] = [smiles]
    else:
      scaffolds[scaffold].append(smiles)
  # Sort from largest to smallest scaffold sets 
  return sorted(scaffolds.items(), key=lambda x: -len(x[1]))

def labels_to_weights(ytrue):
  """Uses the true labels to compute and output sample weights.

  Parameters
  ----------
  ytrue: list or np.ndarray
    True labels.
  """
  n_total = np.shape(ytrue)[0]
  n_positives = np.sum(ytrue)
  n_negatives = n_total - n_positives
  pos_weight = np.floor(n_negatives/n_positives)

  sample_weights = np.zeros(np.shape(ytrue)[0])
  for ind, entry in enumerate(ytrue):
    if entry == 0:  # negative
      sample_weights[ind] = 1
    elif entry == 1:  # positive
      sample_weights[ind] = pos_weight
    else:
      raise ValueError("ytrue can only contain 0s or 1s.")
  return sample_weights
