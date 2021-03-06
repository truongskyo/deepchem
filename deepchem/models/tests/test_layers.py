import deepchem as dc
import numpy as np
import tensorflow as tf
import deepchem.models.layers as layers
from tensorflow.python.framework import test_util


class TestLayers(test_util.TensorFlowTestCase):

  def test_highway(self):
    """Test invoking Highway."""
    width = 5
    batch_size = 10
    input = np.random.rand(batch_size, width).astype(np.float32)
    layer = layers.Highway()
    result = layer(input)
    assert result.shape == (batch_size, width)
    assert len(layer.trainable_variables) == 4

    # Creating a second layer should produce different results, since it has
    # different random weights.

    layer2 = layers.Highway()
    result2 = layer2(input)
    assert not np.allclose(result, result2)

    # But evaluating the first layer again should produce the same result as before.

    result3 = layer(input)
    assert np.allclose(result, result3)

  def test_combine_mean_std(self):
    """Test invoking CombineMeanStd."""
    mean = np.random.rand(5, 3).astype(np.float32)
    std = np.random.rand(5, 3).astype(np.float32)
    layer = layers.CombineMeanStd(training_only=True, noise_epsilon=0.01)
    result1 = layer([mean, std], training=False)
    assert np.array_equal(result1, mean)  # No noise in test mode
    result2 = layer([mean, std], training=True)
    assert not np.array_equal(result2, mean)
    assert np.allclose(result2, mean, atol=0.1)

  def test_stack(self):
    """Test invoking Stack."""
    input1 = np.random.rand(5, 4).astype(np.float32)
    input2 = np.random.rand(5, 4).astype(np.float32)
    result = layers.Stack()([input1, input2])
    assert result.shape == (5, 2, 4)
    assert np.array_equal(input1, result[:, 0, :])
    assert np.array_equal(input2, result[:, 1, :])

  def test_variable(self):
    """Test invoking Variable."""
    value = np.random.rand(5, 4).astype(np.float32)
    layer = layers.Variable(value)
    layer.build([])
    result = layer.call([]).numpy()
    assert np.allclose(result, value)
    assert len(layer.trainable_variables) == 1

  def test_interatomic_l2_distances(self):
    """Test invoking InteratomicL2Distances."""
    atoms = 5
    neighbors = 2
    coords = np.random.rand(atoms, 3)
    neighbor_list = np.random.randint(0, atoms, size=(atoms, neighbors))
    layer = layers.InteratomicL2Distances(atoms, neighbors, 3)
    result = layer([coords, neighbor_list])
    assert result.shape == (atoms, neighbors)
    for atom in range(atoms):
      for neighbor in range(neighbors):
        delta = coords[atom] - coords[neighbor_list[atom, neighbor]]
        dist2 = np.dot(delta, delta)
        assert np.allclose(dist2, result[atom, neighbor])

  def test_graph_conv(self):
    """Test invoking GraphConv."""
    out_channels = 2
    n_atoms = 4  # In CCC and C, there are 4 atoms
    raw_smiles = ['CCC', 'C']
    import rdkit
    mols = [rdkit.Chem.MolFromSmiles(s) for s in raw_smiles]
    featurizer = dc.feat.graph_features.ConvMolFeaturizer()
    mols = featurizer.featurize(mols)
    multi_mol = dc.feat.mol_graphs.ConvMol.agglomerate_mols(mols)
    atom_features = multi_mol.get_atom_features().astype(np.float32)
    degree_slice = multi_mol.deg_slice
    membership = multi_mol.membership
    deg_adjs = multi_mol.get_deg_adjacency_lists()[1:]
    args = [atom_features, degree_slice, membership] + deg_adjs
    layer = layers.GraphConv(out_channels)
    result = layer(args)
    assert result.shape == (n_atoms, out_channels)
    num_deg = 2 * layer.max_degree + (1 - layer.min_degree)
    assert len(layer.trainable_variables) == 2 * num_deg

  def test_graph_pool(self):
    """Test invoking GraphPool."""
    n_atoms = 4  # In CCC and C, there are 4 atoms
    raw_smiles = ['CCC', 'C']
    import rdkit
    mols = [rdkit.Chem.MolFromSmiles(s) for s in raw_smiles]
    featurizer = dc.feat.graph_features.ConvMolFeaturizer()
    mols = featurizer.featurize(mols)
    multi_mol = dc.feat.mol_graphs.ConvMol.agglomerate_mols(mols)
    atom_features = multi_mol.get_atom_features().astype(np.float32)
    degree_slice = multi_mol.deg_slice
    membership = multi_mol.membership
    deg_adjs = multi_mol.get_deg_adjacency_lists()[1:]
    args = [atom_features, degree_slice, membership] + deg_adjs
    result = layers.GraphPool()(args)
    assert result.shape[0] == n_atoms
    # TODO What should shape[1] be?  It's not documented.

  def test_graph_gather(self):
    """Test invoking GraphGather."""
    batch_size = 2
    n_features = 75
    n_atoms = 4  # In CCC and C, there are 4 atoms
    raw_smiles = ['CCC', 'C']
    import rdkit
    mols = [rdkit.Chem.MolFromSmiles(s) for s in raw_smiles]
    featurizer = dc.feat.graph_features.ConvMolFeaturizer()
    mols = featurizer.featurize(mols)
    multi_mol = dc.feat.mol_graphs.ConvMol.agglomerate_mols(mols)
    atom_features = multi_mol.get_atom_features().astype(np.float32)
    degree_slice = multi_mol.deg_slice
    membership = multi_mol.membership
    deg_adjs = multi_mol.get_deg_adjacency_lists()[1:]
    args = [atom_features, degree_slice, membership] + deg_adjs
    result = layers.GraphGather(batch_size)(args)
    # TODO(rbharath): Why is it 2*n_features instead of n_features?
    assert result.shape == (batch_size, 2 * n_features)

  def test_lstm_step(self):
    """Test invoking LSTMStep."""
    max_depth = 5
    n_test = 5
    n_feat = 10
    y = np.random.rand(n_test, 2 * n_feat).astype(np.float32)
    state_zero = np.random.rand(n_test, n_feat).astype(np.float32)
    state_one = np.random.rand(n_test, n_feat).astype(np.float32)
    layer = layers.LSTMStep(n_feat, 2 * n_feat)
    result = layer([y, state_zero, state_one])
    h_out, h_copy_out, c_out = (result[0], result[1][0], result[1][1])
    assert h_out.shape == (n_test, n_feat)
    assert h_copy_out.shape == (n_test, n_feat)
    assert c_out.shape == (n_test, n_feat)
    assert len(layer.trainable_variables) == 1

  def test_attn_lstm_embedding(self):
    """Test invoking AttnLSTMEmbedding."""
    max_depth = 5
    n_test = 5
    n_support = 11
    n_feat = 10
    test = np.random.rand(n_test, n_feat).astype(np.float32)
    support = np.random.rand(n_support, n_feat).astype(np.float32)
    layer = layers.AttnLSTMEmbedding(n_test, n_support, n_feat, max_depth)
    test_out, support_out = layer([test, support])
    assert test_out.shape == (n_test, n_feat)
    assert support_out.shape == (n_support, n_feat)
    assert len(layer.trainable_variables) == 4

  def test_iter_ref_lstm_embedding(self):
    """Test invoking IterRefLSTMEmbedding."""
    max_depth = 5
    n_test = 5
    n_support = 11
    n_feat = 10
    test = np.random.rand(n_test, n_feat).astype(np.float32)
    support = np.random.rand(n_support, n_feat).astype(np.float32)
    layer = layers.IterRefLSTMEmbedding(n_test, n_support, n_feat, max_depth)
    test_out, support_out = layer([test, support])
    assert test_out.shape == (n_test, n_feat)
    assert support_out.shape == (n_support, n_feat)
    assert len(layer.trainable_variables) == 8

  def test_vina_free_energy(self):
    """Test invoking VinaFreeEnergy."""
    n_atoms = 5
    m_nbrs = 1
    ndim = 3
    nbr_cutoff = 1
    start = 0
    stop = 4
    X = np.random.rand(n_atoms, ndim).astype(np.float32)
    Z = np.random.randint(0, 2, (n_atoms)).astype(np.float32)
    layer = layers.VinaFreeEnergy(n_atoms, m_nbrs, ndim, nbr_cutoff, start,
                                  stop)
    result = layer([X, Z])
    assert len(layer.trainable_variables) == 6
    assert result.shape == tuple()

    # Creating a second layer should produce different results, since it has
    # different random weights.

    layer2 = layers.VinaFreeEnergy(n_atoms, m_nbrs, ndim, nbr_cutoff, start,
                                   stop)
    result2 = layer2([X, Z])
    assert not np.allclose(result, result2)

    # But evaluating the first layer again should produce the same result as before.

    result3 = layer([X, Z])
    assert np.allclose(result, result3)

  def test_weighted_linear_combo(self):
    """Test invoking WeightedLinearCombo."""
    input1 = np.random.rand(5, 10).astype(np.float32)
    input2 = np.random.rand(5, 10).astype(np.float32)
    layer = layers.WeightedLinearCombo()
    result = layer([input1, input2])
    assert len(layer.trainable_variables) == 2
    expected = input1 * layer.trainable_variables[0] + input2 * layer.trainable_variables[1]
    assert np.allclose(result, expected)

  def test_neighbor_list(self):
    """Test invoking NeighborList."""
    N_atoms = 5
    start = 0
    stop = 12
    nbr_cutoff = 3
    ndim = 3
    M_nbrs = 2
    coords = start + np.random.rand(N_atoms, ndim) * (stop - start)
    coords = tf.cast(tf.stack(coords), tf.float32)
    layer = layers.NeighborList(N_atoms, M_nbrs, ndim, nbr_cutoff, start, stop)
    result = layer(coords)
    assert result.shape == (N_atoms, M_nbrs)

  def test_atomic_convolution(self):
    """Test invoking AtomicConvolution."""
    batch_size = 4
    max_atoms = 5
    max_neighbors = 2
    dimensions = 3
    params = [[5.0, 2.0, 0.5], [10.0, 2.0, 0.5]]
    input1 = np.random.rand(batch_size, max_atoms,
                            dimensions).astype(np.float32)
    input2 = np.random.randint(
        max_atoms, size=(batch_size, max_atoms, max_neighbors))
    input3 = np.random.randint(
        1, 10, size=(batch_size, max_atoms, max_neighbors))
    layer = layers.AtomicConvolution(radial_params=params)
    result = layer([input1, input2, input3])
    assert result.shape == (batch_size, max_atoms, len(params))
    assert len(layer.trainable_variables) == 3

  def test_alpha_share_layer(self):
    """Test invoking AlphaShareLayer."""
    batch_size = 10
    length = 6
    input1 = np.random.rand(batch_size, length).astype(np.float32)
    input2 = np.random.rand(batch_size, length).astype(np.float32)
    layer = layers.AlphaShareLayer()
    result = layer([input1, input2])
    assert input1.shape == result[0].shape
    assert input2.shape == result[1].shape

    # Creating a second layer should produce different results, since it has
    # different random weights.

    layer2 = layers.AlphaShareLayer()
    result2 = layer2([input1, input2])
    assert not np.allclose(result[0], result2[0])
    assert not np.allclose(result[1], result2[1])

    # But evaluating the first layer again should produce the same result as before.

    result3 = layer([input1, input2])
    assert np.allclose(result[0], result3[0])
    assert np.allclose(result[1], result3[1])

  def test_sluice_loss(self):
    """Test invoking SluiceLoss."""
    input1 = np.ones((3, 4)).astype(np.float32)
    input2 = np.ones((2, 2)).astype(np.float32)
    result = layers.SluiceLoss()([input1, input2])
    assert np.allclose(result, 40.0)

  def test_beta_share(self):
    """Test invoking BetaShare."""
    batch_size = 10
    length = 6
    input1 = np.random.rand(batch_size, length).astype(np.float32)
    input2 = np.random.rand(batch_size, length).astype(np.float32)
    layer = layers.BetaShare()
    result = layer([input1, input2])
    assert input1.shape == result.shape
    assert input2.shape == result.shape

    # Creating a second layer should produce different results, since it has
    # different random weights.

    layer2 = layers.BetaShare()
    result2 = layer2([input1, input2])
    assert not np.allclose(result, result2)

    # But evaluating the first layer again should produce the same result as before.

    result3 = layer([input1, input2])
    assert np.allclose(result, result3)

  def test_ani_feat(self):
    """Test invoking ANIFeat."""
    batch_size = 10
    max_atoms = 5
    input = np.random.rand(batch_size, max_atoms, 4).astype(np.float32)
    layer = layers.ANIFeat(max_atoms=max_atoms)
    result = layer(input)
    # TODO What should the output shape be?  It's not documented, and there
    # are no other test cases for it.

  def test_graph_embed_pool_layer(self):
    """Test invoking GraphEmbedPoolLayer."""
    V = np.random.uniform(size=(10, 100, 50)).astype(np.float32)
    adjs = np.random.uniform(size=(10, 100, 5, 100)).astype(np.float32)
    layer = layers.GraphEmbedPoolLayer(num_vertices=6)
    result = layer([V, adjs])
    assert result[0].shape == (10, 6, 50)
    assert result[1].shape == (10, 6, 5, 6)

    # Creating a second layer should produce different results, since it has
    # different random weights.

    layer2 = layers.GraphEmbedPoolLayer(num_vertices=6)
    result2 = layer2([V, adjs])
    assert not np.allclose(result[0], result2[0])
    assert not np.allclose(result[1], result2[1])

    # But evaluating the first layer again should produce the same result as before.

    result3 = layer([V, adjs])
    assert np.allclose(result[0], result3[0])
    assert np.allclose(result[1], result3[1])

  def test_graph_cnn(self):
    """Test invoking GraphCNN."""
    V = np.random.uniform(size=(10, 100, 50)).astype(np.float32)
    adjs = np.random.uniform(size=(10, 100, 5, 100)).astype(np.float32)
    layer = layers.GraphCNN(num_filters=6)
    result = layer([V, adjs])
    assert result.shape == (10, 100, 6)

    # Creating a second layer should produce different results, since it has
    # different random weights.

    layer2 = layers.GraphCNN(num_filters=6)
    result2 = layer2([V, adjs])
    assert not np.allclose(result, result2)

    # But evaluating the first layer again should produce the same result as before.

    result3 = layer([V, adjs])
    assert np.allclose(result, result3)
