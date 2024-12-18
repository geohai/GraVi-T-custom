import os
import yaml
import torch
import torch.optim as optim
from torch_geometric.loader import DataLoader
from torch_geometric.nn import pool
from gravit.utils.parser import get_args, get_cfg
from gravit.utils.logger import get_logger
from gravit.models import build_model, get_loss_func
from gravit.datasets import GraphDataset

from gravit.utils.formatter import get_formatting_data_dict, get_formatted_preds, get_formatted_preds_egoexo_omnivore, get_formatted_preds_framewise
from gravit.utils.eval_tool import get_eval_score

import numpy as np
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP

# Initialize distributed training
# dist.init_process_group("gloo")

def train(cfg):
    """
    Run the training process given the configuration
    """

    # Input and output paths
    path_graphs = os.path.join(cfg['root_data'], f'graphs/{cfg["graph_name"]}')
    path_result = os.path.join(cfg['root_result'], f'{cfg["exp_name"]}')
    if cfg['split'] is not None:
        path_graphs = os.path.join(path_graphs, f'split{cfg["split"]}')
    os.makedirs(path_result, exist_ok=True)
    print(cfg)

    # Prepare the logger and save the current configuration for future reference
    logger = get_logger(path_result, file_name='train')
    logger.info(cfg['exp_name'])
    logger.info('Saving the configuration file')
    with open(os.path.join(path_result, 'cfg.yaml'), 'w') as f:
        yaml.dump({k: v for k, v in cfg.items() if v is not None}, f, default_flow_style=False, sort_keys=False)

    # Build a model and prepare the data loaders
    logger.info('Preparing a model and data loaders')
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(device)
    model = build_model(cfg, device)
    model.to(device)

    print(f'Loading the data from {path_graphs}')
    train_loader = DataLoader(GraphDataset(os.path.join(path_graphs, 'train')), batch_size=cfg['batch_size'], shuffle=True)
    val_loader = DataLoader(GraphDataset(os.path.join(path_graphs, 'val')))
   
    # Prepare the experiment
    loss_func = get_loss_func(cfg)
    loss_func_val = get_loss_func(cfg, 'val')
    optimizer = optim.Adam(model.parameters(), lr=cfg['lr'], weight_decay=cfg['wd'])
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg['sch_param'])

    # Run the training process
    logger.info('Training process started')
    print(f'Length of train_loader:', len(train_loader))
    print(f'Batch size:', cfg['batch_size'])


    min_loss_val = float('inf')
    for epoch in range(1, cfg['num_epoch']+1):
        print(f'------- Epoch: {epoch} --------')
        model.train()

        # Train for a single epoch
        loss_sum = 0
        # accumulated_gradients = {name: torch.zeros_like(param) for name, param in model.named_parameters()}
        for data in train_loader:
            optimizer.zero_grad()

            data = data.to(device)

            y = data.y_dict['omnivore'].to(device)
            if len(data.x_dict['omnivore']) == 1:
                # print('Skipping -> data.x_dict[omnivore]:', data.x_dict['omnivore'])
                continue

            if cfg['use_spf']:
                c = data.c.to(device)
            else:
                c = None

            logits = model(data, c)
            
            loss = loss_func(logits, y)
            loss.backward()
            loss_sum += loss.item()
            optimizer.step()


        # Adjust the learning rate
        scheduler.step()

        loss_train = loss_sum / len(train_loader)

        # Get the validation loss
        loss_val = val(val_loader, cfg['use_spf'], model, device, loss_func_val)
        

        # Save the best-performing checkpoint
        if loss_val < min_loss_val:
            min_loss_val = loss_val
            epoch_best = epoch
            torch.save(model.state_dict(), os.path.join(path_result, 'ckpt_best.pt'))

        # Log the losses for every epoch
        logger.info(f'Epoch [{epoch:03d}|{cfg["num_epoch"]:03d}] loss_train: {loss_train:.4f}, loss_val: {loss_val:.4f}, best: epoch {epoch_best:03d}')

    logger.info('Training finished')


def val(val_loader, use_spf, model, device, loss_func):
    """
    Run a single validation process
    """

    model.eval()
    data_dict = get_formatting_data_dict(cfg)
    loss_sum = 0
    predictions = []
    with torch.no_grad():
        for data in val_loader:  
            y = data.y_dict['omnivore'].to(device)
            data = data.to(device)
            
            if use_spf:
                c = data.c.to(device)
            else:
                c = None
                
            logits = model(data, c)

            loss = loss_func(logits, y)
            loss_sum += loss.item()

    return loss_sum / len(val_loader)


if __name__ == "__main__":
    args = get_args()
    cfg = get_cfg(args)

    train(cfg)
