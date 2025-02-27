import torch
from torch.nn import Module, ModuleList, Conv1d, Sequential, ReLU, Dropout, functional as F
from torch_geometric.nn import Linear, EdgeConv, GATv2Conv, SAGEConv, BatchNorm, RGCNConv
import torch_geometric
import numpy as np



class DilatedResidualLayer(Module):
    def __init__(self, dilation, in_channels, out_channels):
        super(DilatedResidualLayer, self).__init__()
        self.conv_dilated = Conv1d(in_channels, out_channels, kernel_size=3, padding=dilation, dilation=dilation)
        self.conv_1x1 = Conv1d(out_channels, out_channels, kernel_size=1)
        self.relu = ReLU()
        self.dropout = Dropout()

    def forward(self, x):
        out = self.relu(self.conv_dilated(x))
        out = self.conv_1x1(out)
        out = self.dropout(out)
        return x + out


# This is for the iterative refinement (we refer to MSTCN++: https://github.com/sj-li/MS-TCN2)
class Refinement(Module):
    def __init__(self, final_dim, num_layers=10, interm_dim=64):
        super(Refinement, self).__init__()
        self.conv_1x1 = Conv1d(final_dim, interm_dim, kernel_size=1)
        self.layers = ModuleList([DilatedResidualLayer(2**i, interm_dim, interm_dim) for i in range(num_layers)])
        self.conv_out = Conv1d(interm_dim, final_dim, kernel_size=1)

    def forward(self, x):
        f = self.conv_1x1(x)
        for layer in self.layers:
            f = layer(f)
        out = self.conv_out(f)
        return out
    

# class SubgraphConv1D(Module):
#     def __init__(self, in_channels, out_channels, max_seq_len=40, kernel_size=3, stride=1, padding=1):
#         super(SubgraphConv1D, self).__init__()
#         self.conv1D = Conv1d(in_channels, out_channels, kernel_size, stride, padding)
#         self.batch_norm = BatchNorm(out_channels)
#         self.relu = ReLU()
#         self.dropout = Dropout()
#         self.max_seq_len = max_seq_len
#         self.output_dim = int((self.max_seq_len - kernel_size + 2*padding) / stride + 1)

#     def forward(self, x, batch):
#         x = graph_to_nn_batch(x, batch, max_seq_len=self.max_seq_len)
#         out = self.conv1D(x)
#         out = self.batch_norm(out)
#         out = self.relu(out)
#         out = self.dropout(out)
#         out,batch = nn_batch_to_graph(out, batch, self.output_dim, self.max_seq_len)
#         return out, batch

# # ORIGINAL SPELL MODEL
# class SPELL(Module):
#     def __init__(self, cfg, save_feats=False):
#         super(SPELL, self).__init__()
#         self.use_spf = cfg['use_spf'] # whether to use the spatial features
#         self.use_ref = cfg['use_ref']
#         self.num_modality = cfg['num_modality']
#         self.save_feats = save_feats

#         channels = [cfg['channel1'], cfg['channel2']]
#         final_dim = cfg['final_dim']
#         input_dim = cfg['input_dim'] 
        
#         num_att_heads = cfg['num_att_heads']
#         dropout = cfg['dropout']


#         if self.use_spf:
#             self.layer_spf = Linear(-1, cfg['proj_dim']) # projection layer for spatial features

#         self.layer011 = Linear(input_dim, channels[0]) 
#         if self.num_modality == 2:
#             self.layer012 = Linear(-1, channels[0])

#         self.batch01 = BatchNorm(channels[0])
#         self.relu = ReLU()
#         self.dropout = Dropout(dropout)

#         self.layer11 = EdgeConv(Sequential(Linear(2*channels[0], channels[0]), ReLU(), Linear(channels[0], channels[0])))
#         self.batch11 = BatchNorm(channels[0])
#         self.layer12 = EdgeConv(Sequential(Linear(2*channels[0], channels[0]), ReLU(), Linear(channels[0], channels[0])))
#         self.batch12 = BatchNorm(channels[0])
#         self.layer13 = EdgeConv(Sequential(Linear(2*channels[0], channels[0]), ReLU(), Linear(channels[0], channels[0])))
#         self.batch13 = BatchNorm(channels[0])

#         if num_att_heads > 0:
#             self.layer21 = GATv2Conv(channels[0], channels[1], heads=num_att_heads)
#         else:
#             self.layer21 = SAGEConv(channels[0], channels[1])
#             num_att_heads = 1
#         self.batch21 = BatchNorm(channels[1]*num_att_heads)

#         self.layer31 = SAGEConv(channels[1]*num_att_heads, final_dim)
#         self.layer32 = SAGEConv(channels[1]*num_att_heads, final_dim)
#         self.layer33 = SAGEConv(channels[1]*num_att_heads, final_dim)

#         if self.use_ref:
#             self.layer_ref1 = Refinement(final_dim)
#             self.layer_ref2 = Refinement(final_dim)
#             self.layer_ref3 = Refinement(final_dim)


#     def forward(self, x, edge_index, edge_attr, c=None, batch=None, view_idx=None):
#         feature_dim = x.shape[1]

#         if self.use_spf:
#             x_visual = self.layer011(torch.cat((x[:, :feature_dim//self.num_modality], self.layer_spf(c)), dim=1))
#         else:
#             x_visual = self.layer011(x[:, :feature_dim//self.num_modality])

#         if self.num_modality == 1:
#             x = x_visual
#         elif self.num_modality == 2:
#             x_audio = self.layer012(x[:, feature_dim//self.num_modality:])
#             x = x_visual + x_audio

#         x = self.batch01(x)
#         x = self.relu(x)

#         edge_index_f = edge_index[:, edge_attr<=0]
#         edge_index_b = edge_index[:, edge_attr>=0]

  
#         ######## Forward-graph stream
#         x1 = self.layer11(x, edge_index_f)
#         x1 = self.batch11(x1)
#         x1 = self.relu(x1)
#         x1 = self.dropout(x1)
#         x1 = self.layer21(x1, edge_index_f)
#         x1 = self.batch21(x1)
#         x1 = self.relu(x1)
#         x1 = self.dropout(x1)

#         ######## Backward-graph stream
#         x2 = self.layer12(x, edge_index_b)
#         x2 = self.batch12(x2)
#         x2 = self.relu(x2)
#         x2 = self.dropout(x2)
#         x2 = self.layer21(x2, edge_index_b)
#         x2 = self.batch21(x2)
#         x2 = self.relu(x2)
#         x2 = self.dropout(x2)

#         ######## Undirected-graph stream
#         x3 = self.layer13(x, edge_index)
#         x3 = self.batch13(x3)
#         x3 = self.relu(x3)
#         x3 = self.dropout(x3)
#         x3 = self.layer21(x3, edge_index)
#         x3 = self.batch21(x3)
#         x3 = self.relu(x3)
#         x3 = self.dropout(x3)

#         x1 = self.layer31(x1, edge_index_f)
#         x2 = self.layer32(x2, edge_index_b)
#         x3 = self.layer33(x3, edge_index)

#         out = x1+x2+x3
            
        
#         if self.use_ref:
#             xr0 = torch.permute(out, (1, 0)).unsqueeze(0)
#             xr1 = self.layer_ref1(torch.softmax(xr0, dim=1))
#             xr2 = self.layer_ref2(torch.softmax(xr1, dim=1))
#             xr3 = self.layer_ref3(torch.softmax(xr2, dim=1))
#             out = torch.stack((xr0, xr1, xr2, xr3), dim=0).squeeze(1).transpose(2, 1).contiguous()

#         return out


#### REMOVED GAT/SAGEConv Layer #####
class SPELL(Module):
    def __init__(self, cfg, save_feats=False):
        super(SPELL, self).__init__()
        self.use_spf = cfg['use_spf'] # whether to use the spatial features
        self.use_ref = cfg['use_ref']
        self.num_modality = cfg['num_modality']
        self.save_feats = save_feats

        channels = [cfg['channel1'], cfg['channel2']]
        final_dim = cfg['final_dim']
        input_dim = cfg['input_dim'] 
        
        num_att_heads = cfg['num_att_heads']
        dropout = cfg['dropout']


        if self.use_spf:
            self.layer_spf = Linear(-1, cfg['proj_dim']) # projection layer for spatial features

        self.layer011 = Linear(input_dim, channels[0]) 
        if self.num_modality == 2:
            self.layer012 = Linear(-1, channels[0])

        self.batch01 = BatchNorm(channels[0])
        self.relu = ReLU()
        self.dropout = Dropout(dropout)

        ######
        self.layer11 = EdgeConv(Sequential(Linear(2*channels[0], channels[0]), ReLU(), Linear(channels[0], channels[1])))
        self.batch11 = BatchNorm(channels[1])
        self.layer12 = EdgeConv(Sequential(Linear(2*channels[0], channels[0]), ReLU(), Linear(channels[0], channels[1])))
        self.batch12 = BatchNorm(channels[1])
        self.layer13 = EdgeConv(Sequential(Linear(2*channels[0], channels[0]), ReLU(), Linear(channels[0], channels[1])))
        self.batch13 = BatchNorm(channels[1])

        self.layer31 = RGCNConv(channels[1], final_dim, num_relations=2)
        self.layer32 = RGCNConv(channels[1], final_dim, num_relations=2)
        self.layer33 = RGCNConv(channels[1], final_dim, num_relations=2)
        # self.layer31 = SAGEConv(channels[1], final_dim)
        # self.layer32 = SAGEConv(channels[1], final_dim)
        # self.layer33 = SAGEConv(channels[1], final_dim)
        #####

        if num_att_heads > 0:
            self.layer21 = GATv2Conv(channels[0], channels[1], heads=num_att_heads)
        else:
            self.layer21 = SAGEConv(channels[0], channels[1])
            num_att_heads = 1
        self.batch21 = BatchNorm(channels[1]*num_att_heads)

        if self.use_ref:
            self.layer_ref1 = Refinement(final_dim)
            self.layer_ref2 = Refinement(final_dim)
            self.layer_ref3 = Refinement(final_dim)

    def forward(self, x, edge_index, edge_attr, c=None, batch=None, view_idx=None):
    # def forward(self, data):
        # y = torch.cat([dt.y for dt in data], 0).to(device)
        # x = torch.cat([dt.x for dt in data], 0).to(device)
        # edge_index = torch.cat([dt.edge_index for dt in data], 1).to(device)
        # edge_attr = torch.cat([dt.edge_attr for dt in data], 0).to(device)

        # x = data.x
        # edge_index = data.edge_index
        # edge_attr = data.edge_attr
        # c = None #data.c



        # feature_dim = x.shape[1]

        # if self.use_spf:
        #     x_visual = self.layer011(torch.cat((x[:, :feature_dim//self.num_modality], self.layer_spf(c)), dim=1))
        # else:
        #     x_visual = self.layer011(x[:, :feature_dim//self.num_modality])

        # if self.num_modality == 1:
        #     x = x_visual
        # elif self.num_modality == 2:
        #     x_audio = self.layer012(x[:, feature_dim//self.num_modality:])
        #     x = x_visual + x_audio

        x = self.batch01(x)
        x = self.relu(x)

        edge_index_f = edge_index[:, edge_attr<=0]
        edge_index_b = edge_index[:, edge_attr>=0]

        edge_type = (edge_attr != -2).type(torch.int64)
        edge_type_f = (edge_attr[edge_attr<=0] != -2).type(torch.int64)
        edge_type_b = (edge_attr[edge_attr>=0] != -2).type(torch.int64)
        

  
        ######## Forward-graph stream
        x1 = self.layer11(x, edge_index_f)
        x1 = self.batch11(x1)
        x1 = self.relu(x1)
        x1 = self.dropout(x1)
        # x1 = self.layer21(x1, edge_index_f)
        # x1 = self.batch21(x1)
        # x1 = self.relu(x1)
        # x1 = self.dropout(x1)

        ######## Backward-graph stream
        x2 = self.layer12(x, edge_index_b)
        x2 = self.batch12(x2)
        x2 = self.relu(x2)
        x2 = self.dropout(x2)
        # x2 = self.layer21(x2, edge_index_b)
        # x2 = self.batch21(x2)
        # x2 = self.relu(x2)
        # x2 = self.dropout(x2)

        ######## Undirected-graph stream
        x3 = self.layer13(x, edge_index)
        x3 = self.batch13(x3)
        x3 = self.relu(x3)
        x3 = self.dropout(x3)
        # x3 = self.layer21(x3, edge_index)
        # x3 = self.batch21(x3)
        # x3 = self.relu(x3)
        # x3 = self.dropout(x3)

        # x1 = self.layer31(x1, edge_index_f)
        # x2 = self.layer32(x2, edge_index_b)
        # x3 = self.layer33(x3, edge_index)
        x1 = self.layer31(x1, edge_index_f, edge_type_f)
        x2 = self.layer32(x2, edge_index_b, edge_type_b)
        x3 = self.layer33(x3, edge_index, edge_type)

        out = x1+x2+x3
            
        
        if self.use_ref:
            xr0 = torch.permute(out, (1, 0)).unsqueeze(0)
            xr1 = self.layer_ref1(torch.softmax(xr0, dim=1))
            xr2 = self.layer_ref2(torch.softmax(xr1, dim=1))
            xr3 = self.layer_ref3(torch.softmax(xr2, dim=1))
            out = torch.stack((xr0, xr1, xr2, xr3), dim=0).squeeze(1).transpose(2, 1).contiguous()

        return out