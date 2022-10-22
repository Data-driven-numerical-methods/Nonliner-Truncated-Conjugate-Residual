# -*- coding: utf-8 -*-

from __future__ import division
from __future__ import print_function

import time
import argparse
import numpy as np
import pickle
import torch
import torch.nn.functional as F
import torch.optim as optim
import matplotlib.pyplot as plt
import torch.nn as nn

from utils import load_data, accuracy,download_data
from models import GCN




def FF(features, adj, labels):
    # reload(w)
    y_pred = model(features, adj)
    f = F.nll_loss(y_pred, labels)
    f.backward()
    vl = []
    for param in model.parameters():
        if param.grad is not None:
            vv = nn.functional.normalize(param.grad, p=2.0, dim = 0)
            v = vv.view(-1)
            vl.append(v)
            fp = torch.cat(vl)  
    model.zero_grad()
    return fp

def reload(fp):
    offset = 0
    for name, param in model.named_parameters():
        shape = param.shape
        param.data = fp[offset: offset + shape.numel()].view(shape)
        offset = offset + shape.numel()
        
def combine(model):
    vl = []
    for name, param in model.named_parameters():
        if param.requires_grad:
            v = param.data.view(-1)
            vl.append(v)
    fp = torch.cat(vl)    
    return fp


# Settings
parser = argparse.ArgumentParser()
parser.add_argument('--no_cuda', action='store_true', default=False, help='Disables CUDA training.')
parser.add_argument('--fastmode', action='store_true', default=False,  help='Validate during training pass.')
parser.add_argument('--seed', type=int, default=4, help='Random seed.')
parser.add_argument('--n_epochs', type=int, default=400, help='Number of epochs to train.')
parser.add_argument('--lr', type=float, default=0.01, help='Initial learning rate.')
parser.add_argument('--weight_decay', type=float, default=5e-4, help='Weight decay (L2 loss on parameters).')
parser.add_argument('--hidden', type=int, default=16, help='Number of hidden units.')
parser.add_argument('--dropout', type=float, default=0.5, help='Dropout rate (1 - keep probability).')
# parser.add_argument('--path', type=str, default='../data/cora/', help='data path')
parser.add_argument('--dataset', type=str, default='cora', help='dataset name')
parser.add_argument('--sub_dataset', type=str, default='', help='dataset name')
opt = parser.parse_args()
opt.cuda = not opt.no_cuda and torch.cuda.is_available()

np.random.seed(opt.seed)
torch.manual_seed(opt.seed)
if opt.cuda:
    torch.cuda.manual_seed(opt.seed)

# Download data
download_data(opt.dataset)

# Load data
adj, features, labels, idx_train, idx_val, idx_test = load_data(opt.dataset,opt.sub_dataset)

# Model and optimizer
model = GCN(nfeat=features.shape[1],
            nhid=opt.hidden,
            nclass=labels.max().item() + 1,
            dropout=opt.dropout)
# optimizer = optim.Adam(model.parameters(), lr=opt.lr, weight_decay=opt.weight_decay)

if opt.cuda:
    model.cuda()
    features = features.cuda()
    adj = adj.cuda()
    labels = labels.cuda()
    idx_train = idx_train.cuda()
    idx_val = idx_val.cuda()
    idx_test = idx_test.cuda()


G_dict = {}
for name in model.named_parameters():
    G_dict[name[0]] = name[1].data
  
sizeG = {}
for key in G_dict:
    sizeG[key] = G_dict[key].shape
w =  combine(model)
sum_G = sum(v.numel() for _, v in G_dict.items())
assert(len(w) ==sum_G)
d = len(w)
lb= 5
device = 'cuda'
P = torch.zeros((d, lb), requires_grad=False).to(device)
AP = torch.zeros((d,lb), requires_grad=False).to(device)
reload(w)
r = FF(features, adj, labels)
rho = torch.norm(r)
epsf = 1
ep = epsf * rho/torch.norm(w)
w1 = w-ep*r
reload(w1)
Ar = (FF(features, adj, labels) -r)/ep
reload(w)
t = torch.norm(Ar)
t = 1.0/t
P[:,0] = t * r
AP[:,0]=  t * Ar 
loss_list = []
i2 = 1
i = 1

#########
# Train #
#########


loss_list = []
val_acc_list = []
for epoch in range(opt.n_epochs):

    model.train()
    alph = AP.t()@r
    with torch.no_grad():
        dire = P@alph
        w = w + dire
        reload(w)
    r = FF(features, adj, labels)

    with torch.no_grad():
        rho = torch.norm(r)
        w1 = w-ep*r
        reload(w1)
    r1 = FF(features, adj, labels)
    Ar = (r1-r)/ep
    reload(w)
    ep = epsf * rho/torch.norm(w)
    p = r
    if i <= lb:
        k = 0
    else:
        k = i2
    while True:
        if k ==lb:
            k = 0
        k +=1
        tau = torch.inner(Ar, AP[:,k-1])
        p = p - tau*(P[:,k-1])
        Ar = Ar -  tau*(AP[:,k-1])
        if k == i2:
            break
    t = torch.norm(Ar)
    if (i2) == lb:
        i2 = 0
    i2 = i2+1
    i = i+1
    t = 1.0/t
    AP[:,i2-1] = t*Ar
    P[:,i2-1] = t*p
    with torch.no_grad():
        model.eval()
        output = model(features, adj)
        loss_train = F.nll_loss(output[idx_train], labels[idx_train])
        acc_val = accuracy(output[idx_val], labels[idx_val])
    print(f'[Epoch {epoch+1:04d}/{opt.n_epochs}]'
          f'[Train Loss: {loss_train.item():.4f}]'
          f'[Validation accuracy: {acc_val.item():.4f}]')
    loss_list.append(loss_train.item())
    val_acc_list.append(acc_val.item())
    
with open("results/loss_nltgcr4.pkl", "wb") as fp:  
    pickle.dump(loss_list, fp)

with open("results/acc_nltgcr4.pkl", "wb") as fp:  
    pickle.dump(val_acc_list, fp)

plt.semilogy(loss_list)
###########
# Testing #
###########
model.eval()
output = model(features, adj)
loss_test = F.nll_loss(output[idx_test], labels[idx_test])
acc_test = accuracy(output[idx_test], labels[idx_test])
print("[Test result]"
      f"[Test loss: {loss_test.item():.4f}]"
      f"[Test accuracy: {acc_test.item():.4f}]")