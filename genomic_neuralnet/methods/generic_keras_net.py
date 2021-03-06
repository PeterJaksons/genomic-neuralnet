from __future__ import print_function

import os
import time
import json
import numpy as np

from keras.models import Sequential
from keras.layers import Dense, Dropout, Activation, Lambda
from keras.optimizers import Nadam as Trainer
#from keras.optimizers import Adam as Trainer
from keras.regularizers import WeightRegularizer
from keras.callbacks import EarlyStopping, Callback, LearningRateScheduler
from sklearn.preprocessing import MinMaxScaler 
from genomic_neuralnet.util import get_is_time_stats, get_should_plot

TIMING_EPOCHS = 12000

class LossHistory(Callback):
    def on_train_begin(self, logs={}):
        self.losses = []

    def on_epoch_end(self, epoch, logs={}):
        self.losses.append(logs.get('loss'))

class NeuralNetContainer(object):
    def __init__(self): 
        self.model = None
        self.learning_rate = None
        self.weight_decay = 0.0
        self.dropout_prob = 0.0
        self.epochs = 25
        self.hidden_layers = (10,)
        self.verbose = False
        self.plot = False

    def clone(self):
        if not self.model is None:
            raise NotImplemented('Cannot clone container after building model')
        clone = NeuralNetContainer()
        clone.learning_rate = self.learning_rate
        clone.weight_decay = self.weight_decay
        clone.dropout_prob = self.dropout_prob
        clone.epochs = self.epochs
        clone.hidden_layers = self.hidden_layers
        clone.verbose = self.verbose
        clone.plot = self.plot
        return clone

def _build_nn(net_container, n_features):
    model = Sequential() 

    # Change scale from (-1, 1) to (0, 1)
    model.add(Lambda(lambda x: (x + 1) / 2, input_shape=(n_features,), output_shape=(n_features,)))

    if net_container.weight_decay > 0.0:
        weight_regularizer = WeightRegularizer(net_container.weight_decay)
    else: 
        weight_regularizer = None 

    last_dim = n_features
    for lidx, n_nodes in enumerate(net_container.hidden_layers):
        # Layer, activation, and dropout, in that order.
        model.add(Dense(output_dim=n_nodes, input_dim=last_dim, W_regularizer=weight_regularizer))
        model.add(Activation('sigmoid'))
        if net_container.dropout_prob > 0.0:
            model.add(Dropout(net_container.dropout_prob))
        last_dim = n_nodes

    model.add(Dense(output_dim=1, input_dim=last_dim, bias=False))
    model.add(Activation('linear'))

    if not net_container.learning_rate is None:
        optimizer = Trainer(lr=net_container.learning_rate)
    else:
        #optimizer = Trainer(lr=0.0001)
        optimizer = Trainer()

    model.compile( optimizer=optimizer
                 , loss='mean_squared_error'
                 )

    net_container.model = model


def _train_net(container, X, y, override_epochs=None, is_check_train=False):
    """ 
    Given a container, X (inputs), and y (outputs) train the network in the container. 

    * If override_epochs is an integer, just run that many epochs.

    * The is_check_train parameter signifies that this training is a quick check to make 
      sure that the network is properly initialized and that the output error 
      is decreasing. The best "check trained" network will be passed in again
      for an additional full set of training epochs.
    """
    model = container.model
    epochs = override_epochs if (not override_epochs is None) else container.epochs
    verbose = int(container.verbose)

    def rate_func(epoch):
        if epochs - epoch == 2000:
            # Settle down during last 2000 epochs.
            model.optimizer.lr.set_value(model.optimizer.lr.get_value()/4.0)
        if epochs - epoch == 500:
            # Go a bit further in last 500 epochs.
            model.optimizer.lr.set_value(model.optimizer.lr.get_value()/4.0)
        return float(model.optimizer.lr.get_value())
     
    lr_scheduler = LearningRateScheduler(rate_func)
    loss_history = LossHistory()
    callbacks = [loss_history, lr_scheduler]

    model.fit( X, 
               y, 
               nb_epoch=epochs, 
               batch_size=X.shape[0] / 4,
               verbose=verbose, 
               callbacks=callbacks
             ) 

    if (isinstance(override_epochs, int)) and (not is_check_train) and container.plot:
        # Plot, but only if this is not overriden epochs.
        import matplotlib.pyplot as plt
        plt.plot(range(len(loss_history.losses)), loss_history.losses)
        plt.show()

    return loss_history.losses[-1] 

def _predict(container, X):
    model = container.model

    return model.predict(X)

_NET_TRIES = 2 

def _get_initial_net(container, n_features, X, y):
    """ 
    Create a few networks. Start the training process for a few epochs, then take
    the best one to continue training. This eliminates networks that are poorly
    initialized and will not converge.
    """
    candidates = []
    for _ in range(_NET_TRIES): 
        cont = container.clone()
        _build_nn(cont, n_features)
        candidates.append(cont)

    losses = []
    for candidate in candidates:
        # Train each candidate for 100 epochs.
        loss = _train_net(candidate, X, y, override_epochs=100, is_check_train=True)
        losses.append(loss)

    best_idx = np.argmin(losses)
    return candidates[best_idx]

def get_net_prediction( train_data, train_truth, test_data, test_truth
                      , hidden=(5,), weight_decay=0.0, dropout_prob=0.0
                      , learning_rate=None, epochs=25, verbose=False
                      , iter_id=None
                      ):

    container = NeuralNetContainer()
    container.learning_rate = learning_rate
    container.dropout_prob = dropout_prob
    container.weight_decay = weight_decay
    container.epochs = epochs
    container.hidden_layers = hidden
    container.verbose = verbose
    container.plot = get_should_plot()

    mms = MinMaxScaler(feature_range= (-1, 1)) # Scale output from -1 to 1.
    train_y = mms.fit_transform(train_truth[:,np.newaxis])

    n_features = train_data.shape[1]

    collect_time_stats = get_is_time_stats()
    if collect_time_stats: 
        start = time.time()

    # Find and return an effectively initialized network to start.
    container = _get_initial_net(container, n_features, train_data, train_y)

    # Train the network.
    if collect_time_stats:
        # Train a specific time, never terminating early.
        _train_net(container, train_data, train_y, override_epochs=TIMING_EPOCHS, is_check_train=False)
    else: 
        # Normal training, enable all heuristics.
        _train_net(container, train_data, train_y)

    if collect_time_stats: 
        end = time.time()
        print('Fitting took {} seconds'.format(end - start))
        print(json.dumps({'seconds': end - start, 'hidden': container.hidden_layers}))

    # Unsupervised (test) dataset.
    predicted = _predict(container, test_data)
    predicted = mms.inverse_transform(predicted)
    
    return predicted.ravel()

