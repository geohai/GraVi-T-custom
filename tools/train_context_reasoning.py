import os
import yaml
import torch
import torch.optim as optim
from torch_geometric.loader import DataLoader
from gravit.utils.parser import get_args, get_cfg
from gravit.utils.logger import get_logger
from gravit.models import build_model, get_loss_func
from gravit.datasets import GraphDataset, EgoExoOmnivoreTrainDataset, EgoExoOmnivoreValDataset


def train(cfg):
    """
    Run the training process given the configuration
    """

    # Input and output paths
    path_graphs = os.path.join(cfg['root_data'], f'graphs/{cfg["graph_name"]}')
    if cfg['split'] is not None:
        path_graphs = os.path.join(path_graphs, f'split{cfg["split"]}')
    path_result = os.path.join(cfg['root_result'], f'{cfg["exp_name"]}')
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

    if 'mlp' not in cfg['graph_name']:
        train_loader = DataLoader(GraphDataset(os.path.join(path_graphs, 'train')), batch_size=cfg['batch_size'], shuffle=True)
        val_loader = DataLoader(GraphDataset(os.path.join(path_graphs, 'val')))
    
    else:
        train_loader = torch.utils.data.DataLoader(EgoExoOmnivoreTrainDataset(cfg['split']), batch_size=cfg['batch_size'], shuffle=True, num_workers=6)
        val_loader = torch.utils.data.DataLoader(EgoExoOmnivoreValDataset(cfg['split']), batch_size=cfg['batch_size'], shuffle=False, num_workers=6)

    # Prepare the experiment
    loss_func = get_loss_func(cfg)
    loss_func_val = get_loss_func(cfg, 'val')
    optimizer = optim.Adam(model.parameters(), lr=cfg['lr'], weight_decay=cfg['wd'])
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg['sch_param'])

    # Run the training process
    logger.info('Training process started')

    min_loss_val = float('inf')
    for epoch in range(1, cfg['num_epoch']+1):
        print(f'------- Epoch: {epoch} --------')
        model.train()

        # Train for a single epoch
        loss_sum = 0.
        for data in train_loader:
            optimizer.zero_grad()

            if 'mlp' not in cfg['graph_name']:
                x, y = data.x.to(device), data.y.to(device)
                edge_index = data.edge_index.to(device)
                edge_attr = data.edge_attr.to(device)
                c = None
                if cfg['use_spf']:
                    c = data.c.to(device)

                logits = model(x, edge_index, edge_attr, c)
            
            else:
                x, y = data
                x = x.to(device)
                y = y.to(device)
                edge_index = None
                edge_attr = None
                c = None

                logits = model(x)
                logits = logits.squeeze(1)
                # max_index = torch.argmax(logits, dim=2)
                # Create a tensor of zeros with the same shape as logits
                # one_hot = torch.zeros_like(logits)

                # Set the elements at the max_indices to 1
                # logits = one_hot.scatter_(2, max_index.unsqueeze(2), 1)
            print(logits.dtype, y.dtype)
            print(logits.shape, y.shape)
            loss = loss_func(logits, y)
            print(loss)
            loss.backward()
            loss_sum += loss.item()
            optimizer.step()

        # Adjust the learning rate
        scheduler.step()

        loss_train = loss_sum / len(train_loader)
        print(loss_train)

        # Get the validation loss
        loss_val = val(val_loader, cfg['use_spf'], model, device, loss_func_val)
        print(loss_val)

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
    loss_sum = 0
    with torch.no_grad():
        for data in val_loader:  
            if 'mlp' not in cfg['graph_name']:
                x, y = data.x.to(device), data.y.to(device)
                edge_index = data.edge_index.to(device)
                edge_attr = data.edge_attr.to(device)
                c = None
                if cfg['use_spf']:
                    c = data.c.to(device)

                logits = model(x, edge_index, edge_attr, c)
            
            else:
                x, y = data
                x = x.to(device)
                y = y.to(device)
                edge_index = None
                edge_attr = None
                c = None

                logits = model(x)
                logits = logits.squeeze(1)
               

            # logits = logits[:, :y.size(0)] # TODO: HOW TO HANDLE END OF WINDOWS

            loss = loss_func(logits, y)
            loss_sum += loss.item()

    return loss_sum / len(val_loader)


if __name__ == "__main__":
    args = get_args()
    cfg = get_cfg(args)

    train(cfg)
