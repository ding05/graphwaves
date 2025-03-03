from losses import *

import numpy as np
from numpy import asarray, save, load
import math

import xarray as xr

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch.utils.data.sampler import SequentialSampler
from torch.autograd import Variable

import time

from sklearn.metrics import mean_squared_error, confusion_matrix, classification_report

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.transforms as mtransforms

# FCN configurations

for lead_time in [1]:

    net_class = 'EnsFCN' #
    num_layer = 2 #
    num_hid_feat = 50 #
    num_out_feat = 1 #
    window_size = 5
    train_split = 0.8
    lead_time = lead_time
    noise_var = 0.01
    #loss_function = 'BMSE' + str(noise_var) # 'MSE', 'MAE', 'Huber', 'WMSE', 'WMAE', 'WHuber', 'WFMSE', 'WFMAE', 'BMSE
    weight = 200
    loss_function = 'CmMAE' + str(weight) + '&MAE'
    #loss_function = 'MAE'
    negative_slope = 0.1
    activation = 'lrelu' + str(negative_slope) # 'relu', 'tanh', 'sigm'
    alpha = 0.9
    optimizer = 'RMSP' + str(alpha) # SGD, Adam
    learning_rate = 0.005 # 0.05, 0.02, 0.01
    momentum = 0.9
    weight_decay = 0.01
    dropout = 'nd'
    batch_size = 512 # >= 120 crashed for original size, >= 550 crashed for half size, >= 480 crashed for half size and two variables
    num_sample = 1680-window_size-lead_time+1 # max: node_features.shape[1]-window_size-lead_time+1
    num_train_epoch = 200
    
    data_path = 'data/'
    models_path = 'out/'
    out_path = 'out/'
    
    # Load the input.
    
    loc_name = 'BoP'
    
    x = load(data_path + 'y.npy')
    x1 = load(data_path + 'y_eastaus.npy')
    y = load(data_path + 'y.npy')
    
    x = x.squeeze(axis=1)
    x1 = x1.squeeze(axis=1)
    y = y.squeeze(axis=1)
    y_all = y
    num_var = 1
    
    dataset = []
    
    for i in range(len(y)-window_size-lead_time):
      dataset.append([torch.tensor(x[i:i+window_size]), torch.tensor(y[i+window_size+lead_time-1])])
      #dataset.append([torch.tensor(np.concatenate((x[i:i+window_size], x1[i:i+window_size]))), torch.tensor(y[i+window_size+lead_time-1])])
    
    print('--------------------')
    print()
    
    num_examples = len(dataset)
    num_train = int(num_examples * train_split)
    
    train_sampler = SequentialSampler(torch.arange(num_train))
    test_sampler = SequentialSampler(torch.arange(num_train, num_examples))
    
    train_dataloader = DataLoader(dataset, sampler=torch.arange(num_train), batch_size=batch_size, drop_last=False)
    test_dataloader = DataLoader(dataset, sampler=torch.arange(num_train, num_examples), batch_size=1, drop_last=False)
    
    # Set up a FCN.
    
    class FCN_a(nn.Module):
        def __init__(self):
          super(FCN_a, self).__init__()
          self.fc1 = nn.Linear(window_size * num_var, num_hid_feat)
          self.fc2 = nn.Linear(num_hid_feat, 1)
          self.double()
        
        def forward(self, x):
          x = self.fc1(x)
          x = F.leaky_relu(x, negative_slope)
          x = self.fc2(x)
          x = F.leaky_relu(x, negative_slope)
          return x
    
    class FCN_n(nn.Module):
        def __init__(self):
          super(FCN_n, self).__init__()
          self.fc1 = nn.Linear(window_size * num_var, num_hid_feat)
          self.fc2 = nn.Linear(num_hid_feat, 1)
          self.double()
        
        def forward(self, x):
          x = self.fc1(x)
          x = F.leaky_relu(x, negative_slope)
          x = self.fc2(x)
          x = F.leaky_relu(x, negative_slope)
          return x
    
    model_a = FCN_a()
    model_n = FCN_n()
    optim_a = torch.optim.RMSprop(model_a.parameters(), lr=learning_rate, alpha=alpha, weight_decay=weight_decay, momentum=momentum)
    optim_n = torch.optim.RMSprop(model_n.parameters(), lr=learning_rate, alpha=alpha, weight_decay=weight_decay, momentum=momentum)
    
    # Train the models.
    
    # Start time
    start = time.time()
    
    all_loss_a = []
    all_eval_a = []
    
    for epoch in range(num_train_epoch):
        print('Epoch ' + str(epoch))
        print()
        
        losses = []
        
        # The threshold for defining outliers using the 90th percentile
        y_train = y_all[:int(len(y_all)*0.8)]
        y_train_sorted = np.sort(y_train)
        threshold = y_train_sorted[int(len(y_train_sorted)*0.9):][0]
        
        for x, y in train_dataloader:
            pred = torch.squeeze(model_a(x))
            loss = cm_weighted_mae(pred, y, threshold=threshold, weight=weight)
            optim_a.zero_grad()
            loss.backward()
            optim_a.step()
            losses.append(loss.cpu().detach().numpy())
        print()
        print('Training loss:', sum(losses) / len(losses))
        print()
        all_loss_a.append(sum(losses) / len(losses))
        
        preds = []
        ys = []
        for x, y in test_dataloader:
            pred = torch.squeeze(model_a(x))
            preds.append(pred.cpu().detach().numpy())
            ys.append(y.cpu().detach().numpy())
        val_mse = mean_squared_error(np.array(ys), np.array(preds), squared=True)
        print('Test MSE:', val_mse)
        print()
        all_eval_a.append(val_mse)
    
        print('----------')
        print()

    all_loss_n = []
    all_eval_n = []
    
    for epoch in range(num_train_epoch):
        print('Epoch ' + str(epoch))
        print()
        
        losses = []
        
        for x, y in train_dataloader:
            pred = torch.squeeze(model_n(x))
            loss_func = nn.L1Loss()
            loss = loss_func(pred, y)
            optim_n.zero_grad()
            loss.backward()
            optim_n.step()
            losses.append(loss.cpu().detach().numpy())
        print()
        print('Training loss:', sum(losses) / len(losses))
        print()
        all_loss_n.append(sum(losses) / len(losses))
        
        preds = []
        ys = []
        for x, y in test_dataloader:
            pred = torch.squeeze(model_n(x))
            preds.append(pred.cpu().detach().numpy())
            ys.append(y.cpu().detach().numpy())
        val_mse = mean_squared_error(np.array(ys), np.array(preds), squared=True)
        print('Test MSE:', val_mse)
        print()
        all_eval_n.append(val_mse)
    
        print('----------')
        print()
    
    # End time
    stop = time.time()
    
    # Test the models.
    
    preds_a = []
    ys = []
    for x, y in test_dataloader:
        pred = torch.squeeze(model_a(x))
        preds_a.append(pred.cpu().detach().numpy())
        ys.append(y.cpu().detach().numpy())
    
    preds_n = []
    for x, y in test_dataloader:
        pred = torch.squeeze(model_n(x))
        preds_n.append(pred.cpu().detach().numpy())
    
    preds = []
    for i in range(len(ys)):
        if ys[i] >= threshold:
            preds.append(preds_a[i])
        else:
            preds.append(preds_n[i])

    test_mse = mean_squared_error(np.array(ys), np.array(preds), squared=True)
    test_rmse = mean_squared_error(np.array(ys), np.array(preds), squared=False)    

    print('----------')
    print()
    
    print('Final test MSE:', test_mse)
    print('----------')
    print()
    
    # Show the results.
    
    # Increase the fontsize.
    plt.rcParams.update({'font.size': 20})
    
    # Calculate the threshold for 90th percentile and mark the outliers.
    y_train = y_all[:int(len(y_all)*0.8)]
    y_train_sorted = np.sort(y_train)
    threshold = y_train_sorted[int(len(y_train_sorted)*0.9):][0]
    threshold_weak = y_train_sorted[int(len(y_train_sorted)*0.8):][0] # The weak threshold for 80th percentile
    y_outliers = []
    pred_outliers = []
    for i in range(len(ys)):
      if ys[i] >= threshold:
        y_outliers.append(ys[i])
        pred_outliers.append(preds[i])
      else:
        y_outliers.append(None)
        pred_outliers.append(None)
    
    # Calculate the outlier MSE; remove the NAs.
    temp_y_outliers = [i for i in y_outliers if i is not None]
    temp_pred_outliers = [i for i in pred_outliers if i is not None]
    ol_test_mse = mean_squared_error(np.array(temp_y_outliers), np.array(temp_pred_outliers), squared=True)
    
    fig, ax = plt.subplots(figsize=(12, 8))
    plt.xlabel('Month')
    plt.ylabel('SST Residual')
    plt.title('MSE: ' + str(round(test_mse, 4)) + ', MSE above 90th: ' + str(round(ol_test_mse, 4)))
    patch_a = mpatches.Patch(color='pink', label='Obs')
    patch_b = mpatches.Patch(color='red', label='Obs above 90th')
    patch_c = mpatches.Patch(color='skyblue', label='Pred')
    patch_d = mpatches.Patch(color='blue', label='Pred for Obs above 90th')
    ax.legend(handles=[patch_a, patch_b, patch_c, patch_d])
    month = np.arange(0, len(ys), 1, dtype=int)
    plt.plot(month, np.array(ys, dtype=object), linestyle='-', color='pink')
    ax.plot(month, np.array(ys, dtype=object), 'o', color='pink')
    ax.plot(month, np.array(y_outliers, dtype=object), 'o', color='red')
    plt.plot(month, np.array(preds, dtype=object), linestyle='-', color='skyblue')
    ax.plot(month, np.array(preds, dtype=object), 'o', color='skyblue')
    ax.plot(month, np.array(pred_outliers, dtype=object), 'o', color='blue')
    plt.savefig(out_path + 'pred_a_SSTASODA' + loc_name + '_' + str(net_class) + '_' + str(num_hid_feat) + '_' + str(num_out_feat) + '_' + str(window_size) + '_' + str(lead_time) + '_' + str(num_sample) + '_' + str(train_split) + '_' + str(loss_function) + '_' + str(optimizer) + '_' + str(activation) + '_' + str(learning_rate) + '_' + str(momentum) + '_' + str(weight_decay) + '_' + str(dropout) + '_' + str(batch_size) + '_' + str(num_train_epoch) + '.png')
    
    fig, ax = plt.subplots(figsize=(12, 8))
    lim = max(np.abs(np.array(preds)).max(), np.abs(np.array(ys)).max())
    ax.set_xlim([-lim-0.1, lim+0.1])
    ax.set_ylim([-lim-0.1, lim+0.1])
    plt.xlabel('Obs SST Residual')
    plt.ylabel('Pred SST Residual')
    plt.title('MSE: ' + str(round(test_mse, 4)) + ', MSE above 90th: ' + str(round(ol_test_mse, 4)))
    ax.plot(np.array(ys, dtype=object), np.array(preds, dtype=object), 'o', color='black')
    transform = ax.transAxes
    line_a = mlines.Line2D([0, 1], [0, 1], color='red')
    line_a.set_transform(transform)
    ax.add_line(line_a)
    patch_a = mpatches.Patch(color='pink', label='Obs above 90th')
    ax.legend(handles=[patch_a])
    ax.axvspan(threshold, max(ys)+0.1, color='pink')
    plt.savefig(out_path + 'pred_b_SSTASODA' + loc_name + '_' + str(net_class) + '_' + str(num_hid_feat) + '_' + str(num_out_feat) + '_' + str(window_size) + '_' + str(lead_time) + '_' + str(num_sample) + '_' + str(train_split) + '_' + str(loss_function) + '_' + str(optimizer) + '_' + str(activation) + '_' + str(learning_rate) + '_' + str(momentum) + '_' + str(weight_decay) + '_' + str(dropout) + '_' + str(batch_size) + '_' + str(num_train_epoch) + '.png')
        
    print('Save the observed vs. predicted plots.')
    print('----------')
    print()

    # Confusion matrix

    ys_masked = ['MHW Weak Indicator (>80th)' if ys[i] >= threshold_weak else 'None' for i in range(len(ys))]
    ys_masked = ['MHW Strong Indicator (>90th)' if ys[i] >= threshold else ys_masked[i] for i in range(len(ys_masked))]
    preds_masked = ['MHW Weak Indicator (>80th)' if preds[i] >= threshold_weak else 'None' for i in range(len(preds))]
    preds_masked = ['MHW Strong Indicator (>90th)' if preds[i] >= threshold else preds_masked[i] for i in range(len(preds_masked))]
    
    classification_results = classification_report(ys_masked, preds_masked, digits=4)

    with open(out_path + 'classification_SSTASODA' + loc_name + '_' + str(net_class) + '_' + str(num_hid_feat) + '_' + str(num_out_feat) + '_' + str(window_size) + '_' + str(lead_time) + '_' + str(num_sample) + '_' + str(train_split) + '_' + str(loss_function) + '_' + str(optimizer) + '_' + str(activation) + '_' + str(learning_rate) + '_' + str(momentum) + '_' + str(weight_decay) + '_' + str(dropout) + '_' + str(batch_size) + '_' + str(num_train_epoch) + '.txt', 'w') as f:
        print(classification_results, file=f)
    
    print('Save the classification results in a TXT file.')
    print('----------')
    print()