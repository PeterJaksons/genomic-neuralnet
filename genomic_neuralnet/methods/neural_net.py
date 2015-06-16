import numpy as np

from genomic_neuralnet.config import MAX_EPOCHS, CONTINUE_EPOCHS, TRY_CONVERGENCE, USE_ARAC
from pybrain.structure import FeedForwardNetwork, LinearLayer, SigmoidLayer, FullConnection
from pybrain.supervised.trainers import BackpropTrainer
from pybrain.datasets import SupervisedDataSet, SupervisedDataSet, UnsupervisedDataSet
from pybrain.tools.shortcuts import buildNetwork

def _get_nn(inputs, hidden):
    """
    Construct a neural network.
    """
    # One output layer (1,).
    layers = (inputs,) + hidden + (1,)
    n = buildNetwork(*layers, hiddenclass=SigmoidLayer, fast=USE_ARAC)
    return n

def _train_nn(neuralnet, training_set, weight_decay):
    """
    A stateful method that trains the network
    on a dataset.
    """
    trainer = BackpropTrainer(neuralnet, training_set, weightdecay=weight_decay, momentum=0.5)
    if TRY_CONVERGENCE: # Try to converge to an optimal solution.
        trainer.trainUntilConvergence(maxEpochs=MAX_EPOCHS, continueEpochs=CONTINUE_EPOCHS, validationProportion=0.25)
    else: # Train a specific number of epochs and then stop.
        trainer.trainEpochs(epochs=MAX_EPOCHS)

def get_nn_prediction(train_data, train_truth, test_data, test_truth, hidden=(5,), weight_decay=0.0): 
    mean = np.mean(train_truth)
    sd = np.std(train_truth)

    # Supervised training dataset.
    ds = SupervisedDataSet(len(train_data.columns), 1)
    ds.setField('input', train_data) 
    ds.setField('target', train_truth[:, np.newaxis])
    net = _get_nn(len(train_data.columns), hidden)

    _train_nn(net, ds, weight_decay)

    # Unsupervised (test) dataset.
    test_ds = UnsupervisedDataSet(len(train_data.columns))
    test_ds.setField('sample', test_data)

    predicted = net.activateOnDataset(test_ds) * sd + mean
    return predicted.ravel()
